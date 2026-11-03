/** Trusted Slidev builder and silent-video recorder. Narrative is JSON, never code. */
import { cp, mkdir, readFile, writeFile, symlink, stat } from 'node:fs/promises'
import { createServer } from 'node:http'
import { dirname, extname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'
import { createHash } from 'node:crypto'

const here = dirname(fileURLToPath(import.meta.url))
const topics = ['purpose', 'testing_strategy', 'test_execution', 'platform_suitability']
const slideKinds = ['purpose', 'testing_strategy', 'topology', 'test_execution', 'results', 'platform_suitability']

export async function prepareDeck(input, output) {
  const narrative = JSON.parse(await readFile(join(input, 'narrative.json'), 'utf8'))
  const scenes = JSON.parse(await readFile(join(input, 'scenes.json'), 'utf8'))
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
  await mkdir(output, { recursive: true })
  for (const name of ['components', 'vendor', 'package.json', 'package-lock.json', 'style.css'])
    await cp(join(here, name), join(output, name), { recursive: true })
  await writeFile(join(output, 'narrative.json'), JSON.stringify(narrative, null, 2))
  await writeFile(join(output, 'scenes.json'), JSON.stringify(scenes, null, 2))
  const slides = `---\ntheme: default\ntitle: AutoPoC executive summary\ncanvasWidth: 1280\naspectRatio: 16/9\ndownload: false\ntransition: none\nwakeLock: false\nfonts:\n  provider: none\n  sans: Arial\n  mono: monospace\n---\n\n`
    + slideKinds.map((kind, i) => `${i ? '---\nlayout: default\n---\n\n' : ''}<ExecutiveSlide kind="${kind}" />\n\n<!-- Explain archived evidence; animation timing is illustrative. See narrative.json for claim references. -->\n`).join('\n')
  await writeFile(join(output, 'slides.md'), slides)
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

async function serve(root) {
  const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.otf': 'font/otf', '.woff2': 'font/woff2' }
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

export async function render(input, output) {
  const deck = join(output, 'source')
  const { narrative, scenes } = await prepareDeck(input, deck)
  const modules = resolve(process.env.AUTOPOC_RENDER_NODE_MODULES || join(here, 'node_modules'))
  await symlink(modules, join(deck, 'node_modules'), 'dir')
  const cli = join(modules, '@slidev/cli/bin/slidev.mjs')
  const manifest = { schema_version: 1, run_id: narrative.run_id, status: 'partial', scenes: [], artifacts: {} }
  const save = () => writeFile(join(output, 'presentation-manifest.json'), JSON.stringify(manifest, null, 2))
  await run(process.execPath, [cli, 'build', 'slides.md', '--out', 'dist'], deck)
  manifest.artifacts.deck = { status: 'validated', path: 'source/dist' }
  await save()
  // Export/record independently: a failed video does not discard the deck or PDF.
  try {
    await run(process.execPath, [cli, 'export', 'slides.md', '--output', join(resolve(output), 'executive-summary.pdf'), '--timeout', '60000', ...(process.env.AUTOPOC_CHROMIUM_EXECUTABLE ? ['--executable-path', process.env.AUTOPOC_CHROMIUM_EXECUTABLE] : [])], deck)
    manifest.artifacts.pdf = { status: 'validated', path: 'executive-summary.pdf' }
  } catch (error) { console.error('PDF export:', error.stack || error.message); manifest.artifacts.pdf = { status: 'failed', error: 'PDF export failed' } }
  await save()
  const { chromium } = await import(join(modules, 'playwright-chromium/index.mjs'))
  const { server, url } = await serve(join(deck, 'dist'))
  let browser
  try {
    browser = await chromium.launch({ headless: true, executablePath: process.env.AUTOPOC_CHROMIUM_EXECUTABLE || undefined, args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] })
    const segments = []
    await mkdir(join(output, 'frames'), { recursive: true })
    for (let i = 0; i < 6; i++) {
      const context = await browser.newContext({ viewport: { width: 1280, height: 720 }, recordVideo: { dir: join(output, 'capture'), size: { width: 1280, height: 720 } } })
      await context.route('**/*', route => route.request().url().startsWith(url + '/') ? route.continue() : route.abort())
      const page = await context.newPage()
      const pageErrors = []
      page.on('pageerror', e => pageErrors.push(e.message))
      try {
        await page.goto(`${url}/${i+1}?embedded`, { waitUntil: 'networkidle', timeout: 30000 })
        await page.locator('[data-executive-ready="true"]').waitFor({ timeout: 30000 })
        const fatal = await page.locator('.tl-fatal').allTextContents()
        if (fatal.length || pageErrors.length) {
          // The deck and the PDF embed this same component and data, so the
          // defect is in the content, not in the video pipeline.
          const error = new Error('Scene initialization failed: ' + JSON.stringify({ slide:i+1, pageErrors, fatal }))
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
        manifest.scenes.push({ id: slideKinds[i], duration_seconds: scenes.durations[i], capture_offset: trimStart, ready: true })
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

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (process.argv.length !== 4) { console.error('Usage: node render.mjs INPUT_DIR OUTPUT_DIR'); process.exit(2) }
  try { const result = await render(resolve(process.argv[2]), resolve(process.argv[3])); console.log(JSON.stringify(result)); if (result.status === 'partial') process.exitCode = 1 }
  catch (error) { console.error(error.stack || error.message || 'Presentation generation failed'); process.exitCode = 1 }
}
