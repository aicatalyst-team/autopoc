import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, mkdir, readFile, writeFile, rm } from 'node:fs/promises'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { loadTimeline, pcmWav, muxPresentation, encodeCapture } from './audio.mjs'
const sha = data => createHash('sha256').update(data).digest('hex')
async function fixture(seconds = 1, count = 6) {
  const root = await mkdtemp(join(tmpdir(),'autopoc-audio-'))
  const input = join(root,'input'), speech = join(root,'speech')
  await mkdir(input); await mkdir(join(speech,'narration'),{recursive:true})
  const narrative = JSON.parse(await readFile(new URL('../tests/fixtures/executive-story/simple/narrative.json',import.meta.url)))
  while(narrative.slides.length < count) { const extra = structuredClone(narrative.slides[2]);extra.id=`extra-${narrative.slides.length}`;narrative.slides.splice(3,0,extra) }
  const plan = JSON.parse(await readFile(new URL('../tests/fixtures/executive-story/simple/scenes.json',import.meta.url)))
  plan.slide_ids = narrative.slides.map(s=>s.id)
  const n = JSON.stringify(narrative), p = JSON.stringify(plan)
  await writeFile(join(input,'narrative.json'),n);await writeFile(join(input,'scenes.json'),p)
  let frames = 0
  const scenes = []
  for (const [i,slide] of narrative.slides.entries()) {
    const pcm = Buffer.alloc(seconds*24000*2)
    for(let k=0;k<seconds*24000;k++) pcm.writeInt16LE(Math.round(10000*Math.sin(2*Math.PI*(i%2?880:440)*k/24000)),k*2)
    const audio = pcmWav(pcm)
    const path = `narration/${slide.id}.wav`
    await writeFile(join(speech,path),audio)
    const frame_count = Math.ceil(Math.max(6,seconds+1)*30)
    scenes.push({ id:slide.id,audio_path:path,audio_sha256:sha(audio),audio_seconds:seconds,duration_seconds:frame_count/30,frame_count,start_seconds:frames/30,sentence_offsets:[{start_seconds:0,end_seconds:seconds}],sentence_audio:[{path,sha256:sha(audio)}] })
    frames+=frame_count
  }
  const cue=s=>`${String(Math.floor(s/3600)).padStart(2,'0')}:${String(Math.floor(s/60)%60).padStart(2,'0')}:${String(Math.floor(s%60)).padStart(2,'0')}.${String(Math.round(s*1000)%1000).padStart(3,'0')}`
  const lines=['WEBVTT','']
  for(const [i,slide] of narrative.slides.entries()) {
    const start=scenes[i].start_seconds+.35
    lines.push(`${cue(start)} --> ${cue(start+seconds)}`,slide.narration[0].text,'')
  }
  const captions=lines.join('\n')
  await writeFile(join(speech,'captions.vtt'),captions)
  const timeline = {schema_version:1,run_id:narrative.run_id,narrative_sha256:sha(n),scenes_sha256:sha(p),narration:plan.narration,model_revision:'f3ff3571791e39611d31c381e3a41a3af07b4987',captions_path:'captions.vtt',captions_sha256:sha(captions),sample_rate:24000,fps:30,duration_seconds:frames/30,scenes}
  const path=join(speech,'timeline.json')
  const save=()=>writeFile(path,JSON.stringify(timeline))
  await save()
  return {root,input,speech,path,timeline,save}
}

test('measured timeline accepts more than six scenes and 180 seconds',async()=>{
  const f=await fixture(24,8)
  try { const t=await loadTimeline(f.path,f.input);assert.equal(t.duration_seconds,200);assert.equal(t.scenes.length,8) }
  finally {await rm(f.root,{recursive:true,force:true})}
})
for(const bad of ['hash','order','duration','frames','sentences','pcm','path','identity','nan','captions','caption-hash']) test(`refuse changed ${bad} before recording`,async()=>{
  const f=await fixture()
  try {
    const s=f.timeline.scenes[0]
    if(bad==='hash')s.audio_sha256='0'.repeat(64)
    if(bad==='order')f.timeline.scenes.reverse()
    if(bad==='duration')s.duration_seconds=2
    if(bad==='frames')s.frame_count=181
    if(bad==='sentences')s.sentence_offsets[0].end_seconds=.5
    if(bad==='pcm')await writeFile(join(f.speech,s.audio_path),'not WAV')
    if(bad==='path')s.audio_path='../private.wav'
    if(bad==='identity')f.timeline.narrative_sha256='0'.repeat(64)
    if(bad==='nan')s.audio_seconds=null
    if(bad==='captions')await writeFile(join(f.speech,'captions.vtt'),'WEBVTT\n\n00:00:00.350 --> 00:00:01.350\nreworded after review\n')
    if(bad==='caption-hash')f.timeline.captions_sha256='0'.repeat(64)
    await f.save();await assert.rejects(loadTimeline(f.path,f.input))
  }finally {await rm(f.root,{recursive:true,force:true})}
})

