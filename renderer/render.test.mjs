import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { prepareDeck } from './render.mjs'

test('untrusted narrative stays JSON data and all four topics appear', async () => {
  const root = await mkdtemp(join(tmpdir(), 'autopoc-render-'))
  try {
    const claim = { text: '<script>process.exit(1)</script>', sources: ['report.md'] }
    const narrative = { schema_version: 1, run_id: 'run', project_name: 'Project',
      purpose: [claim], testing_strategy: [claim], test_execution: [claim],
      platform_suitability: [claim], limitations: ['HTTP smoke coverage only'],
      results: { pass: 1, fail: 0, error: 0, skip: 0, incomplete: 0 }, topology: null }
    await writeFile(join(root, 'narrative.json'), JSON.stringify(narrative))
    await writeFile(join(root, 'scenes.json'), JSON.stringify({ durations: [20,20,20,20,20,20] }))
    await prepareDeck(root, join(root, 'deck'))
    const slides = await readFile(join(root, 'deck/slides.md'), 'utf8')
    assert.equal((slides.match(/ExecutiveSlide/g) || []).length, 6)
    assert.ok(!slides.includes('process.exit'))
    assert.deepEqual(JSON.parse(await readFile(join(root, 'deck/narrative.json'))), narrative)
  } finally { await rm(root, { recursive: true, force: true }) }
})

test('missing topics and unsupported durations cannot render', async () => {
  const root = await mkdtemp(join(tmpdir(), 'autopoc-invalid-'))
  try {
    await writeFile(join(root, 'narrative.json'), JSON.stringify({ schema_version: 1 }))
    await writeFile(join(root, 'scenes.json'), JSON.stringify({ durations: [200] }))
    await assert.rejects(prepareDeck(root, join(root, 'deck')))
  } finally { await rm(root, { recursive: true, force: true }) }
})

test('a scene-content failure also invalidates the deck and the PDF', async () => {
  const { failedArtifacts } = await import('./render.mjs')
  const manifest = { artifacts: { deck: { status: 'validated', path: 'source/dist' },
                                  pdf: { status: 'validated', path: 'executive-summary.pdf' } } }
  const fatal = new Error('Scene initialization failed')
  fatal.contentFailure = true
  failedArtifacts(manifest, fatal)
  assert.equal(manifest.artifacts.deck.status, 'failed')
  assert.equal(manifest.artifacts.pdf.status, 'failed')
  assert.equal(manifest.artifacts.video.status, 'failed')
})

test('a video-only failure keeps the deck and the PDF', async () => {
  const { failedArtifacts } = await import('./render.mjs')
  const manifest = { artifacts: { deck: { status: 'validated', path: 'source/dist' },
                                  pdf: { status: 'validated', path: 'executive-summary.pdf' } } }
  failedArtifacts(manifest, new Error('ffmpeg exited non-zero'))
  assert.equal(manifest.artifacts.deck.status, 'validated')
  assert.equal(manifest.artifacts.pdf.status, 'validated')
  assert.equal(manifest.artifacts.video.status, 'failed')
})
