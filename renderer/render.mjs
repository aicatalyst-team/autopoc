/** Trusted Slidev builder and silent-video recorder. Narrative is JSON, never code. */
import { cp, mkdir, readFile, writeFile, symlink, stat } from 'node:fs/promises'
import { createServer } from 'node:http'
import { dirname, extname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'
import { createHash } from 'node:crypto'
import { verifyBrandAssets } from './branding.mjs'
import { loadTimeline, muxPresentation, encodeCapture } from './audio.mjs'
import { validateStoryboard, speakerNotes, transcript } from './storyboard.mjs'
import { inspectScene, sceneProblems, sceneCheckTimes } from './scene-validation.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const topics = ['purpose', 'testing_strategy', 'test_execution', 'platform_suitability']
const slideKinds = ['purpose', 'testing_strategy', 'topology', 'test_execution', 'results', 'platform_suitability']

export async function prepareDeck(input, output) {
  const versions = JSON.parse(await readFile(join(input, 'versions.json'), 'utf8'))
  if (![2,3].includes(versions.template)) throw new Error('This renderer requires template revision 2 or 3; use the original image for legacy inputs')
  const narrative = JSON.parse(await readFile(join(input, 'narrative.json'), 'utf8'))
  const scenes = JSON.parse(await readFile(join(input, 'scenes.json'), 'utf8'))
  if (versions.template === 3) validateStoryboard(narrative, scenes)
  else {
    if (narrative.schema_version !== 1 || typeof narrative.run_id !== 'string'
        || typeof narrative.project_name !== 'string' || narrative.project_name.length > 100)
      throw new Error('Unsupported narrative identity')
    for (const topic of topics) {
      if (!Array.isArray(narrative[topic]) || narrative[topic].length < 1 || narrative[topic].length > 4)
        throw new Error('All four executive topics require bounded claims')
      for (const claim of narrative[topic]) {
        if (typeof claim.text !== 'string' || claim.text.length > 280 || !claim.text.trim()
            || !Array.isArray(claim.sources) || !claim.sources.length
            || claim.sources.some(s => typeof s !== 'string' || s.length > 240))
          throw new Error('Each claim needs bounded text and evidence references')
      }
    }
    if (!Array.isArray(narrative.limitations) || narrative.limitations.length > 5
        || narrative.limitations.some(t => typeof t !== 'string' || t.length > 200))
      throw new Error('Expected concise limitations')
    if (!['pass','fail','error','skip','incomplete'].every(k => Number.isSafeInteger(narrative.results?.[k]) && narrative.results[k] >= 0))
      throw new Error('Expected validated scenario totals')
    if (scenes.durations?.length !== 6 || scenes.durations.some(n => !Number.isFinite(n) || n < 1 || n > 60)
        || scenes.durations.reduce((a,b) => a+b,0) > 180)
      throw new Error('Expected six scene durations totaling at most 180 seconds')
    for (const topology of [narrative.topology, narrative.scenario_flow]) if (topology != null) {
      if (!Array.isArray(topology.nodes) || topology.nodes.length > 12 || !Array.isArray(topology.edges)
          || topology.edges.length > 20 || !Array.isArray(topology.acts) || topology.acts.length > 5)
        throw new Error('Topology exceeds executive graph limits')
      // TopoLoop performs the graph/path validation; publication also requires a reviewed input package.
    }
    if (narrative.scenario_flow && (narrative.test_execution.length > 2 || narrative.test_execution.reduce((n,c) => n+c.text.length,0) > 300))
      throw new Error('Execution explanation must fit alongside the scenario animation')
  }
  await verifyBrandAssets(join(here, 'assets/redhat'))
  await mkdir(output, { recursive: true })
  for (const name of ['components', 'vendor', 'package.json', 'package-lock.json', 'style.css'])
    await cp(join(here, name), join(output, name), { recursive: true })
  for (const name of ['assets', 'branding.mjs', 'scene-validation.mjs', 'storyboard.mjs'])
    await cp(join(here, name), join(output, name), { recursive: true })
  await cp(join(here, 'assets/redhat'), join(output, 'public/brand'), { recursive: true })
  await writeFile(join(output, 'versions.json'), JSON.stringify(versions, null, 2))
  await writeFile(join(output, 'narrative.json'), JSON.stringify(narrative, null, 2))
  await writeFile(join(output, 'scenes.json'), JSON.stringify(scenes, null, 2))
  const slides = `---\ntheme: default\ntitle: AutoPoC executive summary\nfavicon: /brand/logos/redhat-hat-standard.svg\ncanvasWidth: 1280\naspectRatio: 16/9\ndownload: false\ntransition: none\nwakeLock: false\nfonts:\n  provider: none\n  sans: Red Hat Text\n  mono: Red Hat Mono\n---\n\n`
    + (versions.template === 3
      ? narrative.slides.map((slide, i) => `${i ? '---\nlayout: default\n---\n\n' : ''}<ExecutiveSlide slide-id="${slide.id}" />\n\n<!--\n${speakerNotes(slide)}\n-->\n`).join('\n')
      : slideKinds.map((kind, i) => `${i ? '---\nlayout: default\n---\n\n' : ''}<ExecutiveSlide kind="${kind}" />\n\n<!-- Explain archived evidence; animation timing is illustrative. See narrative.json for claim references. -->\n`).join('\n'))
  await writeFile(join(output, 'slides.md'), slides)
  if (versions.template === 3) {
    await writeFile(join(output, 'transcript.txt'), transcript(narrative))
    await writeFile(join(output, 'public/transcript.txt'), transcript(narrative))
  }
  return { narrative, scenes }
}

/** Mark what a capture failure actually invalidated. A broken scene is broken
 *  in the deck and the PDF too; a video-pipeline failure leaves them usable. */
export function failedArtifacts(manifest, error) {
  manifest.artifacts.video = { status: 'failed', error: 'Video recording or validation failed' }
  if (error?.contentFailure)
    for (const kind of ['deck', 'pdf'])
      if (manifest.artifacts[kind])
        manifest.artifacts[kind] = { status: 'failed', error: 'Scene content failed to initialize' }
  return manifest
}

function run(command, args, cwd, timeout = 120000) {
  return new Promise((accept, reject) => {
    const child = spawn(command, args, { cwd, stdio: ['ignore', 'pipe', 'pipe'] })
    let text = ''
    const timer = setTimeout(() => { child.kill('SIGKILL'); reject(new Error('Renderer command timed out')) }, timeout)
    for (const stream of [child.stdout, child.stderr]) stream.on('data', d => { if (text.length < 100000) text += d })
    child.on('error', error => { clearTimeout(timer); reject(error) })
    child.on('exit', code => { clearTimeout(timer); code === 0 ? accept(text) : reject(new Error(`Renderer command failed (${code}): ${text.slice(-2000)}`)) })
  })
}

export async function serve(root) {
  const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.otf': 'font/otf', '.woff2': 'font/woff2' }
  const server = createServer(async (request, response) => {
    try {
      const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname)
      const target = resolve(root, '.' + pathname)
      if (!target.startsWith(resolve(root) + '/')) throw new Error('Invalid path')
      const file = await stat(target).then(s => s.isFile() ? target : join(root, 'index.html')).catch(() => join(root, 'index.html'))
      response.setHeader('Content-Type', mime[extname(file)] || 'application/octet-stream')
      response.end(await readFile(file))
    } catch { response.statusCode = 404; response.end() }
  })
  await new Promise(accept => server.listen(0, '127.0.0.1', accept))
  return { server, url: `http://127.0.0.1:${server.address().port}` }
}

