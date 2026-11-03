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
  return result
}
