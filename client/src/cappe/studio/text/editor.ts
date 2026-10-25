// Typing into composed text. A ProseMirror view in a hidden contenteditable
// owns input (keys, IME, dictation, the clipboard); what is shown is the page
// itself, with the Studio's caret and selection drawn from the composed lines
// (text/caret.ts). Each change becomes the thread's paragraphs in the store
// (one undo step per burst of typing), which composes them again; an undo, or
// a panel changing the type, comes back the other way.
//
// The Story Editor (⌘Y) is this same view, shown in a panel.

import { baseKeymap } from '@tiptap/pm/commands'
import { keymap } from '@tiptap/pm/keymap'
import { EditorState, TextSelection, type Command, type Transaction } from '@tiptap/pm/state'
import { EditorView } from '@tiptap/pm/view'
import { paraText } from '../model/doc'
import { LIMITS, clamp } from '../model/limits'
import { resolveChar } from '../model/identity'
import { applyChar, applyPara, charAt, kernAt, order, setParas, type Pos } from '../model/ops'
import type { CharAttrs, Para, ParaAttrs, Thread } from '../model/types'
import type { Store } from '../store/store'
import { caretAt, lineEls, offsetAtX } from './caret'
import { attrsOf, emptyAttrsOf, fromPM, locOf, markFor, paraAttrsOf, portableSlice, posOf, schema, toPM } from './pm'

const HIDDEN = 'position:fixed;left:0;top:0;width:1px;height:1em;opacity:0;overflow:hidden;white-space:pre-wrap;z-index:-1;pointer-events:none'
const SHOWN = 'white-space:pre-wrap;outline:none;min-height:100%;padding:12px 14px;font:15px/1.6 Georgia,serif;color:#e4e4e7'
// ⌘-arrows are the Mac's line and text edges; elsewhere ⌃-arrows move by word.
const MAC = typeof navigator !== 'undefined' && /Mac|iP(hone|ad|od)/.test(navigator.platform)

export class TextEditor {
  view: EditorView | null = null
  thread: string | null = null
  private paras: Para[] | null = null
  private goal: number | null = null
  private host: HTMLElement
  private store: Store
  private root: () => HTMLElement | null
  private unsubscribe: () => void

  constructor(store: Store, root: () => HTMLElement | null) {
    this.store = store
    this.root = root
    this.host = document.createElement('div')
    this.host.setAttribute('aria-label', 'Text')
    this.host.style.cssText = HIDDEN
    document.body.appendChild(this.host)
    this.unsubscribe = store.subscribe(() => this.sync())
  }

  destroy(): void {
    this.unsubscribe()
    this.view?.destroy()
    this.host.remove()
  }

  private threadObj(): Thread | undefined {
    return this.store.get().doc.threads.find((t) => t.id === this.thread)
  }

  /** Start typing in a thread, at a place (or with a range). */
  open(thread: string, at: Pos = [0, 0], head: Pos = at): void {
    const t = this.store.get().doc.threads.find((x) => x.id === thread)
    if (!t) return
    this.thread = thread
    this.paras = t.paras
    const doc = toPM(t.paras)
    const state = EditorState.create({ doc, plugins: [keymap(this.keys()), keymap(baseKeymap)] })
    const sel = TextSelection.create(doc, posOf(doc, at[0], at[1]), posOf(doc, head[0], head[1]))
    if (!this.view) {
      this.view = new EditorView(this.host, {
        state: state.apply(state.tr.setSelection(sel)),
        dispatchTransaction: (tr) => this.dispatch(tr),
        transformCopied: (slice, view) => portableSlice(slice, this.store.get().doc.identity, paraAttrsOf(view.state.selection.$from.parent)),
        attributes: { spellcheck: 'true', autocorrect: 'on' },
      })
    } else this.view.updateState(state.apply(state.tr.setSelection(sel)))
    this.view.focus()
    this.publish()
  }

  close(): void {
    this.thread = null
    this.paras = null
    this.view?.dom.blur()
    if (this.store.get().editing) this.store.set({ editing: null })
  }

  /** Show the view in a panel (the Story Editor), or hide it again. */
  showIn(container: HTMLElement | null): void {
    if (container) {
      container.appendChild(this.host)
      this.host.style.cssText = SHOWN
    } else {
      document.body.appendChild(this.host)
      this.host.style.cssText = HIDDEN
    }
  }

  focus(): void {
    this.view?.focus()
  }

  /** In the Story Editor (where the browser lays the text out). */
  private shown(): boolean {
    return this.host.style.position !== 'fixed'
  }

