/** Measured, hash-bound PCM input and one final AAC encode. No model runs here. */
import { readFile, writeFile, lstat, rm } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { createHash } from 'node:crypto'
import { validateStoryboard } from './storyboard.mjs'
const need=(ok)=>{if(!ok)throw new Error('Invalid measured narration timeline/audio')}
const sha=data=>createHash('sha256').update(data).digest('hex')
const same=(a,b)=>Math.abs(a-b)<1e-7
const finite=n=>typeof n==='number' && Number.isFinite(n)
async function member(root,path,hash) {
  need(typeof path==='string' && /^narration\/[A-Za-z0-9_/-]+\.wav$/.test(path) && !path.split('/').includes('..'))
  let current=resolve(root)
  for(const part of path.split('/')) { current=join(current,part);need(!(await lstat(current)).isSymbolicLink()) }
  const info=await lstat(current);need(info.isFile() && info.size>44 && info.size<=6*1024*1024)
  const raw=await readFile(current);need(sha(raw)===hash)
  return wavPCM(raw)
}
export function pcmWav(pcm) {
  const header=Buffer.alloc(44)
  header.write('RIFF');header.writeUInt32LE(pcm.length+36,4);header.write('WAVEfmt ',8);header.writeUInt32LE(16,16)
  header.writeUInt16LE(1,20);header.writeUInt16LE(1,22);header.writeUInt32LE(24000,24);header.writeUInt32LE(48000,28);header.writeUInt16LE(2,32);header.writeUInt16LE(16,34);header.write('data',36);header.writeUInt32LE(pcm.length,40)
  return Buffer.concat([header,pcm])
}
function wavPCM(raw) {
  need(raw.length>=44 && raw.toString('ascii',0,4)==='RIFF' && raw.readUInt32LE(4)===raw.length-8 && raw.toString('ascii',8,12)==='WAVE')
  let pcm=null, format=false
  for(let offset=12;offset+8<=raw.length;) {
    const type=raw.toString('ascii',offset,offset+4), size=raw.readUInt32LE(offset+4), start=offset+8
    need(start+size<=raw.length)
    if(type==='fmt ') {need(size>=16 && raw.readUInt16LE(start)===1 && raw.readUInt16LE(start+2)===1 && raw.readUInt32LE(start+4)===24000 && raw.readUInt32LE(start+8)===48000 && raw.readUInt16LE(start+12)===2 && raw.readUInt16LE(start+14)===16);format=true}
    if(type==='data') {need(pcm===null && size>0 && size%2===0);pcm=raw.subarray(start,start+size)}
    offset=start+size+(size%2)
  }
  need(format && pcm!==null);return pcm
}
export async function loadTimeline(path,input) {
  const raw=await readFile(path);need(raw.length<1024*1024)
  const t=JSON.parse(raw), nRaw=await readFile(join(input,'narrative.json')), pRaw=await readFile(join(input,'scenes.json'))
  const n=JSON.parse(nRaw), p=JSON.parse(pRaw)
  validateStoryboard(n,p)
  need(t.schema_version===1 && t.run_id===n.run_id && t.narrative_sha256===sha(nRaw) && t.scenes_sha256===sha(pRaw) && t.sample_rate===24000 && t.fps===30)
  need(t.model_revision==='f3ff3571791e39611d31c381e3a41a3af07b4987' && JSON.stringify(t.narration)===JSON.stringify(p.narration))
  need(Array.isArray(t.scenes) && t.scenes.length===n.slides.length)
  let frames=0
  const pcm=[]
  for(const [i,scene] of t.scenes.entries()) {
    const slide=n.slides[i], policy=p.timing_policy
    need(scene.id===slide.id && finite(scene.audio_seconds) && scene.audio_seconds>0 && finite(scene.duration_seconds) && finite(scene.start_seconds))
    const samples=await member(dirname(path),scene.audio_path,scene.audio_sha256)
    need(same(scene.audio_seconds,samples.length/48000))
    const frameCount=Math.ceil(Math.max(policy.min_scene_seconds,scene.audio_seconds+policy.lead_seconds+policy.tail_seconds)*30)
    need(scene.frame_count===frameCount && same(scene.duration_seconds,frameCount/30) && same(scene.start_seconds,frames/30) && scene.duration_seconds<=policy.max_scene_seconds)
    need(Array.isArray(scene.sentence_audio) && scene.sentence_audio.length===slide.narration.length && Array.isArray(scene.sentence_offsets) && scene.sentence_offsets.length===slide.narration.length)
    const pieces=[];let count=0
    for(const [j,audio] of scene.sentence_audio.entries()) {
      if(j) {const gap=Buffer.alloc(Math.round(policy.sentence_gap_seconds*48000));pieces.push(gap);count+=gap.length}
      const sentence=await member(dirname(path),audio.path,audio.sha256), offset=scene.sentence_offsets[j]
      need(offset && same(offset.start_seconds,count/48000) && same(offset.end_seconds,(count+sentence.length)/48000))
      pieces.push(sentence);count+=sentence.length
    }
    need(samples.equals(Buffer.concat(pieces)))
    const padding=Buffer.alloc(frameCount*800*2)
    samples.copy(padding,Math.round(policy.lead_seconds*48000))
    pcm.push(padding);frames+=frameCount
  }
  need(finite(t.duration_seconds) && same(t.duration_seconds,frames/30) && t.duration_seconds<=p.timing_policy.max_total_seconds)
  return {...t,pcm:Buffer.concat(pcm),captions:await captionFile(dirname(path),t)}
}

