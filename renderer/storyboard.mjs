/** Pure data validation/mapping. This module is safe to import in the browser. */
export const storySections = ['objective', 'testing', 'setup', 'execution', 'results', 'limitations', 'recommendation']
// Outcome significance, not JSON key order. Authored narratives serialize
// results alphabetically, which put the only meaningful figure fourth behind
// four zeros on the delivered 9 November deck.
export const resultOrder = ['pass', 'fail', 'error', 'skip', 'incomplete']
export const timingPolicy = { lead_seconds:.35, tail_seconds:.65, min_scene_seconds:6, sentence_gap_seconds:.20, max_scene_seconds:120, max_total_seconds:900, max_scenes:30 }
const white = /[\p{White_Space}\u001c-\u001f]+/u
const trim = value => value.replace(/^[\p{White_Space}\u001c-\u001f]+|[\p{White_Space}\u001c-\u001f]+$/gu, '')
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value)
const need = (condition, message = 'Invalid executive storyboard') => { if (!condition) throw new Error(message) }
// misaki.en.LINK_REGEX: Misaki reads "[word](/ips/)" as a pronunciation or
// stress override, so reviewed scripts must never contain it.
const markup = /\[[^\]]+\]\([^)]*\)/
const text = (value, limit) => { need(typeof value === 'string' && Array.from(value).length >= 1 && Array.from(value).length <= limit && !!trim(value)); return value }
const id = value => { need(typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/.test(value)); return value }

function refs(value, claims, minimum = 1, maximum = 512) {
  need(Array.isArray(value) && value.length >= minimum && value.length <= maximum)
  need(value.every(v => typeof v === 'string' && claims.has(v)) && new Set(value).size === value.length)
}

export function validateStoryboard(narrative, plan) {
  need(object(narrative) && [2,3].includes(narrative.schema_version))
  id(narrative.run_id); text(narrative.project_name, 100)
  const statuses = ['pass','fail','error','skip','incomplete']
  need(object(narrative.results) && Object.keys(narrative.results).sort().join() === [...statuses].sort().join())
  need(statuses.every(s => Number.isSafeInteger(narrative.results[s]) && narrative.results[s] >= 0))
  need(Array.isArray(narrative.claims) && narrative.claims.length >= 1 && narrative.claims.length <= 512)
  const claims = new Set()
  for (const claim of narrative.claims) {
    need(object(claim)); id(claim.id); need(!claims.has(claim.id)); claims.add(claim.id)
    text(claim.text, 280)
    need(['planned','observed','inferred','recommendation'].includes(claim.kind))
    need(Array.isArray(claim.sources) && claim.sources.length >= 1 && claim.sources.length <= 16)
    for (const reference of claim.sources) {
      text(reference, 512)
      const marker = reference.indexOf('#')
      const member = marker < 0 ? reference : reference.slice(0, marker)
      need(/^[A-Za-z0-9][A-Za-z0-9_./-]*$/.test(member) && !member.split('/').includes('..'))
      if (marker >= 0) {
        const selector = reference.slice(marker + 1)
        need(/^L[1-9][0-9]*-L[1-9][0-9]*$/.test(selector) || (member.endsWith('.json') && selector.startsWith('/') && !/~(?![01])/.test(selector)))
      }
    }
  }
  need(Array.isArray(narrative.coverage_gaps) && narrative.coverage_gaps.length <= 32)
  narrative.coverage_gaps.forEach(v => text(v, 280))
  need(Array.isArray(narrative.conflicts) && narrative.conflicts.length <= 32)
  for (const conflict of narrative.conflicts) { need(object(conflict)); text(conflict.text, 280); refs(conflict.claim_ids, claims, 2) }
  need(Array.isArray(narrative.slides) && narrative.slides.length >= 6 && narrative.slides.length <= 30)
  const seen = new Set(), chapters = new Set()
  let previous = -1
  for (const slide of narrative.slides) {
    need(object(slide)); id(slide.id); need(!seen.has(slide.id)); seen.add(slide.id)
    const rank = storySections.indexOf(slide.section)
    need(rank >= 0 && rank >= previous); previous = rank; chapters.add(slide.section)
    text(slide.title, 100)
    refs(slide.title_claim_ids, claims); refs(slide.bullet_claim_ids, claims, 1, 4)
    need(Array.isArray(slide.narration) && slide.narration.length >= 1 && slide.narration.length <= 12)
    let words = 0
    for (const sentence of slide.narration) { need(object(sentence) && !markup.test(text(sentence.text, 2000))); words += trim(sentence.text).split(white).length; refs(sentence.claim_ids, claims) }
    need(words <= 180)
    if (slide.graph != null) {
      need(object(slide.graph))
      for (const [field, maximum] of [['nodes',12],['edges',20],['acts',5]])
        need(Array.isArray(slide.graph[field]) && slide.graph[field].length <= maximum && slide.graph[field].every(row => field === 'edges' ? Array.isArray(row) && row.length === 2 && row.every(v => typeof v === 'string') : object(row)))
      refs(slide.graph_claim_ids, claims)
    } else { refs(slide.graph_claim_ids, claims, 0); need(slide.graph_claim_ids.length === 0) }
  }
  if (narrative.schema_version === 3) validateGenericStory(narrative, claims)
  need(storySections.filter(s => s !== 'execution').every(s => chapters.has(s)))
  need(object(plan) && plan.schema_version === 2 && !('durations' in plan))
  need(Array.isArray(plan.slide_ids) && plan.slide_ids.length === narrative.slides.length && plan.slide_ids.every((s, i) => s === narrative.slides[i].id))
  need(object(plan.narration) && plan.narration.engine === 'kokoro' && plan.narration.voice === 'af_heart' && plan.narration.speed === .95
    && typeof plan.narration.model_manifest_sha256 === 'string' && /^[0-9a-f]{64}$/.test(plan.narration.model_manifest_sha256))
  // Optional: plans reviewed before the lexicon existed render without overrides.
  need(plan.narration.lexicon_sha256 == null || /^[0-9a-f]{64}$/.test(plan.narration.lexicon_sha256))
  need(object(plan.timing_policy) && Object.keys(plan.timing_policy).sort().join() === Object.keys(timingPolicy).sort().join())
  need(Object.entries(timingPolicy).every(([key, value]) => Number.isFinite(plan.timing_policy[key]) && plan.timing_policy[key] === value))
  if (narrative.schema_version === 3) {
    const total = narrative.slides.reduce((sum, slide) => {
      const words = slide.narration.reduce((count, sentence) => count + trim(sentence.text).split(white).length, 0)
      return sum + Math.max(timingPolicy.min_scene_seconds, words / 3
        + Math.max(slide.narration.length - 1, 0) * timingPolicy.sentence_gap_seconds
        + timingPolicy.lead_seconds + timingPolicy.tail_seconds)
    }, 0)
    need(total <= timingPolicy.max_total_seconds, `Narration cannot fit the 900s guard: estimated ${total.toFixed(1)}s. Revise scope or shorten the script before synthesis; measured audio remains authoritative.`)
  }
  return narrative.slides
}

