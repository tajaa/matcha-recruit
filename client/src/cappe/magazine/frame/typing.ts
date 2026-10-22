import { commandKey, layerKey } from './layers'
import { makePlain, pastePlain, plainOf } from './plain'
import { editorOf, makeRich, richValue } from './rich'
import { select } from './selection'
import { book, place, post, state } from './state'
import { blockOf, storyOf } from './targets'
import { hideBar, inBar, openLink, showBar } from './toolbar'

/** Typing straight into the page. Every [data-mz-f] is a field: plain words
 *  (plain.ts) or rich text (rich.ts). What is typed goes to the editor
 *  outside as `mz-edit` (a plain field's words, a rich field's document) a
 *  moment after typing pauses and when the field is left; `mz-editing` says
 *  when typing starts and stops (the editor outside never reloads the page
 *  under it meanwhile). */

const isRich = (f: Element) => f.getAttribute('data-mz-k') === 'rich'
const fieldOf = (t: EventTarget | null) => (t instanceof Element ? t.closest<HTMLElement>('[data-mz-f]') : null)

const last = new WeakMap<Element, string>()
let original = ''
let timer: ReturnType<typeof setTimeout> | undefined
let lastTyped = 0

/** Whether a key was just pressed in a field: a scroll of the book then is
 *  the browser showing the caret, not the owner turning the pages. */
export const typedRecently = () => performance.now() - lastTyped < 600

function valueOf(f: HTMLElement) {
  return isRich(f) ? richValue(f) : plainOf(f)
}

function commit(f: HTMLElement) {
  clearTimeout(timer)
  const value = valueOf(f)
  const key = JSON.stringify(value)
  if (value === null || key === last.get(f)) return
  last.set(f, key)
  post({ type: 'mz-edit', story: storyOf(f), block: blockOf(f), field: f.getAttribute('data-mz-f'), value, rich: isRich(f) })
}

function typed(f: HTMLElement) {
  clearTimeout(timer)
  timer = setTimeout(() => commit(f), 250)
  place()
}

function caretRect(): DOMRect | null {
  const s = getSelection()
  if (!s?.rangeCount) return null
  const r = s.getRangeAt(0), rects = r.getClientRects()
  const rect = rects.length ? rects[rects.length - 1] : null
  if (rect && (rect.width || rect.height)) return rect
  const n = r.startContainer
  return (n.nodeType === Node.ELEMENT_NODE ? n as Element : n.parentElement)?.getBoundingClientRect() ?? null
}

/** Keep the words being typed on screen: when they run onto another page,
 *  turn to it. The browser also scrolls the book part way to show the
 *  caret (Chromium does, a page's width or less), which would leave it
 *  between two spreads: that is put right too. */
export function followCaret() {
  const f = state.editing, mz = book()
  if (!f) return
  const rect = caretRect(), pages = f.closest('.mz-book')
  if (rect && pages && mz) {
    const w = pages.clientWidth || 1
    const spread = Math.floor((rect.left - pages.getBoundingClientRect().left + pages.scrollLeft) / w)
    if (spread !== mz.at() || Math.abs(pages.scrollLeft - spread * w) > 2) {
      // The book counts its spreads when it is laid out; words typed onto a
      // new one need it counted again first, or the turn stops short.
      mz.refit()
      mz.go(spread, true)
    }
  }
  if (isRich(f)) showBar(); else hideBar()
}

function mount(f: HTMLElement) {
  if (isRich(f)) {
    makeRich(f, typed, followCaret)
    last.set(f, JSON.stringify(richValue(f)))
  } else makePlain(f)
}

/** Type into a field that only opens when asked (the words on a design's
 *  layer: a click there selects the layer, a double click types), the caret
 *  where the pointer is, else all its words selected. */
export function editField(f: HTMLElement, at?: { x: number; y: number }) {
  let ed = editorOf(f)
  if (!ed) { mount(f); ed = editorOf(f) }
  if (!ed) return
  ed.setEditable(true)
  const pos = at ? ed.view.posAtCoords({ left: at.x, top: at.y }) : null
  if (pos) ed.commands.focus(pos.pos)
  else { ed.commands.focus(); ed.commands.selectAll() }
}

