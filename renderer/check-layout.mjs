/** Real-browser acceptance for an already built, offline branded deck.
 * Usage: AUTOPOC_RENDER_NODE_MODULES=... node check-layout.mjs DIST SCREENSHOTS
 */
import assert from 'node:assert/strict'
import { mkdir, writeFile, readFile } from 'node:fs/promises'
import { join, resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { serve } from './render.mjs'
import { inspectScene, sceneProblems } from './scene-validation.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const modules = resolve(process.env.AUTOPOC_RENDER_NODE_MODULES || join(here, 'node_modules'))
const { chromium } = await import(join(modules, 'playwright-chromium/index.mjs'))
const output = resolve(process.argv[3])
await mkdir(output, { recursive: true })
const { server, url } = await serve(resolve(process.argv[2]))
let browser
const narrative = JSON.parse(await readFile(join(resolve(process.argv[2]), '../narrative.json')))
const results = { scenes: [], checks: [], externalRequests: [] }
try {
  browser = await chromium.launch({ headless: true, executablePath: process.env.AUTOPOC_CHROMIUM_EXECUTABLE || undefined,
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] })
  const contextFor = async (block = '') => {
    const context = await browser.newContext({ viewport: { width: 1280, height: 720 } })
    await context.route('**/*', route => {
      const request = route.request().url()
      if (!request.startsWith(url + '/')) { results.externalRequests.push(request); return route.abort() }
      return block && request.includes(block) ? route.abort() : route.continue()
    })
    return context
  }
  const open = async (context, slide = 1) => {
    const page = await context.newPage()
    page.on('pageerror', error => { throw error })
    await page.goto(`${url}/${slide}?embedded`, { waitUntil: 'networkidle' })
    await page.locator('[data-executive-ready="true"]').waitFor()
    return page
  }
  const context = await contextFor()
  const first = await open(context)
  const count = (await first.evaluate(inspectScene)).count
  await first.close()
  assert.ok(Number.isInteger(count) && count >= 6 && count <= 30)
  for (let i = 1; i <= count; i++) {
    const page = await open(context, i)
    const snapshot = await page.evaluate(inspectScene)
    assert.deepEqual(sceneProblems(snapshot), [], `Scene ${i}`)
    assert.deepEqual(await page.locator('.tl-fatal').allTextContents(), [])
    const root = page.locator('.executive[data-executive-ready="true"]')
    assert.equal(await root.locator('.slide-number').textContent(), String(i))
    if ([2,3].includes(narrative.schema_version)) {
      const slide = narrative.slides[i-1]
      assert.equal(snapshot.id, slide.id)
      assert.equal(await root.locator('h1').textContent(), slide.title)
      const text = await root.innerText()
      for (const id of slide.bullet_claim_ids) assert.ok(text.includes(narrative.claims.find(c => c.id === id).text))
      if (await root.locator('.results').count())
        for (const [status, count] of Object.entries(narrative.results)) assert.equal(await root.locator(`.results .${status} strong`).textContent(), String(count))
    }
    await page.screenshot({ path: join(output, `slide-${i}.png`) })
    results.scenes.push({ slide: i, snapshot })
    await page.close()
  }
  const page = await open(context)
  await page.locator('.executive[data-executive-ready="true"]').locator('.claims li, .project-definition').first().evaluate(el => { el.firstChild.textContent = 'Oversized claim '.repeat(600) })
  assert.ok(sceneProblems(await page.evaluate(inspectScene)).some(p => p.includes('shorten')))
  results.checks.push('oversized claim refused')
  await page.reload({ waitUntil: 'networkidle' }); await page.locator('[data-executive-ready="true"]').waitFor()
  await page.locator('.executive[data-executive-ready="true"] h1').evaluate(el => { el.textContent = 'Very long project title '.repeat(60) })
  assert.ok(sceneProblems(await page.evaluate(inspectScene)).some(p => p.includes('slide title')))
  results.checks.push('oversized title refused')
  const counters = await open(context, results.scenes.find(s => s.snapshot.section === 'results').slide)
  await counters.locator('.executive[data-executive-ready="true"] .results strong').first().evaluate(el => { el.textContent = '9'.repeat(20) })
  assert.ok(sceneProblems(await counters.evaluate(inspectScene)).some(p => p.includes('result ')))
  results.checks.push('oversized result count refused')
  const graphPage = results.scenes.find(s => s.snapshot.hasGraph)
  const diagram = await open(context, graphPage?.slide || 1)
  const labels = diagram.locator('.executive[data-executive-ready="true"] .tl-node.on .tl-node-t')
  if (await labels.count()) {
    await labels.last().evaluate(el => { el.textContent = 'An extremely long evidence based component name '.repeat(8) })
    assert.ok(sceneProblems(await diagram.evaluate(inspectScene)).some(p => p.includes('diagram')))
    results.checks.push('oversized diagram label refused')
    await diagram.reload({ waitUntil:'networkidle' }); await diagram.locator('[data-executive-ready="true"]').waitFor()
    // Lay a plain element exactly over a lit label rather than moving the nodes:
    // CSS2DRenderer rewrites the transform of the nodes it owns every frame, and a
    // slide with a single lit node has nothing to move onto anything else.
    const overlaid = await diagram.evaluate(() => {
      const label = document.querySelector('.executive[data-executive-ready="true"] .tl-node.on .tl-node-t')
      const stage = label?.closest('.topology-stage')
      if (!stage) return false
      const clone = document.createElement('div')
      clone.className = 'tl-node-t'
      clone.textContent = label.textContent.trim() || 'overlapping label'
      clone.style.cssText = 'position:absolute;left:0;top:0;opacity:1;visibility:visible;pointer-events:none'
      stage.appendChild(clone)
      // Translate by the measured delta so placement does not depend on which
      // ancestor turns out to be the containing block.
      const target = label.getBoundingClientRect(), placed = clone.getBoundingClientRect()
      clone.style.transform = `translate(${target.left - placed.left}px, ${target.top - placed.top}px)`
      return true
    })
    assert.ok(overlaid, 'No lit topology label was available to overlap')
    assert.ok(sceneProblems(await diagram.evaluate(inspectScene)).some(p => p.includes('overlaps')))
    results.checks.push('overlapping node labels refused')
  }
  await context.close()
  for (const [block, key] of [['/fonts/RedHatText-Regular.woff2', 'missingFonts'], ['/logos/redhat-logo-standard.svg', 'missingImages']]) {
    const missing = await contextFor(block)
    const page = await open(missing)
    const snapshot = await page.evaluate(inspectScene)
    assert.ok(snapshot[key].length || snapshot.errors.length, `${key} was silently accepted: ${JSON.stringify(snapshot)}`)
    results.checks.push(`${key} refused`)
    await missing.close()
  }
  assert.deepEqual(results.externalRequests, [], 'Deck attempted external asset requests')
  results.checks.push('all assets served offline')
  await writeFile(join(output, 'layout-check.json'), JSON.stringify(results, null, 2))
  console.log(JSON.stringify({ scenes: results.scenes.length, checks: results.checks }))
} finally { await browser?.close(); await new Promise(accept => server.close(accept)) }
