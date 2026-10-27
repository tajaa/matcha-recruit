// Ask the Studio's conversation (server/app/cappe/services/magazine/studio/
// ask.py). It belongs to the Studio, not the panel, so closing the panel
// keeps it and an answer still arrives while the panel is shut. Each question
// goes with the guide, the commands, the page in view and the last few turns;
// nothing is saved on the server.

import { useSyncExternalStore } from 'react'
import { CappeApiError } from '../../../api'
import { studioApi, type AskLink, type AskRequest } from '../../api'
import type { State, Store } from '../../store/store'
import { COMMANDS } from '../commands'
import type { StudioCtx } from '../context'
import { GUIDE, MORE_KEYS } from '../guideContent'
import { clip, describeStudio } from './describe'

export const MAX_QUESTION = 1_000
const HISTORY = 6
const TURN_CHARS = 4_000
const PICTURE_SIDE = 1_280

/** What the empty panel offers to ask. */
export const SUGGESTIONS = [
  'How do I make text flow into another frame?',
  'Make this page look more like a fashion magazine',
  'How do I cut the background out of a picture?',
]

/** Commands the model isn't told about: asking itself, and leaving. */
const UNSENT = new Set(['ask', 'ask-about', 'close'])

export type Picture = { media_type: 'image/jpeg'; data: string; preview: string }
export type Turn = { id: number; q: string; picture: Picture | null; a: string | null; links: AskLink[]; error: string | null }
/** `draft`: words to put in the question box (`n` counts each, so the same words twice still land). */
export type AskState = { turns: Turn[]; busy: boolean; focus: number; draft: { text: string; n: number } | null }

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

function message(err: unknown): string {
  if (err instanceof CappeApiError && err.status === 429) return 'You’ve asked as much as you can for today. Try again tomorrow.'
  return err instanceof Error && err.message ? err.message : 'The Studio couldn’t answer that. Try again.'
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

export class Conversation {
  private state: AskState = { turns: [], busy: false, focus: 0, draft: null }
  private listeners = new Set<() => void>()
  private next = 1

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

  /** Ask the text box to take the keyboard (the panel listens). */
  focus(): void {
    this.set({ focus: this.state.focus + 1 })
  }

  /** Start a question with these words, for the person to finish (and give a picture to). */
  prompt(text: string): void {
    this.set({ draft: { text, n: (this.state.draft?.n ?? 0) + 1 }, focus: this.state.focus + 1 })
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
    const history = this.state.turns.filter((t) => t.a).slice(-HISTORY)
      .map((t) => ({ q: t.q, a: clip(t.a ?? '', TURN_CHARS) }))
    const id = this.next++
    this.set({ busy: true, turns: [...this.state.turns, { id, q, picture, a: null, links: [], error: null }] })
    const s = c.store.get()
    try {
      const res = await studioApi.ask(c.siteId, c.postId, {
        question: q, history, guide: guidePayload(), commands: commandsPayload(s), page: describeStudio(s),
        picture: picture ? { media_type: picture.media_type, data: picture.data } : null,
      })
      this.patchTurn(id, { a: res.answer, links: res.links })
    } catch (err) {
      this.patchTurn(id, { error: message(err) })
    } finally {
      this.set({ busy: false })
    }
  }

  /** Ask the last question again, after it failed. */
  async retry(c: StudioCtx): Promise<void> {
    const last = this.state.turns[this.state.turns.length - 1]
    if (!last?.error || this.state.busy) return
    this.set({ turns: this.state.turns.slice(0, -1) })
    await this.ask(c, last.q, last.picture)
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
