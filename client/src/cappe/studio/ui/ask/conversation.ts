// Ask the Studio's conversation (server/app/cappe/services/magazine/studio/
// ask.py). It belongs to the Studio, not the panel, so closing the panel
// keeps it and an answer still arrives while the panel is shut. Each question
// goes with the guide, the commands, the page in view and the last few turns;
// nothing is saved on the server.
//
// In Merlin mode the request is designed, not answered (studio/merlin.py):
// up to three rounds, each a picture of the page and its description sent,
// edits back, checked and applied (ui/ask/merlinOps.ts). Every round after the
// first joins the first's undo step, so ⌘Z or Undo Merlin takes the whole
// design back; if anything else changes the document meanwhile, Merlin stops.

import { useSyncExternalStore } from 'react'
import { CappeApiError } from '../../../api'
import { studioApi, type AskLink, type AskRequest, type MerlinRequest } from '../../api'
import type { State, Store } from '../../store/store'
import { COMMANDS } from '../commands'
import type { StudioCtx } from '../context'
import { GUIDE, MORE_KEYS } from '../guideContent'
import { clip, describeStudio } from './describe'
import { applyOps, fitOps, type Applied, type Scope } from './merlinOps'
import { snapshot } from './snapshot'

export const MAX_QUESTION = 1_000
const HISTORY = 6
const TURN_CHARS = 4_000
const PICTURE_SIDE = 1_280
export const MERLIN_ROUNDS = 3
const MERLIN_NOTES = 60 // the server keeps this many notes a round

/** What the empty panel offers to ask. */
export const SUGGESTIONS = [
  'How do I make text flow into another frame?',
  'Make this page look more like a fashion magazine',
  'How do I cut the background out of a picture?',
]

/** What Merlin's empty panel offers to design. */
export const MERLIN_SUGGESTIONS = [
  'Make this page feel like a fashion magazine',
  'Give the headline more drama',
  'Tidy this page onto the margins and columns',
]

/** Commands the model isn't told about: asking itself, and leaving. */
const UNSENT = new Set(['ask', 'ask-about', 'merlin', 'close'])

export type Picture = { media_type: 'image/jpeg'; data: string; preview: string }
/** One of Merlin's rounds: what it said, how many edits took and how many it couldn't make. */
export type MerlinRound = { say: string; did: number; skipped: number }
export type MerlinRun = {
  rounds: MerlinRound[]
  /** What it is doing now; null once it has finished. */
  stage: 'looking' | 'designing' | 'applying' | null
  /** Why it stopped before it was done, if it did. */
  stopped: string | null
  /** `Store.changes` just after its last edit, or null when it changed nothing:
   *  while they are equal, nothing else has touched the document, and one undo
   *  takes Merlin's whole design back. */
  changes: number | null
  undone: boolean
}
/** `current`: the person's own design as it was drawn and sent beside their reference picture
 *  (for Merlin, the page before it started). `merlin`: a request Merlin designed. */
export type Turn = { id: number; q: string; picture: Picture | null; current?: Picture | null; a: string | null; links: AskLink[];
  error: string | null; merlin?: MerlinRun }
export type Mode = 'ask' | 'merlin'
/** `draft`: words to put in the question box (`n` counts each, so the same words twice still land). */
export type AskState = { turns: Turn[]; busy: boolean; focus: number; draft: { text: string; n: number } | null; mode: Mode }

/** What "Ask about this" starts the question with. */
export const MATCH_QUESTION = 'How can I make this look like the picture I’ve attached?'

/** The guide as the server takes it; the shortcuts section gets the keys
 *  that aren't commands (the commands carry their own). */
export function guidePayload(): AskRequest['guide'] {
  return GUIDE.map((s) => ({
    id: s.id, title: s.title, body: s.body ?? '',
    points: s.id === 'keys' ? MORE_KEYS.map(([k, what]) => `${k}: ${what}`) : (s.points ?? []),
  }))
}

export function commandsPayload(s: State): AskRequest['commands'] {
  return COMMANDS.filter((c) => !UNSENT.has(c.id))
    .map((c) => ({ id: c.id, label: c.label, keys: c.keys ?? '', enabled: c.enabled ? c.enabled(s) : true }))
}

