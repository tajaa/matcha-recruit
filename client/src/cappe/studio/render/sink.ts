// The one place the Studio writes HTML into the page. Everything it writes
// was made by render/layoutRender.ts from the Studio's own document: words
// escaped, colours, faces and numbers checked, pictures from the library by
// their checked URLs (the server's renderer, held byte-equal). Nothing typed
// or fetched is written here raw.

const shown = new WeakMap<Element, string>()

/** Set an element's HTML, only when it changed (a page drawn again). */
export function setHtml(el: Element, html: string): boolean {
  if (shown.get(el) === html) return false
  el.innerHTML = html
  shown.set(el, html)
  return true
}