/** Sentence captions are generated beside the measured timeline and hash-bound,
 * so a changed cue file fails the render instead of shipping altered wording. */
async function captionFile(root,timeline) {
  need(timeline.captions_path==='captions.vtt' && /^[0-9a-f]{64}$/.test(timeline.captions_sha256))
  const path=join(root,timeline.captions_path)
  need(!(await lstat(path)).isSymbolicLink())
  const raw=await readFile(path)
  need(raw.length<=4*1024*1024 && sha(raw)===timeline.captions_sha256 && raw.toString('utf8',0,6)==='WEBVTT')
  return path
}

export async function muxPresentation(segments,timeline,output,run) {
  need(segments.length===timeline.scenes.length)
  for(const [i,path] of segments.entries()) {
    const p=JSON.parse(await run('ffprobe',['-v','error','-show_format','-show_streams','-of','json',path],output))
    const v=p.streams.find(s=>s.codec_type==='video')
    need(v && v.width===1280 && v.height===720 && v.codec_name==='h264' && v.pix_fmt==='yuv420p' && v.avg_frame_rate==='30/1' && Number(v.nb_frames)===timeline.scenes[i].frame_count && Math.abs(Number(p.format.duration)-timeline.scenes[i].duration_seconds)<=.25)
  }
  await writeFile(join(output,'concat.txt'),segments.map(p=>`file '${resolve(p).replaceAll("'","'\\''")}'`).join('\n'))
  await run('ffmpeg',['-v','error','-y','-f','concat','-safe','0','-i','concat.txt','-an','-c:v','copy','silent.mp4'],output)
  await writeFile(join(output,'padded-narration.wav'),pcmWav(timeline.pcm))
  await run('ffmpeg',['-v','error','-y','-i','silent.mp4','-i','padded-narration.wav','-i',timeline.captions,'-map','0:v:0','-map','1:a:0','-map','2:s:0','-c:v','copy','-c:a','aac','-b:a','128k','-ar','24000','-c:s','mov_text','-metadata:s:s:0','language=eng','-movflags','+faststart','executive-summary.mp4'],output)
  const probe=JSON.parse(await run('ffprobe',['-v','error','-show_format','-show_streams','-of','json','executive-summary.mp4'],output))
  const video=probe.streams.find(s=>s.codec_type==='video'),audio=probe.streams.find(s=>s.codec_type==='audio')
  const text=probe.streams.find(s=>s.codec_type==='subtitle')
  need(probe.streams.length===3 && video && audio && text && text.codec_name==='mov_text' && video.codec_name==='h264' && video.width===1280 && video.height===720 && video.pix_fmt==='yuv420p' && video.avg_frame_rate==='30/1' && Number(video.nb_frames)===timeline.scenes.reduce((sum,s)=>sum+s.frame_count,0) && audio.codec_name==='aac')
  need(Math.abs(Number(probe.format.duration)-timeline.duration_seconds)<=.25 && Math.abs(Number(audio.duration)-timeline.duration_seconds)<=.25 && Math.abs(Number(video.duration)-timeline.duration_seconds)<=.25)
  need((await lstat(join(output,'executive-summary.mp4'))).size<=1024**3)
  await run('ffmpeg',['-v','error','-xerror','-i','executive-summary.mp4','-f','null','-'],output)
  return {status:'validated',path:'executive-summary.mp4',duration_seconds:Number(probe.format.duration),width:1280,height:720,fps:video.avg_frame_rate,audio_codec:audio.codec_name,subtitle_codec:text.codec_name}
}