export function startTyping() {
  // Words on a design's layer open on a double click (layers.ts).
  document.querySelectorAll<HTMLElement>('[data-mz-f]:not([data-mz-lazy])').forEach(mount)

  document.addEventListener('focusin', (e) => {
    const f = fieldOf(e.target)
    if (!f) return
    state.editing = f
    original = isRich(f) ? '' : plainOf(f)
    if (!isRich(f)) last.set(f, JSON.stringify(original))
    post({ type: 'mz-editing', on: true })
  })
  document.addEventListener('focusout', (e) => {
    const f = state.editing
    // Leaving the field, or the link box in its bar: the field and its bar
    // are one place to type in, and only leaving both ends editing (a click
    // on a picture with a link half typed must not leave it on).
    if (!f || (fieldOf(e.target) !== f && !inBar(e.target))) return
    setTimeout(() => {
      const now = document.activeElement
      if (now && (f.contains(now) || inBar(now))) return
      commit(f)
      // Words on a layer close again: a click there selects the layer.
      if (f.hasAttribute('data-mz-lazy')) editorOf(f)?.setEditable(false)
      if (state.editing !== f) return // already typing in the next field
      state.editing = null
      hideBar()
      place()
      post({ type: 'mz-editing', on: false })
    }, 0)
  })
  document.addEventListener('input', (e) => {
    const f = fieldOf(e.target)
    if (f && !isRich(f)) typed(f) // a rich field reports through its editor
  })
  document.addEventListener('paste', (e) => {
    const f = fieldOf(e.target)
    // A rich field keeps what its editor can hold of a paste (extensions.ts).
    if (f && !isRich(f)) pastePlain(e)
  })
  document.addEventListener('selectionchange', followCaret)
  // Before a field's own editor, which marks keys it ignores (Escape) as
  // handled; nothing here is a key that editor uses.
  document.addEventListener('keydown', onKey, true)
}

function onKey(e: KeyboardEvent) {
  // The link box in the bar answers its own Enter and Escape.
  if (inBar(e.target)) return
  const mod = e.metaKey || e.ctrlKey, k = (e.key || '').toLowerCase()
  const f = state.editing
  if (f) {
    lastTyped = performance.now()
    if (e.key === 'Escape') {
      // A headline goes back to what it was; a paragraph's typing is kept
      // (undo takes it back), so a stray key never throws it away.
      e.preventDefault()
      if (!isRich(f)) f.textContent = original
      if (isRich(f)) editorOf(f)?.commands.blur()
      else f.blur()
    } else if (e.key === 'Enter' && !e.shiftKey && !isRich(f)) {
      e.preventDefault()
      f.blur()
    } else if (mod && k === 'k' && isRich(f)) {
      e.preventDefault()
      openLink()
    } else if (mod && k === 's') {
      e.preventDefault()
      commit(f)
      post({ type: 'mz-key', key: 'save' })
    } else if (/^(Home|End|PageUp|PageDown)$/.test(e.key) && !e.shiftKey) {
      // On a Mac these scroll the page rather than move the caret, which
      // here would carry the book off screen mid-sentence.
      e.preventDefault()
    }
    return
  }
  // Keys for the layers selected (nudge, select all, step out, type in).
  if (layerKey(e)) { e.preventDefault(); e.stopPropagation(); return }
  const command = commandKey(e)
  if (command) {
    if (e.target instanceof Element && e.target.closest('input, textarea')) return
    e.preventDefault()
    post({ type: 'mz-key', key: command })
    return
  }
  if (mod && k === 'z') { e.preventDefault(); post({ type: 'mz-key', key: e.shiftKey ? 'redo' : 'undo' }) }
  else if (mod && k === 'y') { e.preventDefault(); post({ type: 'mz-key', key: 'redo' }) }
  else if (mod && k === 's') { e.preventDefault(); post({ type: 'mz-key', key: 'save' }) }
  else if (e.key === 'Delete' || e.key === 'Backspace') {
    // Never the browser's own "back", which would leave the editor.
    if (!(e.target instanceof Element && e.target.closest('input, textarea'))) e.preventDefault()
    if (state.selected.kind === 'block' || state.selected.kind === 'layer') post({ type: 'mz-key', key: 'delete' })
  } else if (e.key === 'Escape' && state.selected.kind !== 'none') {
    select({ kind: 'none' }, null)
    post({ type: 'mz-select', target: { kind: 'none' } })
  }
}
