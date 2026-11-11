/** Offsets start at speech; measured scenes include a 350ms silent lead. */
export function checkWindows(slide, scene) {
  const need = value => { if (!value) throw new Error('Invalid measured check timing') }
  need(scene?.id === slide.id && Number.isFinite(scene.start_seconds) && scene.start_seconds >= 0 && Number.isFinite(scene.duration_seconds) && scene.duration_seconds > 0 && Array.isArray(scene.sentence_offsets))
  let previousEnd = 0
  for (const offset of scene.sentence_offsets) {
    need(Number.isFinite(offset?.start_seconds) && Number.isFinite(offset.end_seconds) && offset.start_seconds >= previousEnd && offset.end_seconds > offset.start_seconds && offset.end_seconds + .35 <= scene.duration_seconds)
    previousEnd = offset.end_seconds
  }
  let previousIndex = -1
  return slide.checks.map(row => {
    const indices = row.narration_sentence_indices
    need(Array.isArray(indices) && indices.length && indices[0] > previousIndex && indices.every((n,i) => Number.isSafeInteger(n) && n >= 0 && n < scene.sentence_offsets.length && (!i || n === indices[i-1]+1)))
    previousIndex = indices.at(-1)
    return { scenario_id:row.scenario_id, start_seconds:scene.start_seconds + .35 + scene.sentence_offsets[indices[0]].start_seconds, end_seconds:scene.start_seconds + .35 + scene.sentence_offsets[indices.at(-1)].end_seconds }
  })
}
export function activeCheck(windows, elapsedSeconds) {
  return windows.find(window => elapsedSeconds >= window.start_seconds && elapsedSeconds < window.end_seconds)?.scenario_id ?? null
}