/** Playwright has variable startup and final-frame padding. Legacy callers crop
 * by measured media end; template 4 binds capture to a private slate's exit. */
export async function encodeCapture(raw,scene,output,cwd,run,{anchor_slate=false}={}) {
  const probe=JSON.parse(await run('ffprobe',['-v','error','-show_format','-of','json',raw],cwd))
  const duration=Number(probe.format.duration)
  need(finite(duration) && duration>=scene.duration_seconds)
  // Template 4 has a trusted private pre-roll slate. Bind its visible exit to
  // actual frame PTS; browser startup and final-frame padding are variable.
  // Legacy callers retain the original measured-media-end crop unchanged.
  const offset=anchor_slate ? await slateCaptureOffset(raw,output,cwd,run) : duration-scene.duration_seconds
  need(finite(offset) && offset>=0)
  if (!(offset+scene.duration_seconds<=duration+.04)) {
    // Numeric capture diagnostics are safe to retain in the manifest/log. Do
    // not include raw paths, browser content or private pre-roll artifacts.
    throw new Error(`Insufficient captured scene coverage: raw_seconds=${duration}, anchor_seconds=${offset}, required_seconds=${scene.duration_seconds}, available_seconds=${Number((duration-offset).toFixed(6))}`)
  }
  await run('ffmpeg',['-v','error','-y','-ss',String(offset),'-i',raw,'-an','-vf','fps=30,tpad=stop_mode=clone:stop_duration=0.1','-frames:v',String(scene.frame_count),'-c:v','libx264','-pix_fmt','yuv420p',output],cwd)
  return offset
}

async function slateCaptureOffset(raw,output,cwd,run) {
  const timestamps=resolve(cwd,`${output}.anchor-frames.json`), colors=resolve(cwd,`${output}.anchor-rgb`)
  try {
    await run('ffprobe',['-v','error','-select_streams','v:0','-show_entries','frame=best_effort_timestamp_time','-of','json','-o',timestamps,raw],cwd)
    await run('ffmpeg',['-v','error','-y','-i',raw,'-vf','crop=2:2:2:2,scale=1:1','-fps_mode','passthrough','-f','rawvideo','-pix_fmt','rgb24',colors],cwd)
    const frames=JSON.parse(await readFile(timestamps)).frames, pixels=await readFile(colors)
    need(pixels.length===frames.length*3)
    let slateFrames=0
    for(let i=0;i<frames.length;i++) {
      const magenta=pixels[i*3]>180 && pixels[i*3+1]<80 && pixels[i*3+2]>180
      if(magenta) { slateFrames++; continue }
      if(slateFrames>=3) return Number(frames[i].best_effort_timestamp_time)
      slateFrames=0
    }
    throw new Error('Trusted capture slate transition is missing')
  } finally { await rm(timestamps,{force:true});await rm(colors,{force:true}) }
}
