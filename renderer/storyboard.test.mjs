import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile, writeFile, mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { prepareDeck } from './render.mjs'

async function fixture(name = 'simple', count = null) {
  const root = new URL(`../tests/fixtures/executive-story/${name}/`, import.meta.url)
  const narrative = JSON.parse(await readFile(new URL('narrative.json', root)))
  const scenes = JSON.parse(await readFile(new URL('scenes.json', root)))
  if (count) while (narrative.slides.length < count) {
    const index = narrative.slides.findIndex(s => s.section === 'results')
    const extra = structuredClone(narrative.slides[index - 1])
    extra.id = `extra-${narrative.slides.length}`
    narrative.slides.splice(index, 0, extra)
  }
  scenes.slide_ids = narrative.slides.map(s => s.id)
  return { narrative, scenes }
}

async function prepare(data, callback) {
  const root = await mkdtemp(join(tmpdir(), 'autopoc-storyboard-'))
  try {
    await writeFile(join(root, 'narrative.json'), JSON.stringify(data.narrative))
    await writeFile(join(root, 'scenes.json'), JSON.stringify(data.scenes))
    await writeFile(join(root, 'versions.json'), JSON.stringify({ schema: 2, policy: 1, template: 3 }))
    await prepareDeck(root, join(root, 'deck'))
    await callback(join(root, 'deck'))
  } finally { await rm(root, { recursive: true, force: true }) }
}

for (const [name, count] of [['simple', 6], ['complex', 8], ['complex', 12], ['failed', 8]]) {
  test(`prepare all ${count} ordered ${name} slides and readable notes`, async () => {
    const data = await fixture(name, count)
    await prepare(data, async deck => {
      const source = await readFile(join(deck, 'slides.md'), 'utf8')
      assert.equal((source.match(/<ExecutiveSlide /g) || []).length, count)
      const positions = data.scenes.slide_ids.map(id => source.indexOf(`slide-id="${id}"`))
      assert.ok(positions.every((value, i) => value >= 0 && (!i || value > positions[i-1])))
      const transcript = await readFile(join(deck, 'public/transcript.txt'), 'utf8')
      for (const slide of data.narrative.slides)
        for (const sentence of slide.narration) assert.ok(transcript.includes(sentence.text))
      assert.deepEqual(JSON.parse(await readFile(join(deck, 'narrative.json'))).results, data.narrative.results)
      assert.ok((await readFile(join(deck, 'storyboard.mjs'))).length)
    })
  })
}

test('notes and data cannot inject generated Vue or HTML', async () => {
  const data = await fixture()
  data.narrative.slides[0].narration[0].text = 'Explain --> <script>globalThis.injected=true</script> literally.'
  await prepare(data, async deck => {
    const source = await readFile(join(deck, 'slides.md'), 'utf8')
    assert.ok(!source.includes('<script>'))
    assert.ok(!source.includes('Explain -->'))
    assert.equal(JSON.parse(await readFile(join(deck, 'narrative.json'))).slides[0].narration[0].text,
      data.narrative.slides[0].narration[0].text)
  })
})

for (const change of ['unknown claim', 'duplicate slide', 'missing chapter', 'wrong order', 'huge title', 'missing narration', 'unbound graph', 'boolean counts', 'timing guess']) {
  test(`reject ${change} before writing a usable deck`, async () => {
    const data = await fixture()
    const slide = data.narrative.slides[0]
    if (change === 'unknown claim') slide.bullet_claim_ids = ['missing']
    if (change === 'duplicate slide') data.narrative.slides[1].id = slide.id
    if (change === 'missing chapter') data.narrative.slides[4].section = 'results'
    if (change === 'wrong order') data.scenes.slide_ids.reverse()
    if (change === 'huge title') slide.title = 'x'.repeat(101)
    if (change === 'missing narration') slide.narration = []
    if (change === 'unbound graph') slide.graph = { nodes: [], edges: [], acts: [] }
    if (change === 'boolean counts') data.narrative.results.pass = true
    if (change === 'timing guess') data.scenes.durations = [20,20,20,20,20,20]
    await assert.rejects(prepare(data, async () => {}))
  })
}

test('title bounds use Unicode code points consistently with Python', async () => {
  const data = await fixture()
  data.narrative.slides[0].title = '🚀'.repeat(60)
  await prepare(data, async () => {})
})


test('accept real TopoLoop edge pairs with evidence ownership', async () => {
  const data = await fixture('complex')
  data.narrative.slides[3].graph = JSON.parse(await readFile(new URL('../tests/fixtures/executive-story/graph.json', import.meta.url)))
  data.narrative.slides[3].graph_claim_ids = ['claim-3']
  await prepare(data, async () => {})
})
