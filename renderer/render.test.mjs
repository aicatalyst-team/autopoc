import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, readFile, writeFile, rm, cp, unlink } from 'node:fs/promises'
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
    await writeFile(join(root, 'versions.json'), JSON.stringify({ template: 2 }))
    await prepareDeck(root, join(root, 'deck'))
    const slides = await readFile(join(root, 'deck/slides.md'), 'utf8')
    assert.equal((slides.match(/ExecutiveSlide/g) || []).length, 6)
    assert.ok(!slides.includes('process.exit'))
    assert.deepEqual(JSON.parse(await readFile(join(root, 'deck/narrative.json'))), narrative)
    assert.match(slides, /sans: Red Hat Text/)
    const brand = JSON.parse(await readFile(join(root, 'deck/assets/redhat/manifest.json')))
    for (const entry of brand.files) {
      assert.deepEqual(await readFile(join(root, 'deck/public/brand', entry.path)),
        await readFile(join(root, 'deck/assets/redhat', entry.path)))
    }
    assert.ok((await readFile(join(root, 'deck/scene-validation.mjs'))).length)
    assert.equal(JSON.parse(await readFile(join(root, 'deck/versions.json'))).template, 2)
  } finally { await rm(root, { recursive: true, force: true }) }
})

test('legacy inputs are rejected before creating an unversioned deck', async () => {
  const root = await mkdtemp(join(tmpdir(), 'autopoc-legacy-'))
  try {
    await writeFile(join(root, 'versions.json'), JSON.stringify({ template: 1 }))
    await assert.rejects(prepareDeck(root, join(root, 'deck')), /template revision 2/)
  } finally { await rm(root, { recursive: true, force: true }) }
})

test('missing or changed brand files fail verification rather than fall back', async () => {
  const { verifyBrandAssets } = await import('./branding.mjs')
  const root = await mkdtemp(join(tmpdir(), 'autopoc-assets-'))
  try {
    await cp(new URL('./assets/redhat/', import.meta.url), root, { recursive: true })
    await verifyBrandAssets(root)
    const font = join(root, 'fonts/RedHatText-Regular.woff2')
    const bytes = await readFile(font)
    await writeFile(font, 'tampered')
    await assert.rejects(verifyBrandAssets(root), /Brand asset integrity/)
    await writeFile(font, bytes)
    await unlink(join(root, 'logos/redhat-logo-standard.svg'))
    await assert.rejects(verifyBrandAssets(root), /Required brand asset/)
  } finally { await rm(root, { recursive: true, force: true }) }
})

test('content validation distinguishes missing assets and overflowing text from usable scenes', async () => {
  const { sceneProblems } = await import('./scene-validation.mjs')
  const good = { errors: [], missingFonts: [], missingImages: [], overflow: [] }
  assert.deepEqual(sceneProblems(good), [])
  assert.match(sceneProblems({ ...good, missingFonts: ['Red Hat Text'] }).join(), /font/)
  assert.match(sceneProblems({ ...good, missingImages: ['corporate logo'] }).join(), /image/)
  assert.match(sceneProblems({ ...good, overflow: ['purpose claim'] }).join(), /shorten/)
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