function httpsReference(value) {
  text(value, 2048)
  need(/^https:\/\/[^/?#]+(?:[/?#]|$)/i.test(value) && !/[\s\\\x00-\x1f\x7f]/u.test(value))
  let parsed
  try { parsed = new URL(value) } catch { throw new Error('Invalid project reference') }
  need(parsed.protocol === 'https:' && !!parsed.hostname && !parsed.username && !parsed.password
    && !/^https:\/\/[^/?#]*@/i.test(value), 'Project references must be credential-free HTTPS URLs')
}

function validateGenericStory(narrative, claims) {
  const context = narrative.project_context
  need(object(context) && Object.keys(context).sort().join() === ['repository_url','revision','definition_claim_id','homepage_url','documentation_url'].sort().join())
  httpsReference(context.repository_url)
  for (const key of ['homepage_url','documentation_url']) if (context[key] !== null) httpsReference(context[key])
  if (context.revision !== null) text(context.revision, 280)
  refs([context.definition_claim_id], claims)
  const opening = narrative.slides[0]
  need(opening.layout === 'identity' && [...opening.title_claim_ids, ...opening.bullet_claim_ids].includes(context.definition_claim_id), 'Project definition must be visible')
  const scenarios = []; let checkSlides = 0
  for (const slide of narrative.slides) {
    need(['summary','identity','checks','topology'].includes(slide.layout))
    need('visual_id' in slide)
    if (slide.visual_id !== null) { id(slide.visual_id); need(slide.layout === 'identity') }
    if (slide.layout === 'topology') need(slide.graph != null, 'Topology layout requires a graph')
    need(Array.isArray(slide.checks))
    if (slide.layout !== 'checks') { need(slide.checks.length === 0); continue }
    checkSlides++
    need(slide.section === 'testing' && slide.checks.length <= 5, 'Paginate testing checks in five-row slides')
    let previous = -1
    for (const row of slide.checks) {
      need(object(row) && Object.keys(row).sort().join() === ['scenario_id','label_claim_id','purpose_claim_id','narration_sentence_indices'].sort().join())
      scenarios.push(id(row.scenario_id)); refs([row.label_claim_id], claims); refs([row.purpose_claim_id], claims)
      const indices = row.narration_sentence_indices
      need(Array.isArray(indices) && indices.length > 0)
      need(indices.every((v,i) => Number.isSafeInteger(v) && v >= 0 && v < slide.narration.length && (!i || v === indices[i-1] + 1)))
      need(indices[0] > previous, 'Check sentence mappings must be contiguous, ordered and nonoverlapping')
      previous = indices.at(-1)
    }
  }
  // Exact IDs are bound against verified evidence by Python before offline rendering.
  need(new Set(scenarios).size === scenarios.length && scenarios.length === Object.values(narrative.results).reduce((a,b) => a+b, 0), 'Every original scenario must appear exactly once')
  need(checkSlides >= 1, 'Explicit testing checks content is required even for no checks')
}

export function speakerNotes(slide) {
  return slide.narration.map(s => s.text).join('\n\n').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('--','&#45;&#45;')
}

export function transcript(narrative) {
  return narrative.slides.map(s => `${s.title}\n${s.narration.map(n => n.text).join('\n')}`).join('\n\n') + '\n'
}
