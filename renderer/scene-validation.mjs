/** inspectScene also runs serialized in Playwright's browser context. */
export function sceneProblems(snapshot) {
  return [...snapshot.errors,
    ...snapshot.missingFonts.map(name => `Required font unavailable: ${name}`),
    ...snapshot.missingImages.map(name => `Required image unavailable: ${name}`),
    ...snapshot.overflow.map(name => `Layout overflow in ${name}; shorten the reviewed text before rendering`)]
}

export async function loadSceneAssets(section, assets = []) {
  for (const family of ['Display', 'Text', 'Mono']) for (const weight of [400, 500, 700]) {
    const descriptor = `${weight} 16px "Red Hat ${family}"`
    const faces = await document.fonts.load(descriptor)
    if (!faces.length || !document.fonts.check(descriptor)) throw new Error(`Required font unavailable: Red Hat ${family} ${weight}`)
  }
  await Promise.all([...section.querySelectorAll('img')].map(img => img.decode()))
  // Decode the entire verified manifest, including assets on other slides.
  await Promise.all(assets.map(async asset => {
    const image = new Image(); image.src = `/visuals/${asset.id}.png`
    await image.decode()
    if (image.naturalWidth !== asset.width || image.naturalHeight !== asset.height) throw new Error('Reviewed image dimensions differ after decode')
  }))
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
  Object.assign(result, { id:root.dataset.slideId, count:Number(root.dataset.slideCount), section:root.dataset.slideSection, hasGraph:root.dataset.slideGraph === 'true' })
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
      || box.top < bounds.top - tolerance || box.left < bounds.left - tolerance
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
  const visible = element => {
    for (let parent = element; parent; parent = parent.parentElement) {
      const style = getComputedStyle(parent)
      if (style.visibility === 'hidden' || style.display === 'none' || Number(style.opacity) === 0) return false
    }
    return true
  }
  // Measure painted text, not container boxes. A label may intentionally sit
  // inside the graph canvas; its words must not intersect another caption.
  // Include surrounding headings/footer so cross-region collisions fail too.
  const texts = []
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  let text
  while ((text = walker.nextNode())) {
    const element = text.parentElement
    if (!text.textContent.trim() || !visible(element) || element.closest('style, script')) continue
    const stage = element.closest('.topology-stage')
    const range = document.createRange(); range.selectNodeContents(text)
    const name = element.classList[0] || element.tagName.toLowerCase()
    for (const rect of range.getClientRects()) {
      if (!rect.width || !rect.height) continue
      texts.push({ rect, stage, name })
      if (!stage) continue
      let clipped = false
      // Stage and every clipping ancestor matter, including the CSS2D viewport.
      for (let parent = element; parent && root.contains(parent); parent = parent.parentElement) {
        const box = parent.getBoundingClientRect(), style = getComputedStyle(parent)
        const ownRegion = parent.matches('.tl-board, .tl-term, .tl-ann')
        const clipX = ownRegion || parent === stage || ['hidden','clip','auto','scroll'].includes(style.overflowX)
        const clipY = ownRegion || parent === stage || ['hidden','clip','auto','scroll'].includes(style.overflowY)
        if ((clipX && (rect.left < box.left - tolerance || rect.right > box.right + tolerance))
          || (clipY && (rect.top < box.top - tolerance || rect.bottom > box.bottom + tolerance))) clipped = true
      }
      if (clipped) result.overflow.push(`diagram ${name} text`)
    }
  }
  for (let i = 0; i < texts.length; i++) for (let j = i+1; j < texts.length; j++) {
    const a = texts[i], b = texts[j]
    if (!a.stage && !b.stage) continue
    if (a.rect.left < b.rect.right - tolerance && a.rect.right > b.rect.left + tolerance
      && a.rect.top < b.rect.bottom - tolerance && a.rect.bottom > b.rect.top + tolerance)
      result.overflow.push(`diagram ${a.name} overlaps ${b.name}`)
  }
  result.overflow = [...new Set(result.overflow)]
  return result
}
