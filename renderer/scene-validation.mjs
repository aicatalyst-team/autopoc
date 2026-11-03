/** inspectScene also runs serialized in Playwright's browser context. */
export function sceneProblems(snapshot) {
  return [...snapshot.errors,
    ...snapshot.missingFonts.map(name => `Required font unavailable: ${name}`),
    ...snapshot.missingImages.map(name => `Required brand image unavailable: ${name}`),
    ...snapshot.overflow.map(name => `Layout overflow in ${name}; shorten the reviewed text before rendering`)]
}

export async function loadSceneAssets(section) {
  for (const family of ['Display', 'Text', 'Mono']) for (const weight of [400, 500, 700]) {
    const descriptor = `${weight} 16px "Red Hat ${family}"`
    const faces = await document.fonts.load(descriptor)
    if (!faces.length || !document.fonts.check(descriptor)) throw new Error(`Required font unavailable: Red Hat ${family} ${weight}`)
  }
  await Promise.all([...section.querySelectorAll('img')].map(img => img.decode()))
  await document.fonts.ready
}

export function sceneCheckTimes(graph) {
  if (!graph) return []
  const times = new Set([3]) // PDF/reduced-motion still
  for (const act of graph.acts) {
    for (const time of [act.t0 + .01, (act.t0 + act.t1) / 2, act.t1 - .01,
      ...(act.log || []).map(line => line.at + .01)])
      if (Number.isFinite(time) && time >= 0) times.add(time)
  }
  if (times.size > 80) throw new Error('Too many animation states; simplify the reviewed scene')
  return [...times].sort((a, b) => a - b)
}

export function inspectScene() {
  const root = document.querySelector('.executive[data-executive-ready="true"]')
  const result = { errors: [], missingFonts: [], missingImages: [], overflow: [] }
  if (!root) { result.errors.push('Executive scene is missing'); return result }
  if (root.dataset.executiveError) result.errors.push(root.dataset.executiveError)
  for (const family of ['Display', 'Text', 'Mono']) for (const weight of [400, 500, 700])
    if (!document.fonts.check(`${weight} 16px "Red Hat ${family}"`)) result.missingFonts.push(`Red Hat ${family} ${weight}`)
  for (const img of root.querySelectorAll('img'))
    if (!img.complete || !img.naturalWidth) result.missingImages.push(img.alt || img.src)
  const bounds = root.getBoundingClientRect()
  const tolerance = Math.max(1, bounds.width / 1280 * 2)
  for (const region of root.querySelectorAll('[data-layout-region]')) {
    const box = region.getBoundingClientRect()
    let over = region.scrollHeight > region.clientHeight + 2 || region.scrollWidth > region.clientWidth + 2
      || box.bottom > bounds.bottom + tolerance || box.right > bounds.right + tolerance
    const walker = document.createTreeWalker(region, NodeFilter.SHOW_TEXT)
    let node
    while ((node = walker.nextNode())) {
      if (!node.textContent.trim() || node.parentElement.closest('.topology-stage')) continue
      const range = document.createRange(); range.selectNodeContents(node)
      for (const text of range.getClientRects())
        if (text.bottom > box.bottom + tolerance || text.top < box.top - tolerance || text.right > box.right + tolerance || text.left < box.left - tolerance) over = true
    }
    if (over) result.overflow.push(region.dataset.layoutRegion)
  }
  for (const title of root.querySelectorAll('[data-max-lines]')) {
    const line = parseFloat(getComputedStyle(title).lineHeight)
    if (title.getBoundingClientRect().height > line * Number(title.dataset.maxLines) * bounds.width / 1280 + tolerance) result.overflow.push('slide title')
  }
  for (const stage of root.querySelectorAll('.topology-stage')) {
    const stageBox = stage.getBoundingClientRect()
    const visible = element => {
      for (let parent = element; parent && parent !== stage; parent = parent.parentElement) {
        const style = getComputedStyle(parent)
        if (style.visibility === 'hidden' || style.display === 'none' || Number(style.opacity) === 0) return false
      }
      return true
    }
    for (const element of stage.querySelectorAll('.tl-node.on, .tl-hud-top, .tl-status, .tl-board, .tl-term, .tl-ann')) {
      if (!visible(element)) continue
      const ownRegion = element.matches('.tl-board, .tl-term, .tl-ann')
      const box = ownRegion ? element.getBoundingClientRect() : stageBox
      let clipped = ownRegion && (element.scrollHeight > element.clientHeight + 2 || element.scrollWidth > element.clientWidth + 2)
      const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT)
      let text
      while ((text = walker.nextNode())) {
        if (!text.textContent.trim()) continue
        const range = document.createRange(); range.selectNodeContents(text)
        for (const rect of range.getClientRects())
          if (rect.left < box.left - tolerance || rect.right > box.right + tolerance
              || rect.top < box.top - tolerance || rect.bottom > box.bottom + tolerance) clipped = true
      }
      if (clipped) result.overflow.push(`diagram ${element.classList[0]} text`)
    }
    const heading = stage.querySelector('.tl-hud-top')?.getBoundingClientRect()
    if (!heading) continue
    for (const node of stage.querySelectorAll('.tl-node.on')) {
      const box = node.getBoundingClientRect()
      if (box.left < heading.right && box.right > heading.left
          && box.top < heading.bottom && box.bottom > heading.top)
        result.overflow.push('diagram heading overlaps a node label')
    }
  }
  return result
}
