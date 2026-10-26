import { useMemo, useSyncExternalStore } from 'react'
import type { ReaderAnnotationBody, ReaderQuote } from './annotationTypes'

type CommentDraft = { quote: ReaderQuote | null; page: number; text: string }
type Request = { json: string; id: string }

/** Keep work across history navigation without persisting private words to
 * browser storage. Every account, story and view has its own draft and retries. */
class CommentDraftStore {
  private draft: CommentDraft | null = null
  private listeners = new Set<() => void>()
  private requests = new Map<string, string>()
  private warnBeforeUnload = (event: BeforeUnloadEvent) => {
    event.preventDefault()
    event.returnValue = ''
  }

  get = () => this.draft
  subscribe = (listener: () => void) => {
    this.listeners.add(listener)
    return () => { this.listeners.delete(listener) }
  }
  set = (draft: CommentDraft | null) => {
    if (this.draft === draft) return
    this.draft = draft
    // A history POP can unmount the reader. Keep the warning until the
    // retained work is saved or discarded, even on the magazine's own page.
    if (draft?.text.trim()) window.addEventListener('beforeunload', this.warnBeforeUnload)
    else window.removeEventListener('beforeunload', this.warnBeforeUnload)
    this.listeners.forEach((listener) => listener())
  }
  request = (body: ReaderAnnotationBody): Request => {
    const json = JSON.stringify(body)
    const id = this.requests.get(json) ?? crypto.randomUUID()
    this.requests.set(json, id)
    return { json, id }
  }
  complete = (request: Request, submitted: CommentDraft | null) => {
    if (this.requests.get(request.json) === request.id) this.requests.delete(request.json)
    // A different annotation or newer typing must never clear this draft.
    if (submitted && this.draft === submitted) this.set(null)
  }
  cancel = () => { this.set(null) }
  discard = () => {
    this.requests.clear()
    this.set(null)
  }
}

const drafts = new Map<string, Map<string, CommentDraftStore>>()

export function hasCommentDrafts(accountId: string) {
  return [...(drafts.get(accountId)?.values() ?? [])].some((store) => !!store.get()?.text.trim())
}

export function discardCommentDrafts(accountId: string) {
  drafts.get(accountId)?.forEach((store) => store.discard())
}

export function useCommentDraft(accountId: string, endpoint: string, view: ReaderAnnotationBody['view']) {
  const store = useMemo(() => {
    let account = drafts.get(accountId)
    if (!account) { account = new Map(); drafts.set(accountId, account) }
    const key = JSON.stringify([endpoint, view])
    let found = account.get(key)
    if (!found) { found = new CommentDraftStore(); account.set(key, found) }
    return found
  }, [accountId, endpoint, view])
  const draft = useSyncExternalStore(store.subscribe, store.get)
  return [draft, store] as const
}
