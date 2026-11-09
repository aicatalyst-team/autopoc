/** Pure data validation/mapping. This module is safe to import in the browser. */
export const storySections = ['objective', 'testing', 'setup', 'execution', 'results', 'limitations', 'recommendation']
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
  need(object(narrative) && narrative.schema_version === 2)
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
  need(storySections.filter(s => s !== 'execution').every(s => chapters.has(s)))
  need(object(plan) && plan.schema_version === 2 && !('durations' in plan))
  need(Array.isArray(plan.slide_ids) && plan.slide_ids.length === narrative.slides.length && plan.slide_ids.every((s, i) => s === narrative.slides[i].id))
  need(object(plan.narration) && plan.narration.engine === 'kokoro' && plan.narration.voice === 'af_heart' && plan.narration.speed === .95
    && typeof plan.narration.model_manifest_sha256 === 'string' && /^[0-9a-f]{64}$/.test(plan.narration.model_manifest_sha256))
  // Optional: plans reviewed before the lexicon existed render without overrides.
  need(plan.narration.lexicon_sha256 == null || /^[0-9a-f]{64}$/.test(plan.narration.lexicon_sha256))
  need(object(plan.timing_policy) && Object.keys(plan.timing_policy).sort().join() === Object.keys(timingPolicy).sort().join())
  need(Object.entries(timingPolicy).every(([key, value]) => Number.isFinite(plan.timing_policy[key]) && plan.timing_policy[key] === value))
  return narrative.slides
}

export function speakerNotes(slide) {
  return slide.narration.map(s => s.text).join('\n\n').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('--','&#45;&#45;')
}

export function transcript(narrative) {
  return narrative.slides.map(s => `${s.title}\n${s.narration.map(n => n.text).join('\n')}`).join('\n\n') + '\n'
}
