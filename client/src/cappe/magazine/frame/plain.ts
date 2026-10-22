/** Fields of plain words (a headline, a caption, a quote): typed straight
 *  into the page, no formatting. */

const plainMode = (() => {
  const d = document.createElement('div')
  try { d.contentEditable = 'plaintext-only' } catch { return 'true' }
  return d.contentEditable === 'plaintext-only' ? 'plaintext-only' : 'true'
})()

export function makePlain(f: HTMLElement) {
  f.setAttribute('contenteditable', plainMode)
  f.setAttribute('spellcheck', 'true')
}

/** A plain field's words as typed: not `innerText`, which would hand back
 *  what CSS shows (a kicker set in capitals); a line break is a newline, and
 *  a typed space at a line's end (a no-break space) is a space. */
export function plainOf(f: HTMLElement): string {
  let out = ''
  const walk = (n: Node) => n.childNodes.forEach((c) => {
    if (c.nodeType === Node.TEXT_NODE) out += c.nodeValue
    else if (c.nodeName === 'BR') out += '\n'
    else {
      if (/^(DIV|P)$/.test(c.nodeName) && out && !out.endsWith('\n')) out += '\n'
      walk(c)
    }
  })
  walk(f)
  return out.replace(/\u00a0/g, ' ').replace(/\n+$/, '')
}

/** Words only: another page's formatting never comes in with them. */
export function pastePlain(e: ClipboardEvent) {
  e.preventDefault()
  document.execCommand('insertText', false, e.clipboardData?.getData('text/plain') || '')
}