  /** Keep the hidden input at the caret (screen), so an IME's window opens there. */
  moveInput(x: number, y: number): void {
    if (this.host.style.position !== 'fixed') return
    this.host.style.left = `${x}px`
    this.host.style.top = `${y}px`
  }

  private dispatch(tr: Transaction): void {
    const view = this.view!
    let next = this.unkern(view.state.apply(tr), tr)
    const { $from, empty } = next.selection
    if (empty && !$from.parent.content.size && !next.storedMarks) {
      const ec = emptyAttrsOf($from.parent)
      if (Object.keys(ec).length) next = next.apply(next.tr.setStoredMarks(markFor(ec, !!this.currentPara().style)))
    }
    view.updateState(next)
    if (!tr.getMeta('keepGoal')) this.goal = null
    if (tr.docChanged && this.thread) {
      const paras = fromPM(next.doc)
      this.paras = paras
      const thread = this.thread
      this.store.edit((d) => setParas(d, thread, paras), { key: `type:${thread}`, extra: { editing: this.selection() } })
    } else this.publish()
  }

  /** Characters typed after a kerned one don't take its kerning: it is the
   *  space after that one letter, set at the caret (⌥← ⌥→), not a look. */
  private unkern(next: EditorState, tr: Transaction): EditorState {
    if (!tr.docChanged || tr.getMeta('paste') || tr.getMeta('uiEvent') === 'paste') return next
    let fix = next.tr
    tr.mapping.maps.forEach((map, k) => map.forEach((_a, _b, start, end) => {
      const later = tr.mapping.slice(k + 1)
      const from = later.map(start, -1), to = later.map(end)
      if (to - from > 8 || to <= from) return
      next.doc.nodesBetween(from, to, (node, pos) => {
        if (!node.isText) return
        const attrs = attrsOf(node.marks)
        if (!attrs.kern) return
        const rest = { ...attrs }
        delete rest.kern
        const a = Math.max(from, pos), b = Math.min(to, pos + node.nodeSize)
        fix = fix.removeMark(a, b, schema.marks.ch)
        for (const mark of markFor(rest, !!this.currentPara().style)) fix = fix.addMark(a, b, mark)
      })
    }))
    return fix.docChanged ? next.apply(fix) : next
  }

  /** Manual kerning at the caret: the space after the character before it, by
   *  `step` thousandths of an em; with text selected, its tracking. */
  private kern(step: number): Command {
    return () => {
      const t = this.threadObj()
      const sel = this.selection()
      if (!t || !sel) return true
      const [a, b] = order(sel.anchor, sel.head)
      const identity = this.store.get().doc.identity
      const base = identity?.paragraphs.find((p) => p.id === t.paras[a[0]].style)?.char
      const thread = t.id
      if (a[0] !== b[0] || a[1] !== b[1]) {
        const cur = resolveChar(charAt(t.paras[a[0]], a[1] + 1), base, identity)
        const track = clamp(cur.track + step, LIMITS.TRACK_MIN, LIMITS.TRACK_MAX)
        this.store.edit((d) => setParas(d, thread, applyChar(t.paras, a, b, { track })), { key: `track:${thread}` })
        return true
      }
      this.kernCaret(step, false)
      return true
    }
  }

  /** The kerning after the character before the caret set to `value`; false
   *  when there is no caret (text is selected), so the selection takes it. */
  kernTo(value: number): boolean {
    const sel = this.selection()
    if (!sel || sel.anchor[0] !== sel.head[0] || sel.anchor[1] !== sel.head[1]) return false
    this.kernCaret(value, true)
    return true
  }

  private kernCaret(step: number, absolute: boolean): void {
    const t = this.threadObj()
    const sel = this.selection()
    if (!t || !sel || !sel.head[1]) return
    const [p, o] = sel.head
    const identity = this.store.get().doc.identity
    const base = identity?.paragraphs.find((x) => x.id === t.paras[p].style)?.char
    const resolve = (r: CharAttrs) => resolveChar(r, base, identity)
    const thread = t.id
    this.store.edit((d) => setParas(d, thread, kernAt(t.paras, p, o, step, this.store.measure.width, resolve, absolute)),
      { key: `kern:${thread}`, extra: { editing: sel } })
  }

  private selection(): { thread: string; anchor: Pos; head: Pos } | null {
    if (!this.view || !this.thread) return null
    const { anchor, head } = this.view.state.selection
    return { thread: this.thread, anchor: locOf(this.view.state.doc, anchor), head: locOf(this.view.state.doc, head) }
  }