test('real FFmpeg preserves silence, tones and boundaries with one AAC encode',{skip:!process.env.AUTOPOC_FFMPEG_INTEGRATION},async()=>{
  const f=await fixture()
  const run=async(command,args,cwd)=>execFileSync(command,args,{cwd,maxBuffer:20*1024*1024}).toString()
  try {
    const t=await loadTimeline(f.path,f.input)
    const segment=join(f.root,'black.mp4')
    await run('ffmpeg',['-v','error','-y','-f','lavfi','-i','color=c=black:s=1280x720:r=30:d=6','-an','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',segment],f.root)
    const result=await muxPresentation(Array(6).fill(segment),t,f.root,run)
    assert.equal(result.width,1280);assert.ok(Math.abs(result.duration_seconds-36)<.25)
    const samples=execFileSync('ffmpeg',['-v','error','-i',join(f.root,'executive-summary.mp4'),'-vn','-f','f32le','-ar','24000','-ac','1','pipe:1'],{maxBuffer:20*1024*1024})
    const rms=(start,end)=>{let sum=0,n=0;for(let k=Math.round(start*24000);k<end*24000;k++){sum+=samples.readFloatLE(k*4)**2;n++}return Math.sqrt(sum/n)}
    assert.ok(rms(.05,.25)<.005);assert.ok(rms(.5,1)>.15);assert.ok(rms(5.8,6.25)<.005);assert.ok(rms(6.5,7)>.15);assert.ok(rms(7.6,7.9)<.005)
    const power=(start,freq)=>{let x=0,y=0;for(let k=0;k<4800;k++){const v=samples.readFloatLE((Math.round(start*24000)+k)*4);x+=v*Math.sin(2*Math.PI*freq*k/24000);y+=v*Math.cos(2*Math.PI*freq*k/24000)}return x*x+y*y}
    assert.ok(power(.5,440)>power(.5,880)*100);assert.ok(power(6.5,880)>power(6.5,440)*100)
    assert.equal(result.subtitle_codec,'mov_text')
    const vtt=execFileSync('ffmpeg',['-v','error','-i',join(f.root,'executive-summary.mp4'),'-map','0:s:0','-f','webvtt','pipe:1'],{maxBuffer:4*1024*1024}).toString()
    const spoken=JSON.parse(await readFile(join(f.input,'narrative.json'))).slides[0].narration[0].text
    assert.ok(vtt.includes(spoken),vtt.slice(0,400))
    // We write HH:MM:SS.mmm; FFmpeg's webvtt muxer re-emits the hour-less form.
    assert.match(vtt,/(?:00:)?00:00\.350 --> (?:00:)?00:01\.350/)
  }finally {await rm(f.root,{recursive:true,force:true})}
})

test('changed WAV retains prepared deck/PDF and explicitly fails narrated video',async()=>{
  const {recordPresentation}=await import('./render.mjs')
  const f=await fixture()
  try {
    const manifest={artifacts:{deck:{status:'validated'},pdf:{status:'validated'}}}
    await writeFile(join(f.root,'presentation-manifest.json'),JSON.stringify(manifest))
    await writeFile(join(f.speech,f.timeline.scenes[0].audio_path),'changed')
    const result=await recordPresentation(f.input,f.root,f.path)
    assert.equal(result.status,'partial');assert.equal(result.artifacts.video.status,'failed')
    assert.equal(result.artifacts.deck.status,'validated');assert.equal(result.artifacts.pdf.status,'validated')
  }finally {await rm(f.root,{recursive:true,force:true})}
})


test('capture trimming uses recorded media duration instead of delayed wall clock',{skip:!process.env.AUTOPOC_FFMPEG_INTEGRATION},async()=>{
  const root=await mkdtemp(join(tmpdir(),'autopoc-capture-'))
  const run=async(command,args,cwd)=>execFileSync(command,args,{cwd,maxBuffer:20*1024*1024}).toString()
  try {
    const raw=join(root,'delayed.webm'),output=join(root,'scene.mp4')
    await run('ffmpeg',['-v','error','-y','-f','lavfi','-i','color=c=blue:s=1280x720:r=25:d=6.96','-c:v','libvpx','-deadline','realtime',raw],root)
    const offset=await encodeCapture(raw,{duration_seconds:184/30,frame_count:184},output,root,run)
    assert.ok(Math.abs(offset-(6.96-184/30))<.05)
    const p=JSON.parse(await run('ffprobe',['-v','error','-show_format','-show_streams','-of','json',output],root))
    assert.equal(Number(p.streams[0].nb_frames),184)
  }finally {await rm(root,{recursive:true,force:true})}
})

test('real variable-frame browser recording retains every fractional scene frame',{skip:!process.env.AUTOPOC_FFMPEG_INTEGRATION},async()=>{
  const root=await mkdtemp(join(tmpdir(),'autopoc-browser-frames-'))
  const run=async(command,args,cwd)=>execFileSync(command,args,{cwd,maxBuffer:20*1024*1024}).toString()
  try {
    const raw=new URL('../tests/fixtures/executive-story/delayed-capture.webm',import.meta.url).pathname
    const output=join(root,'fractional.mp4')
    await encodeCapture(raw,{duration_seconds:181/30,frame_count:181},output,root,run)
    const p=JSON.parse(await run('ffprobe',['-v','error','-show_streams','-of','json',output],root))
    assert.equal(Number(p.streams[0].nb_frames),181)
  }finally {await rm(root,{recursive:true,force:true})}
})
