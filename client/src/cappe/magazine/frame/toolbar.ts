import type { Editor } from '@tiptap/core'
import { editorOf } from './rich'
import { state, ui } from './state'

/** The small bar over selected words in a rich field: bold, italic,
 *  underline, strike-through, a link, two headings, a quote and two kinds of
 *  list. A link is typed into the bar itself (the sandbox blocks prompt()). */

type Tool = { cmd: string; label: string; title: string; run: (e: Editor) => void; on: (e: Editor) => boolean }

const TOOLS: Tool[] = [
  { cmd: 'bold', label: 'B', title: 'Bold', run: (e) => e.chain().focus().toggleBold().run(), on: (e) => e.isActive('bold') },
  { cmd: 'italic', label: 'I', title: 'Italic', run: (e) => e.chain().focus().toggleItalic().run(), on: (e) => e.isActive('italic') },
  { cmd: 'underline', label: 'U', title: 'Underline', run: (e) => e.chain().focus().toggleUnderline().run(), on: (e) => e.isActive('underline') },
  { cmd: 'strike', label: 'S', title: 'Strike through', run: (e) => e.chain().focus().toggleStrike().run(), on: (e) => e.isActive('strike') },
  { cmd: 'link', label: 'Link', title: 'Link', run: () => openLink(), on: (e) => e.isActive('link') },
  { cmd: 'h2', label: 'H2', title: 'Heading', run: (e) => e.chain().focus().toggleHeading({ level: 2 }).run(), on: (e) => e.isActive('heading', { level: 2 }) },
  { cmd: 'h3', label: 'H3', title: 'Small heading', run: (e) => e.chain().focus().toggleHeading({ level: 3 }).run(), on: (e) => e.isActive('heading', { level: 3 }) },
  { cmd: 'quote', label: '“', title: 'Quote', run: (e) => e.chain().focus().toggleBlockquote().run(), on: (e) => e.isActive('blockquote') },
  { cmd: 'ul', label: '•', title: 'Bulleted list', run: (e) => e.chain().focus().toggleBulletList().run(), on: (e) => e.isActive('bulletList') },
  { cmd: 'ol', label: '1.', title: 'Numbered list', run: (e) => e.chain().focus().toggleOrderedList().run(), on: (e) => e.isActive('orderedList') },
]

const bar = ui('div', 'mze-bar')
bar.setAttribute('role', 'toolbar')
bar.setAttribute('aria-label', 'Format')
for (const t of TOOLS) {
  const b = document.createElement('button')
  b.type = 'button'
  b.dataset.cmd = t.cmd
  b.title = t.title
  b.setAttribute('aria-label', t.title)
  b.textContent = t.label
  bar.appendChild(b)
}
const linkInput = document.createElement('input')
linkInput.className = 'mze-link'
linkInput.type = 'url'
linkInput.placeholder = 'Paste a link, then Enter'
linkInput.setAttribute('aria-label', 'Link address')
linkInput.hidden = true
bar.appendChild(linkInput)

const current = () => (state.editing ? editorOf(state.editing) : undefined)
let linkRange: { from: number; to: number } | null = null

// Pressing a button keeps the words selected.
bar.addEventListener('mousedown', (e) => { if (e.target !== linkInput) e.preventDefault() })
bar.addEventListener('click', (e) => {
  const b = e.target instanceof Element ? e.target.closest('button') : null
  const ed = current()
  const tool = TOOLS.find((t) => t.cmd === b?.dataset.cmd)
  if (!ed || !tool) return
  tool.run(ed)
  if (tool.cmd !== 'link') showBar()
})

/** Type a link for the selected words (⌘K, or the bar's Link). */
export function openLink() {
  const ed = current()
  if (!ed) return
  const { from, to } = ed.state.selection
  linkRange = { from, to }
  linkInput.value = (ed.getAttributes('link').href as string | undefined) || ''
  linkInput.hidden = false
  showBar(true)
  linkInput.focus()
}

linkInput.addEventListener('keydown', (e) => {
  if (e.key !== 'Enter' && e.key !== 'Escape') return
  e.preventDefault()
  e.stopPropagation()
  const ed = current(), range = linkRange
  linkInput.hidden = true
  if (!ed || !range) return
  const chain = ed.chain().focus().setTextSelection(range)
  const raw = linkInput.value.trim()
  if (e.key === 'Enter') {
    const href = !raw || /^(https?:|mailto:)/i.test(raw) ? raw : `https://${raw}`
    if (!href) chain.extendMarkRange('link').unsetLink().run()
    else if (range.from === range.to && !ed.isActive('link')) {
      chain.insertContent({ type: 'text', text: raw, marks: [{ type: 'link', attrs: { href } }] }).run()
    } else chain.extendMarkRange('link').setLink({ href }).run()
  } else chain.run()
  showBar()
})

/** Over the selected words of the rich field being typed into; hidden when
 *  nothing is selected (unless a link is being typed). */
export function showBar(keep = false) {
  const ed = current()
  const sel = getSelection()
  if (!ed || !sel?.rangeCount || (sel.isCollapsed && !keep && linkInput.hidden)) { hideBar(); return }
  let rect = sel.getRangeAt(0).getBoundingClientRect()
  if (!rect.width && !rect.height) {
    const c = ed.view.coordsAtPos(ed.state.selection.head)
    rect = new DOMRect(c.left, c.top, 1, c.bottom - c.top)
  }
  bar.style.display = 'flex'
  const w = bar.offsetWidth, h = bar.offsetHeight
  bar.style.top = `${rect.top - h - 8 < 4 ? rect.bottom + 8 : rect.top - h - 8}px`
  bar.style.left = `${Math.max(4, Math.min(innerWidth - w - 4, rect.left + rect.width / 2 - w / 2))}px`
  bar.querySelectorAll('button').forEach((b) => {
    const tool = TOOLS.find((t) => t.cmd === b.dataset.cmd)
    b.setAttribute('aria-pressed', tool?.on(ed) ? 'true' : 'false')
  })
}

export function hideBar() {
  bar.style.display = 'none'
  linkInput.hidden = true
}

/** Whether focus has gone to the bar (typing a link), not away from the field. */
export const inBar = (el: EventTarget | null) => el instanceof Element && !!el.closest('.mze-bar')