function message(err: unknown, mode: Mode = 'ask'): string {
  if (err instanceof CappeApiError && err.status === 429) {
    return mode === 'merlin' ? 'Merlin has designed as much as it can for you today. Try again tomorrow.'
      : 'You’ve asked as much as you can for today. Try again tomorrow.'
  }
  return err instanceof Error && err.message ? err.message
    : mode === 'merlin' ? 'Merlin couldn’t design that. Try again.' : 'The Studio couldn’t answer that. Try again.'
}

const CHANGED = 'You changed the page while Merlin worked, so it stopped there.'

/** What a round tells the next one: a line for each edit made or not, and how
 *  many of each. Kept to what the server takes (`MERLIN_NOTES` lines, and as
 *  many `skipped`): a round of 40 edits that mostly missed can note more, and
 *  the next request would be refused. `took`: whether the page changed. */
export function roundNotes(took: boolean, out: Applied, dropped: number): { notes: string[]; did: number; skipped: number } {
  const notes = took ? [...out.did, ...out.skipped]
    : out.did.length ? ['None of these edits took: the page would hold more than a story can.', ...out.skipped] : [...out.skipped]
  if (dropped) notes.push(`${dropped} edit${dropped === 1 ? '' : 's'} couldn’t be used and ${dropped === 1 ? 'was' : 'were'} left out.`)
  const did = took ? out.did.length : 0
  return { notes: notes.slice(0, MERLIN_NOTES), did, skipped: Math.min(MERLIN_NOTES, notes.length - did) }
}