export async function render(input, output, { prepareOnly = false } = {}) {
  const deck = join(output, 'source')
  const { narrative, scenes } = await prepareDeck(input, deck)
  const descriptors = narrative.schema_version === 2 ? narrative.slides.map(s => ({ id:s.id, graph:s.graph })) : slideKinds.map((id, i) => ({ id, graph:i === 2 ? narrative.topology : i === 3 ? narrative.scenario_flow : null }))
  const modules = resolve(process.env.AUTOPOC_RENDER_NODE_MODULES || join(here, 'node_modules'))
  await symlink(modules, join(deck, 'node_modules'), 'dir')
  const cli = join(modules, '@slidev/cli/bin/slidev.mjs')
  const manifest = { schema_version: 1, run_id: narrative.run_id, status: 'partial', scenes: [], artifacts: {} }
  const save = () => writeFile(join(output, 'presentation-manifest.json'), JSON.stringify(manifest, null, 2))
  await run(process.execPath, [cli, 'build', 'slides.md', '--out', 'dist'], deck)
  manifest.artifacts.deck = { status: 'pending', path: 'source/dist' }
  await save()
  const { chromium } = await import(join(modules, 'playwright-chromium/index.mjs'))
  const { server, url } = await serve(join(deck, 'dist'))
  let browser
  try {
    browser = await chromium.launch({ headless: true, executablePath: process.env.AUTOPOC_CHROMIUM_EXECUTABLE || undefined, args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] })
    // Every scene must be readable and fully branded before any PDF is exported.
    for (let i = 0; i < descriptors.length; i++) {
      const context = await browser.newContext({ viewport: { width: 1280, height: 720 } })
      await context.route('**/*', route => route.request().url().startsWith(url + '/') ? route.continue() : route.abort())
      const page = await context.newPage()
      const errors = []
      page.on('pageerror', e => errors.push(e.message))
      try {
        await page.goto(`${url}/${i+1}?embedded`, { waitUntil: 'networkidle', timeout: 30000 })
        await page.locator('[data-executive-ready="true"]').waitFor({ timeout: 30000 })
        const problems = [...errors, ...await page.locator('.tl-fatal').allTextContents(), ...sceneProblems(await page.evaluate(inspectScene))]
        if (problems.length) {
          const error = new Error(`Scene ${i+1} content validation failed: ${problems.join('; ')}`)
          error.contentFailure = true
          throw error
        }
        const graph = descriptors[i].graph
        for (const time of sceneCheckTimes(graph)) {
          await page.evaluate(time => window.dispatchEvent(new CustomEvent('executive-still', { detail: time })), time)
          await page.locator('[data-executive-ready="true"]').waitFor({ timeout: 30000 })
          const timedProblems = [...errors, ...await page.locator('.tl-fatal').allTextContents(), ...sceneProblems(await page.evaluate(inspectScene))]
          if (timedProblems.length) {
            const error = new Error(`Scene ${i+1} at ${time}s failed validation: ${timedProblems.join('; ')}`)
            error.contentFailure = true
            throw error
          }
        }
      } finally { await context.close() }
    }
    manifest.artifacts.deck.status = 'validated'
    // Export/record independently: an encoding failure does not discard PDF/deck.
    try {
      await run(process.execPath, [cli, 'export', 'slides.md', '--output', join(resolve(output), 'executive-summary.pdf'), '--timeout', '60000', ...(process.env.AUTOPOC_CHROMIUM_EXECUTABLE ? ['--executable-path', process.env.AUTOPOC_CHROMIUM_EXECUTABLE] : [])], deck)
      manifest.artifacts.pdf = { status: 'validated', path: 'executive-summary.pdf' }
    } catch (error) { console.error('PDF export:', error.stack || error.message); manifest.artifacts.pdf = { status: 'failed', error: 'PDF export failed' } }
    await save()
    if (!prepareOnly) {
      if (narrative.schema_version === 2) throw new Error('Narrated inputs require prepare, speech and record stages')
      const segments = []
      await mkdir(join(output, 'frames'), { recursive: true })
      for (let i = 0; i < descriptors.length; i++) {
        const context = await browser.newContext({ viewport: { width: 1280, height: 720 }, recordVideo: { dir: join(output, 'capture'), size: { width: 1280, height: 720 } } })
        await context.route('**/*', route => route.request().url().startsWith(url + '/') ? route.continue() : route.abort())
        const page = await context.newPage()
        const pageErrors = []
        page.on('pageerror', e => pageErrors.push(e.message))
        try {
          await page.goto(`${url}/${i+1}?embedded`, { waitUntil: 'networkidle', timeout: 30000 })
          await page.locator('[data-executive-ready="true"]').waitFor({ timeout: 30000 })
          const fatal = await page.locator('.tl-fatal').allTextContents()
          const problems = sceneProblems(await page.evaluate(inspectScene))
          if (fatal.length || pageErrors.length || problems.length) {
            // The deck and the PDF embed this same component and data, so the
            // defect is in the content, not in the video pipeline.
            const error = new Error('Scene initialization failed: ' + JSON.stringify({ slide:i+1, pageErrors, fatal, problems }))
            error.contentFailure = true
            throw error
          }
          await page.evaluate(() => window.dispatchEvent(new Event('executive-reset')))
          await page.locator('[data-executive-ready="true"]').waitFor({ timeout: 30000 })
          await page.screenshot({ path: join(output, 'frames', `${i+1}.png`) })
          const start = performance.now()
          await page.waitForTimeout(scenes.durations[i] * 1000)
          const elapsed = (performance.now() - start) / 1000
          const video = page.video()
          await context.close()
          const raw = await video.path()
          // Trim from the end: pre-readiness loading belongs outside the scene interval.
          const probe = JSON.parse(await run('ffprobe', ['-v','error','-show_format','-of','json',raw], output))
          const trimStart = Math.max(0, Number(probe.format.duration) - elapsed)
          const segment = join(resolve(output), `scene-${i+1}.mp4`)
          await run('ffmpeg', ['-y','-ss',String(trimStart),'-i',raw,'-t',String(scenes.durations[i]),'-an','-r','30','-c:v','libx264','-pix_fmt','yuv420p',segment], output)
          segments.push(segment)
          manifest.scenes.push({ id: descriptors[i].id, duration_seconds: scenes.durations[i], capture_offset: trimStart, ready: true })
        } finally { await context.close() }
      }
      await writeFile(join(output, 'concat.txt'), segments.map(p => `file '${p.replaceAll("'", "'\\''")}'`).join('\n'))
      await run('ffmpeg', ['-y','-f','concat','-safe','0','-i','concat.txt','-c','copy','-movflags','+faststart','executive-summary.mp4'], output)
      const probe = JSON.parse(await run('ffprobe', ['-v','error','-show_format','-show_streams','-of','json','executive-summary.mp4'], output))
      const video = probe.streams.find(s => s.codec_type === 'video')
      const expected = scenes.durations.reduce((a,b) => a+b,0)
      if (!video || video.width !== 1280 || video.height !== 720 || video.codec_name !== 'h264' || video.pix_fmt !== 'yuv420p'
          || Math.abs(Number(probe.format.duration)-expected) > 1 || !(Number(video.nb_frames) > 0)) throw new Error('Invalid video format/duration')
      manifest.artifacts.video = { status: 'validated', path: 'executive-summary.mp4', duration_seconds: Number(probe.format.duration), width:1280, height:720, fps:video.avg_frame_rate }
    }
  } catch (error) {
    failedArtifacts(manifest, error)
    console.error(error.message)
  } finally { await browser?.close(); await new Promise(accept => server.close(accept)) }
  for (const artifact of Object.values(manifest.artifacts)) if (artifact.status === 'validated' && artifact.path !== 'source/dist') {
    const data = await readFile(join(output, artifact.path))
    artifact.sha256 = createHash('sha256').update(data).digest('hex'); artifact.size = data.length
  }
  manifest.status = Object.values(manifest.artifacts).every(a => a.status === 'validated') ? 'generated_unpublished' : 'partial'
  await save()
  return manifest
}

