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

for (const change of ['unknown claim', 'duplicate slide', 'missing chapter', 'wrong order', 'huge title', 'missing narration', 'unbound graph', 'boolean counts', 'timing guess', 'engine markup', 'bad lexicon identity']) {
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
    if (change === 'engine markup') slide.narration[0].text = 'Pushed to [Quay](/kˈi/) today.'
    if (change === 'bad lexicon identity') data.scenes.narration.lexicon_sha256 = 'not-a-digest'
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

test('result counters render in outcome order, not JSON key order', async () => {
  const { resultOrder } = await import('./storyboard.mjs')
  const data = await fixture()
  assert.deepEqual(resultOrder, ['pass', 'fail', 'error', 'skip', 'incomplete'])
  // Authored narratives serialize alphabetically; the deck must not inherit it.
  assert.notDeepEqual(Object.keys(data.narrative.results).sort(), resultOrder)
  assert.deepEqual([...resultOrder].sort(), Object.keys(data.narrative.results).sort())
  const vue = await readFile(new URL('./components/ExecutiveSlide.vue', import.meta.url), 'utf8')
  assert.match(vue, /v-for="status in resultOrder"/)
  assert.doesNotMatch(vue, /v-for="\(value, status\) in narrative\.results"/)
})

const genericCases = JSON.parse(await readFile(new URL('../tests/fixtures/executive-story/schema3-cases.json', import.meta.url)))
const { validateStoryboard } = await import('./storyboard.mjs')
for (const item of genericCases) test(`schema3 ${item.name} identity and complete paginated checks`, () => {
  assert.equal(validateStoryboard(item.narrative, item.plan).length, item.narrative.slides.length)
})
for (const [name, mutate] of Object.entries({
  missingContext: n => delete n.project_context,
  missingOptional: n => delete n.project_context.homepage_url,
  credentials: n => n.project_context.repository_url = 'https://user:secret@git.example/repo',
  insecure: n => n.project_context.documentation_url = 'http://example.org/docs',
  revision: n => n.project_context.revision = '',
  definition: n => n.project_context.definition_claim_id = 'missing',
  invisible: n => { n.slides[0].bullet_claim_ids = ['claim-1']; n.slides[0].title_claim_ids = ['claim-1'] },
  opening: n => n.slides[0].layout = 'summary',
  missingLayout: n => delete n.slides[1].layout,
  unknownLayout: n => n.slides[1].layout = 'gallery',
  missingVisual: n => delete n.slides[0].visual_id,
  summaryVisual: n => n.slides.at(-1).visual_id = 'image-1',
  checksVisual: n => n.slides[1].visual_id = 'image-1',
  noGraph: n => n.slides.at(-1).layout = 'topology',
  duplicate: n => n.slides[1].checks[1].scenario_id = 'check-0',
  omitted: n => n.slides[1].checks.pop(),
  sixRows: n => n.slides[1].checks.push(n.slides[2].checks.pop()),
  wrongSection: n => n.slides.at(-1).layout = 'checks',
  missingChecks: n => delete n.slides[1].checks,
  label: n => n.slides[1].checks[0].label_claim_id = 'missing',
  purpose: n => n.slides[1].checks[0].purpose_claim_id = 'missing',
  emptyMapping: n => n.slides[1].checks[0].narration_sentence_indices = [],
  duplicateMapping: n => n.slides[1].checks[0].narration_sentence_indices = [0,0],
  reverseMapping: n => n.slides[1].checks[0].narration_sentence_indices = [1,0],
  noncontiguousMapping: n => n.slides[1].checks[0].narration_sentence_indices = [0,2],
  overlappingMapping: n => n.slides[1].checks[1].narration_sentence_indices = [0],
  outsideMapping: n => n.slides[1].checks[0].narration_sentence_indices = [12],
  booleanMapping: n => n.slides[1].checks[0].narration_sentence_indices = [true],
  nonchecksRows: n => n.slides.at(-1).checks = [n.slides[1].checks[0]],
  unknownVersion: n => n.schema_version = 4,
})) test(`schema3 rejects ${name}`, () => {
  const item = structuredClone(genericCases[4]); mutate(item.narrative)
  assert.throws(() => validateStoryboard(item.narrative, item.plan))
})
test('empty inventory explicitly needs a testing checks layout', () => {
  const item = structuredClone(genericCases[0]); item.narrative.slides[1].layout = 'summary'
  assert.throws(() => validateStoryboard(item.narrative, item.plan))
})

test('schema3 reviewed imagery metadata and contiguous multi-sentence row', () => {
  const item = structuredClone(genericCases[1]), n = item.narrative
  Object.assign(n.project_context, { revision:'abc123', homepage_url:'https://example.org/', documentation_url:'https://docs.example.org/guide' })
  n.slides[0].visual_id = 'project-image'
  n.slides[1].narration.push({text:'The check also covers invalid input.',claim_ids:['claim-1']})
  n.slides[1].checks[0].narration_sentence_indices = [0,1]
  validateStoryboard(n, item.plan)
})
test('schema3 impossible long inventory fails before synthesis', () => {
  const item = structuredClone(genericCases[4]), n = item.narrative
  while (n.slides.length < 30) { const extra = structuredClone(n.slides.at(-1)); extra.id = `extra-${n.slides.length}`; n.slides.push(extra) }
  for (const slide of n.slides) slide.narration = Array.from({length:12}, () => ({text:Array(15).fill('word').join(' '),claim_ids:['claim-0']}))
  item.plan.slide_ids = n.slides.map(s => s.id)
  assert.throws(() => validateStoryboard(n,item.plan), /estimated/)
})
for (const url of ['https:///example.org','https://@example.org','https://example.org:bad','https://example.org/\nsecret']) test(`schema3 rejects malformed URL ${JSON.stringify(url)}`, () => {
  const item = structuredClone(genericCases[0]); item.narrative.project_context.repository_url = url
  assert.throws(() => validateStoryboard(item.narrative,item.plan))
})