/** A picture, at most 1,280 px on its longest side, as a JPEG to send. */
export async function preparePicture(file: Blob): Promise<Picture> {
  const bitmap = await createImageBitmap(file)
  const k = Math.min(1, PICTURE_SIDE / Math.max(bitmap.width, bitmap.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(bitmap.width * k))
  canvas.height = Math.max(1, Math.round(bitmap.height * k))
  const g = canvas.getContext('2d')
  if (!g) throw new Error('This browser can’t read that picture.')
  g.fillStyle = '#fff' // a transparent PNG on white, not black
  g.fillRect(0, 0, canvas.width, canvas.height)
  g.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  bitmap.close()
  const preview = canvas.toDataURL('image/jpeg', 0.85)
  return { media_type: 'image/jpeg', data: preview.slice(preview.indexOf(',') + 1), preview }
}

/** A design under way: what each round sends, and what the rounds so far did. */
type Design = {
  turn: number; q: string; picture: Picture | null; history: { q: string; a: string }[]
  pageId: string; selection: string[]; scope: Scope
  previous: MerlinRequest['previous']; says: string[]; rounds: MerlinRound[]
  /** `Store.changes` after Merlin's last edit (or when it started), and whether it has made one. */
  mark: number; stepped: boolean
}

export class Conversation {
  private state: AskState = { turns: [], busy: false, focus: 0, draft: null, mode: 'ask' }
  private listeners = new Set<() => void>()
  private drafts = 0 // `draft.n`: still counting after a draft is taken
  private next = 1
  private halt = false
  private running: number | null = null
  private abort: AbortController | null = null
  /** The design that failed last, to carry on from. */
  private left: Design | null = null

  get = (): AskState => this.state

  subscribe = (fn: () => void): (() => void) => {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }

  private set(patch: Partial<AskState>): void {
    this.state = { ...this.state, ...patch }
    this.listeners.forEach((fn) => fn())
  }

  private patchTurn(id: number, patch: Partial<Turn>): void {
    this.set({ turns: this.state.turns.map((t) => (t.id === id ? { ...t, ...patch } : t)) })
  }

  private patchRun(id: number, patch: Partial<MerlinRun>): void {
    this.set({ turns: this.state.turns.map((t) => (t.id === id && t.merlin ? { ...t, merlin: { ...t.merlin, ...patch } } : t)) })
  }

  /** The last few answered turns, to go with the next request. */
  private history(): { q: string; a: string }[] {
    return this.state.turns.filter((t) => t.a).slice(-HISTORY).map((t) => ({ q: t.q, a: clip(t.a ?? '', TURN_CHARS) }))
  }

  /** Ask (answers) or Merlin (designs). */
  setMode(mode: Mode): void {
    if (mode !== this.state.mode) this.set({ mode, focus: this.state.focus + 1 })
  }

  /** Ask the text box to take the keyboard (the panel listens). */
  focus(): void {
    this.set({ focus: this.state.focus + 1 })
  }

  /** Start a question with these words, for the person to finish (and give a picture to). */
  prompt(text: string): void {
    this.set({ draft: { text, n: ++this.drafts }, focus: this.state.focus + 1 })
  }

  /** The draft went into the question box. */
  taken(): void {
    if (this.state.draft) this.set({ draft: null })
  }

  clear(): void {
    if (!this.state.busy) this.set({ turns: [] })
  }

  async ask(c: StudioCtx, question: string, picture: Picture | null = null): Promise<void> {
    const q = clip(question.trim(), MAX_QUESTION)
    if (!q || this.state.busy) return
    const history = this.history()
    const id = this.next++
    this.set({ busy: true, turns: [...this.state.turns, { id, q, picture, a: null, links: [], error: null }] })
    const s = c.store.get()
    try {
      // With a reference picture, a picture of theirs to compare it with (as
      // the page is when they ask; null when the browser can't draw it).
      const current = picture ? await snapshot(s, c.fonts, c.siteId) : null
      if (current) this.patchTurn(id, { current })
      const res = await studioApi.ask(c.siteId, c.postId, {
        question: q, history, guide: guidePayload(), commands: commandsPayload(s), page: describeStudio(s),
        picture: picture ? { media_type: picture.media_type, data: picture.data } : null,
        current: current ? { media_type: current.media_type, data: current.data } : null,
      })
      this.patchTurn(id, { a: res.answer, links: res.links })
    } catch (err) {
      this.patchTurn(id, { error: message(err) })
    } finally {
      this.set({ busy: false })
    }
  }

  /** Ask the last question again (or have Merlin try again), after it failed.
   *  A design that made changes before it failed carries on from the round
   *  that failed, in the same undo step, while nothing else has changed the
   *  page; else it starts again. */
  async retry(c: StudioCtx): Promise<void> {
    const last = this.state.turns[this.state.turns.length - 1]
    if (!last?.error || this.state.busy) return
    const left = this.left
    if (last.merlin && left?.turn === last.id && left.mark === c.store.changes) {
      this.patchTurn(last.id, { error: null })
      await this.rounds(c, left)
      return
    }
    // A design that made changes before it failed stays, with its Undo.
    if (!last.merlin?.rounds.length) this.set({ turns: this.state.turns.slice(0, -1) })
    await (last.merlin ? this.design(c, last.q, last.picture) : this.ask(c, last.q, last.picture))
  }

  /** Merlin designs the page in view: rounds of edits, each looked at before the next. */
  async design(c: StudioCtx, request: string, picture: Picture | null = null): Promise<void> {
    const q = clip(request.trim(), MAX_QUESTION)
    if (!q || this.state.busy) return
    const start = c.store.get()
    const pageId = start.doc.pages[start.page]?.id
    const id = this.next++
    const run: MerlinRun = { rounds: [], stage: null, stopped: null, changes: null, undone: false }
    const turn: Turn = { id, q, picture, a: null, links: [], error: null, merlin: run }
    if (!pageId) {
      // The box was emptied when this was sent: the turn keeps the words and picture.
      this.set({ turns: [...this.state.turns, { ...turn, error: 'There’s no page in view for Merlin to design.' }] })
      return
    }
    const history = this.history()
    this.set({ turns: [...this.state.turns, turn] })
    await this.rounds(c, {
      turn: id, q, picture, history, pageId, selection: start.selection,
      scope: { page: pageId, selection: start.selection,
        hasFamily: (family) => c.fonts.book.manifest.faces.some((f) => f.family === family) },
      previous: [], says: [], rounds: [], mark: c.store.changes, stepped: false,
    })
  }

  /** The rounds of a design from where `d` left off (`d.rounds.length` made). */
  private async rounds(c: StudioCtx, d: Design): Promise<void> {
    const id = d.turn
    this.halt = false
    this.running = id
    this.left = null
    this.abort = new AbortController()
    const signal = this.abort.signal
    this.set({ busy: true })
    this.patchRun(id, { stage: 'looking', stopped: null })
    const stop = (why: string) => this.patchRun(id, { stopped: why })
    try {
      for (let round = d.rounds.length + 1; round <= MERLIN_ROUNDS; round++) {
        const now = c.store.get()
        const page = now.doc.pages.findIndex((p) => p.id === d.pageId)
        if (page < 0) { stop('The page Merlin was designing is gone.'); break }
        // The page it started on, as it is now, with what was selected then.
        const s = { ...now, page, selection: d.selection.filter((sel) => now.doc.items.some((i) => i.id === sel)) }
        this.patchRun(id, { stage: 'looking' })
        const current = await snapshot(s, c.fonts, c.siteId, { whole: true })
        if (round === 1 && current) this.patchTurn(id, { current })
        if (this.halt) break
        this.patchRun(id, { stage: 'designing' })
        const res = await studioApi.merlin(c.siteId, c.postId, {
          request: d.q, round, history: d.history, page: describeStudio(s, { forMerlin: true }), previous: [...d.previous],
          selected: s.selection.length,
          picture: d.picture ? { media_type: d.picture.media_type, data: d.picture.data } : null,
          current: current ? { media_type: current.media_type, data: current.data } : null,
        }, signal)
        if (this.halt) break
        if (c.store.changes !== d.mark) { stop(CHANGED); break }
        this.patchRun(id, { stage: 'applying' })
        // The faces the edits set, loaded first, so the text is set in them.
        await c.fonts.ensureDoc(applyOps(c.store.get().doc, res.ops, d.scope).doc).catch(() => {})
        if (this.halt) break
        if (c.store.changes !== d.mark) { stop(CHANGED); break }
        const before = c.store.get().doc
        let out: Applied = { doc: before, did: [], skipped: [] }
        // Measured in the faces just loaded: an edit that would leave text overflowing is left out.
        c.store.edit((doc) => (out = fitOps(doc, res.ops, d.scope, c.store.measure)).doc, { join: d.stepped })
        const took = c.store.get().doc !== before
        if (took) {
          d.stepped = true
          d.mark = c.store.changes
        }
        const { notes, did, skipped } = roundNotes(took, out, res.dropped)
        d.previous.push({ say: res.say, notes, did, skipped })
        if (res.say) d.says.push(res.say)
        d.rounds = [...d.rounds, { say: res.say, did, skipped }]
        this.patchRun(id, { rounds: d.rounds, changes: d.stepped ? d.mark : null })
        // Edits that were all unusable are not "nothing to do": the next round can put them right.
        if (res.done || (!res.ops.length && !res.dropped)) break
      }
      if (this.halt) stop('Stopped.')
    } catch (err) {
      if (this.halt) stop('Stopped.')
      else {
        this.patchTurn(id, { error: message(err, 'merlin') })
        this.left = d // "Try again" carries on from here
      }
    } finally {
      if (d.says.length) this.patchTurn(id, { a: d.says.join(' ') })
      this.patchRun(id, { stage: null })
      this.running = null
      this.abort = null
      this.set({ busy: false })
    }
  }

  /** Stop Merlin now: a round asked for is called off and left unmade; what
   *  earlier rounds did stays. A round the server has started still counts. */
  stop(): void {
    if (this.running === null || this.halt) return
    this.halt = true
    this.patchRun(this.running, { stopped: 'Stopping…' })
    this.abort?.abort()
  }

  /** Take Merlin's design back: one undo, while nothing else has changed the page. */
  undoMerlin(c: StudioCtx, id: number): void {
    const run = this.state.turns.find((t) => t.id === id)?.merlin
    if (!run || run.undone || run.changes === null || run.stage || run.changes !== c.store.changes) return
    c.store.undo()
    this.patchRun(id, { undone: true })
  }
}

const all = new WeakMap<Store, Conversation>()

/** The Studio's conversation (one per Studio store). */
export function conversation(store: Store): Conversation {
  let conv = all.get(store)
  if (!conv) {
    conv = new Conversation()
    all.set(store, conv)
  }
  return conv
}

export function useConversation(store: Store): AskState {
  const conv = conversation(store)
  return useSyncExternalStore(conv.subscribe, conv.get, conv.get)
}