export async function recordPresentation(input, output, timelinePath) {
  const path = join(output, 'presentation-manifest.json')
  const manifest = JSON.parse(await readFile(path))
  const save = () => writeFile(path, JSON.stringify(manifest, null, 2))
  let browser, server
  try {
    if (manifest.artifacts.deck?.status !== 'validated') throw new Error('Recording requires the validated prepared deck')
    const narrative = JSON.parse(await readFile(join(input, 'narrative.json')))
    const timeline = await loadTimeline(timelinePath, input)
    const modules = resolve(process.env.AUTOPOC_RENDER_NODE_MODULES || join(here, 'node_modules'))
    const { chromium } = await import(join(modules, 'playwright-chromium/index.mjs'))
    const hosted = await serve(join(output, 'source/dist')); server = hosted.server
    const url = hosted.url
    browser = await chromium.launch({ headless:true, executablePath:process.env.AUTOPOC_CHROMIUM_EXECUTABLE || undefined, args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'] })
    const segments = []
    manifest.scenes = []
    for (const [i,scene] of timeline.scenes.entries()) {
      const capture = join(output, `capture-${i+1}`)
      const context = await browser.newContext({ viewport:{width:1280,height:720}, recordVideo:{dir:capture,size:{width:1280,height:720}} })
      await context.route('**/*', route => route.request().url().startsWith(url + '/') ? route.continue() : route.abort())
      const page = await context.newPage(), errors=[]
      page.on('pageerror', e => errors.push(e.message))
      let raw, offset
      try {
        await page.goto(`${url}/${i+1}?embedded`, {waitUntil:'networkidle',timeout:30000})
        await page.locator('[data-executive-ready="true"]').waitFor({timeout:30000})
        await page.evaluate(duration => window.dispatchEvent(new CustomEvent('executive-duration',{detail:duration})),scene.duration_seconds)
        await page.evaluate(() => window.dispatchEvent(new CustomEvent('executive-reset')))
        await page.locator('[data-executive-ready="true"]').waitFor({timeout:30000})
        const problems=[...errors,...await page.locator('.tl-fatal').allTextContents(),...sceneProblems(await page.evaluate(inspectScene))]
        if(problems.length) { const failure=new Error(`Scene ${scene.id}: ${problems.join('; ')}`);failure.contentFailure=true;throw failure }
        await page.waitForTimeout(scene.duration_seconds*1000+150)
        if(errors.length || (await page.locator('.tl-fatal').count())) {const failure=new Error('Scene failed during recording');failure.contentFailure=true;throw failure}
        raw=await page.video().path()
      } finally { await context.close() }
      const segment=join(resolve(output),`scene-${i+1}.mp4`)
      offset=await encodeCapture(raw,scene,segment,output,run)
      segments.push(segment)
      manifest.scenes.push({id:scene.id,duration_seconds:scene.duration_seconds,frame_count:scene.frame_count,capture_offset:offset,ready:true,graph:!!narrative.slides[i].graph})
      await save()
    }
    await browser.close(); browser=null
    manifest.artifacts.video=await muxPresentation(segments,timeline,output,run)
    manifest.narration={...timeline.narration,model_revision:timeline.model_revision,duration_seconds:timeline.duration_seconds,timeline_sha256:createHash('sha256').update(await readFile(timelinePath)).digest('hex')}
  } catch (error) { failedArtifacts(manifest,error); console.error(error.stack || error.message) }
  finally { await browser?.close(); if(server) await new Promise(accept=>server.close(accept)) }
  manifest.status=Object.values(manifest.artifacts).every(a=>a.status==='validated') ? 'generated_unpublished' : 'partial'
  await save();return manifest
}

export async function preparePresentation(input, output) { return render(input, output, { prepareOnly: true }) }

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args=process.argv.slice(2)
  const stage=args[3]
  if (!(args.length===2 || (args.length===4 && args[2]==='--stage' && stage==='prepare') || (args.length===6 && args[2]==='--stage' && stage==='record' && args[4]==='--timeline'))) {
    console.error('Usage: node render.mjs INPUT OUTPUT [--stage prepare|record --timeline PATH]'); process.exit(2)
  }
  try {
    const result=stage==='record' ? await recordPresentation(resolve(args[0]),resolve(args[1]),resolve(args[5])) : await render(resolve(args[0]),resolve(args[1]),{prepareOnly:stage==='prepare'})
    console.log(JSON.stringify(result)); if(result.status==='partial') process.exitCode=1
  } catch(error) {console.error(error.stack || error.message);process.exitCode=1}
}