  private publish(): void {
    this.store.set({ editing: this.selection() })
  }

  /** The store's paragraphs changed under the view (undo, a panel): show them. */
  private sync(): void {
    if (!this.view || !this.thread) return
    const t = this.threadObj()
    if (!t) return this.close()
    if (t.paras === this.paras) return
    this.paras = t.paras
    const sel = this.selection()!
    const doc = toPM(t.paras)
    const state = EditorState.create({ doc, plugins: this.view.state.plugins })
    const clamp = ([p, o]: Pos): number => posOf(doc, Math.min(p, doc.childCount - 1), o)
    this.view.updateState(state.apply(state.tr.setSelection(TextSelection.create(doc, clamp(sel.anchor), clamp(sel.head)))))
    this.store.set({ editing: this.selection() })
  }

  // ── type from the panels ───────────────────────────────────────────────────

  /** The type at the caret (what typing would take), or of the selection's start. */
  currentChar(): CharAttrs {
    const view = this.view
    if (!view) return {}
    if (view.state.storedMarks) return attrsOf(view.state.storedMarks)
    const { $from } = view.state.selection
    if (!$from.parent.content.size) return emptyAttrsOf($from.parent)
    const t = this.threadObj()
    const [p, o] = locOf(view.state.doc, view.state.selection.from)
    return t ? charAt(t.paras[p], o) : {}
  }

  currentPara(): ParaAttrs {
    const t = this.threadObj()
    const sel = this.selection()
    if (!t || !sel) return {}
    const attrs: ParaAttrs & { runs?: unknown } = { ...t.paras[sel.head[0]] }
    delete attrs.runs
    return attrs
  }

  applyChar(attrs: CharAttrs): void {
    const t = this.threadObj()
    const sel = this.selection()
    if (!t || !sel || !this.view) return
    const [a, b] = order(sel.anchor, sel.head)
    if (a[0] === b[0] && a[1] === b[1] && paraText(t.paras[a[0]]).length) {
      // Nothing selected: the next characters typed take it.
      const merged = { ...('style' in attrs ? {} : this.currentChar()), ...attrs }
      if ('color' in attrs && !('swatch' in attrs)) delete merged.swatch
      this.view.dispatch(this.view.state.tr.setStoredMarks(markFor(merged, !!this.currentPara().style)))
      return
    }
    const thread = t.id
    this.store.edit((d) => setParas(d, thread, applyChar(t.paras, a, b, attrs)), { key: null })
    this.view.focus()
  }

  applyPara(attrs: ParaAttrs): void {
    const t = this.threadObj()
    const sel = this.selection()
    if (!t || !sel) return
    const thread = t.id
    this.store.edit((d) => setParas(d, thread, applyPara(t.paras, sel.anchor[0], sel.head[0], attrs)), { key: null })
    this.view?.focus()
  }

  // ── keys ───────────────────────────────────────────────────────────────────

  private keys(): Record<string, Command> {
    const toggle = (key: keyof CharAttrs, on: unknown, off: unknown): Command => () => {
      const identity = this.store.get().doc.identity
      const base = identity?.paragraphs.find((p) => p.id === this.currentPara().style)?.char
      const cur = resolveChar(this.currentChar(), base, identity)
      this.applyChar({ [key]: cur[key as keyof typeof cur] === on ? off : on } as CharAttrs)
      return true
    }
    return {
      Enter: splitParagraph,
      'Shift-Enter': (state, dispatch) => { dispatch?.(state.tr.insertText('\n').scrollIntoView()); return true },
      Tab: (state, dispatch) => { dispatch?.(state.tr.insertText(' ')); return true },
      'Mod-b': toggle('wt', 700, 400),
      'Mod-i': toggle('it', true, false),
      'Mod-u': toggle('u', true, false),
      'Mod-z': () => { this.store.undo(); return true },
      // Kerning, as InDesign keys it: tighter or looser by 10, by 50 with ⌘ (Ctrl).
      'Alt-ArrowLeft': this.kern(-10),
      'Alt-ArrowRight': this.kern(10),
      'Alt-Mod-ArrowLeft': this.kern(-50),
      'Alt-Mod-ArrowRight': this.kern(50),
      'Shift-Mod-z': () => { this.store.redo(); return true },
      Escape: () => {
        const frame = this.threadObj()?.frames[0]
        this.close()
        if (frame) this.store.set({ selection: [frame], tool: 'select' })
        return true
      },
      // The page's lines; the Story Editor's own lines are the browser's.
      ArrowUp: () => this.vertical(-1, false),
      ArrowDown: () => this.vertical(1, false),
      'Shift-ArrowUp': () => this.vertical(-1, true),
      'Shift-ArrowDown': () => this.vertical(1, true),
      Home: () => this.lineEdge(false, false),
      End: () => this.lineEdge(true, false),
      'Shift-Home': () => this.lineEdge(false, true),
      'Shift-End': () => this.lineEdge(true, true),
      // The line and text edges by the composed lines, not the hidden input's.
      ...(MAC ? {
        'Mod-ArrowLeft': () => this.lineEdge(false, false),
        'Mod-ArrowRight': () => this.lineEdge(true, false),
        'Shift-Mod-ArrowLeft': () => this.lineEdge(false, true),
        'Shift-Mod-ArrowRight': () => this.lineEdge(true, true),
        'Mod-ArrowUp': () => this.textEdge(false, false),
        'Mod-ArrowDown': () => this.textEdge(true, false),
        'Shift-Mod-ArrowUp': () => this.textEdge(false, true),
        'Shift-Mod-ArrowDown': () => this.textEdge(true, true),
      } : {
        'Ctrl-Home': () => this.textEdge(false, false),
        'Ctrl-End': () => this.textEdge(true, false),
        'Shift-Ctrl-Home': () => this.textEdge(false, true),
        'Shift-Ctrl-End': () => this.textEdge(true, true),
      }),
    }
  }

  private setHead(pos: Pos, extend: boolean, keepGoal = false): boolean {
    const view = this.view!
    const doc = view.state.doc
    const head = posOf(doc, pos[0], pos[1])
    const sel = extend ? TextSelection.create(doc, view.state.selection.anchor, head) : TextSelection.create(doc, head)
    const tr = view.state.tr.setSelection(sel).scrollIntoView()
    if (keepGoal) tr.setMeta('keepGoal', true)
    view.dispatch(tr)
    return true
  }

  /** Up or down a composed line, keeping the caret's x. */
  vertical(dir: 1 | -1, extend: boolean): boolean {
    if (this.shown()) return false
    const t = this.threadObj()
    const root = this.root()
    const sel = this.selection()
    if (!t?.comp || !root || !sel) return false
    const here = caretAt(root, t, sel.head[0], sel.head[1])
    if (!here) return false
    const goal = this.goal ?? here.x
    const k = here.k + dir
    const lines = t.comp.lines
    if (k < 0) return this.setHead([0, 0], extend)
    if (k >= lines.length) {
      const last = lines[lines.length - 1]
      return this.setHead([last[1], last[3]], extend)
    }
    const el = lineEls(root, t.id).get(k)
    const [, p, s] = lines[k]
    const off = el ? s + offsetAtX(el, goal) : s
    this.setHead([p, off], extend, true)
    this.goal = goal
    return true
  }

  /** To the start or end of the composed line. */
  lineEdge(end: boolean, extend: boolean): boolean {
    if (this.shown()) return false
    const t = this.threadObj()
    const sel = this.selection()
    const root = this.root()
    if (!t?.comp || !sel || !root) return false
    const here = caretAt(root, t, sel.head[0], sel.head[1])
    if (!here) return false
    const [, p, s, e] = t.comp.lines[here.k]
    return this.setHead([p, end ? e : s], extend)
  }

  /** To the start or end of the whole text. */
  textEdge(end: boolean, extend: boolean): boolean {
    if (this.shown()) return false
    const t = this.threadObj()
    if (!t || !this.view) return false
    const last = t.paras.length - 1
    return this.setHead(end ? [last, paraText(t.paras[last]).length] : [0, 0], extend)
  }

  /** Put the caret at a place (a click), or extend to it (a drag, Shift-click). */
  place(pos: Pos, extend = false): void {
    if (!this.view) return
    this.setHead(pos, extend)
    this.view.focus()
  }
}

/** Enter: a new paragraph, with this one's attributes and the type at the caret. */
const splitParagraph: Command = (state, dispatch) => {
  const { $from } = state.selection
  if (!dispatch) return true
  const tr = state.tr
  if (!state.selection.empty) tr.deleteSelection()
  const pos = tr.mapping.map($from.pos)
  const at = tr.doc.resolve(pos)
  const marks = state.storedMarks ?? at.marks()
  const ec = JSON.stringify(marks.length ? attrsOf(marks) : emptyAttrsOf($from.parent))
  tr.split(pos, 1, [{ type: schema.nodes.paragraph, attrs: { pa: $from.parent.attrs.pa, ec } }])
  dispatch(tr.scrollIntoView())
  return true
}
