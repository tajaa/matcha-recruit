import { useEffect, useRef, useState } from 'react'
import { Highlighter, Loader2, MessageSquare, StickyNote, Trash2, Underline, X } from 'lucide-react'
import { cappeApi } from '../../api'
import BookFrame from './BookFrame'
import { jumpToAnnotation, pageAt, paintAnnotations, selectedQuote, selectionPageAt } from './annotations'
import type { ReaderAnnotation, ReaderAnnotationBody, ReaderQuote } from './annotationTypes'

const BUTTON = 'inline-flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-lg px-3 text-sm text-zinc-200 hover:bg-zinc-800 disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-lime-300'
const TOOL = 'inline-flex min-h-11 shrink-0 flex-col items-center justify-center gap-1 rounded-lg px-1 text-xs text-zinc-200 hover:bg-zinc-800 disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-lime-300 sm:flex-row sm:gap-2 sm:px-3 sm:text-sm'
const MAX_COMMENT = 4000

type Props = {
  html: string; title: string; endpoint: string; canAnnotate: boolean; asText: boolean
  prepare: (doc: Document) => void; onLink: (path: string) => void; onClose: () => void; onTextView: () => void
}

/** Native dialog supplies focus trapping, inert background and focus return.
 * Full viewport on phones; inset reading room with a notebook on desktop. */
export default function ReaderModal(props: Props) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [doc, setDoc] = useState<Document | null>(null)
  const [notes, setNotes] = useState<ReaderAnnotation[]>([])
  const [loaded, setLoaded] = useState(false)
  const [loadVersion, setLoadVersion] = useState(0)
  const [loadError, setLoadError] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [notebook, setNotebook] = useState(false)
  const [selection, setSelection] = useState<ReaderQuote | null>(null)
  const [page, setPage] = useState(1)
  const [selectedPage, setSelectedPage] = useState(1)
  const [draft, setDraft] = useState<{ quote: ReaderQuote | null; page: number; text: string } | null>(null)
  const [found, setFound] = useState<Set<string>>(new Set())
  const pending = useRef<{ json: string; id: string } | null>(null)
  const writing = useRef(false)
  const latest = useRef(props)
  useEffect(() => { latest.current = props })
  const draftRef = useRef(draft)
  useEffect(() => { draftRef.current = draft })
  const view = props.asText ? 'text' : 'pages'
  const currentNotes = notes.filter((n) => n.view === view)

  const leave = (action: () => void) => {
    if (draftRef.current?.text.trim() && !window.confirm('Discard your unsaved comment?')) return
    action()
  }
  const close = () => leave(() => latest.current.onClose())

  useEffect(() => {
    const el = dialog.current
    const previous = document.activeElement
    el?.showModal?.()
    if (el && !el.open) el.setAttribute('open', '')
    return () => { el?.close?.(); if (previous instanceof HTMLElement) previous.focus() }
  }, [])

  useEffect(() => {
    if (!props.canAnnotate) return
    let live = true
    cappeApi.get<{ annotations: ReaderAnnotation[] }>(props.endpoint)
      .then((r) => { if (live) { setNotes(r.annotations); setLoaded(true); setLoadError('') } })
      .catch((e) => { if (live) setLoadError(e instanceof Error ? e.message : 'Could not load your notes') })
    return () => { live = false }
  }, [props.endpoint, props.canAnnotate, loadVersion])

  useEffect(() => {
    if (!doc) return
    const frame = window.requestAnimationFrame(() => setFound(paintAnnotations(doc, notes.filter((n) => n.view === view))))
    return () => window.cancelAnimationFrame(frame)
  }, [doc, notes, view])

  useEffect(() => {
    if (!doc || !props.canAnnotate) return
    let lastPage = pageAt(doc)
    const timer = window.setInterval(() => {
      const next = pageAt(doc)
      if (next !== lastPage) {
        lastPage = next; setPage(next); setSelection(null); doc.getSelection()?.removeAllRanges()
      }
      const quote = selectedQuote(doc)
      // Keep the captured quote when focus moves to the outside toolbar.
      if (quote) {
        setSelection((s) => s?.start === quote.start && s.exact === quote.exact ? s : quote)
        setSelectedPage(selectionPageAt(doc))
      }
    }, 180)
    return () => window.clearInterval(timer)
  }, [doc, props.canAnnotate])

  async function save(body: ReaderAnnotationBody) {
    if (writing.current) return
    writing.current = true; setBusy(true); setError('')
    const json = JSON.stringify(body)
    if (pending.current?.json !== json) pending.current = { json, id: crypto.randomUUID() }
    try {
      const saved = await cappeApi.put<ReaderAnnotation>(`${props.endpoint}/${pending.current.id}`, body)
      setNotes((all) => [...all.filter((n) => n.id !== saved.id), saved])
      pending.current = null
      setDraft(null); setSelection(null); doc?.getSelection()?.removeAllRanges()
      setNotice(body.kind === 'comment' ? 'Comment saved.' : body.kind === 'highlight' ? 'Highlight saved.' : 'Underline saved.')
    } catch (e) {
      setError(`${e instanceof Error ? e.message : 'Could not confirm the save'}. Your selection and comment are kept; try again.`)
    } finally { writing.current = false; setBusy(false) }
  }

  async function remove(id: string) {
    if (writing.current) return
    writing.current = true; setBusy(true); setError('')
    try {
      await cappeApi.delete(`${props.endpoint}/${id}`)
      setNotes((all) => all.filter((n) => n.id !== id))
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not delete. Try again.') }
    finally { writing.current = false; setBusy(false) }
  }

  const mark = (kind: 'highlight' | 'underline') => {
    if (selection) void save({ kind, view, page: selectedPage, quote: selection, text: '' })
  }
  const ready = props.canAnnotate && loaded && !busy
  const hasTextView = props.asText || !!doc?.querySelector('.mz-paged')

  return (
    <dialog ref={dialog} aria-label={`${props.title} — magazine reader`} onCancel={(e) => { e.preventDefault(); close() }}
      className="fixed inset-0 m-0 h-dvh max-h-none w-screen max-w-none overflow-hidden border border-zinc-800 bg-zinc-950 p-0 text-zinc-100 shadow-2xl backdrop:bg-black/80 sm:inset-6 sm:m-auto sm:h-[calc(100dvh-3rem)] sm:w-[calc(100vw-3rem)] sm:max-w-[1440px] sm:rounded-2xl">
      <div className="flex h-full min-h-0 flex-col" style={{ paddingTop: 'env(safe-area-inset-top)', paddingBottom: 'env(safe-area-inset-bottom)' }}>
        <header className="flex shrink-0 items-center gap-3 border-b border-zinc-800 px-3 py-2 sm:px-5">
          <div className="min-w-0 flex-1"><p className="text-[10px] uppercase tracking-[.2em] text-zinc-500">Your reading room</p>
            <h1 className="truncate font-serif text-lg">{props.title}</h1></div>
          {hasTextView && <button type="button" className={BUTTON} onClick={() => leave(props.onTextView)}>{props.asText ? 'Designed pages' : 'Text view'}</button>}
          <button type="button" className={BUTTON} aria-label="Close reader" onClick={close} autoFocus><X className="h-5 w-5" /></button>
        </header>
        <div role="toolbar" aria-label="Reader annotations" className="grid shrink-0 grid-cols-4 items-center gap-1 border-b border-zinc-800 px-2 py-1 sm:flex sm:px-4">
          <button type="button" className={TOOL} disabled={!ready || !selection} onPointerDown={(e) => e.preventDefault()} onClick={() => mark('highlight')}><Highlighter className="h-4 w-4 text-yellow-300" />Highlight</button>
          <button type="button" className={TOOL} disabled={!ready || !selection} onPointerDown={(e) => e.preventDefault()} onClick={() => mark('underline')}><Underline className="h-4 w-4" />Underline</button>
          <button type="button" className={TOOL} disabled={!ready} onPointerDown={(e) => e.preventDefault()}
            onClick={() => { setDraft((d) => d ?? { quote: selection, page: selection ? selectedPage : page, text: '' }); setNotebook(true) }}><MessageSquare className="h-4 w-4" />Comment</button>
          <button type="button" className={`${TOOL} sm:ml-auto`} aria-pressed={notebook} onClick={() => setNotebook((v) => !v)}><StickyNote className="h-4 w-4" />Notes ({currentNotes.length})</button>
        </div>
        <div className="flex min-h-0 flex-1">
          <div className={`${notebook ? 'hidden md:flex' : 'flex'} min-h-0 min-w-0 flex-1 flex-col`}>
            <BookFrame html={props.html} title={props.title} prepare={(d) => {
              props.prepare(d)
              const style = d.createElement('style')
              style.textContent = '.cz-header,.cz-footer{display:none!important}'
              d.head.appendChild(style)
              setDoc(d)
            }} onLink={(path) => leave(() => props.onLink(path))} openExternal
              className="min-h-0 flex-1 [&_button]:min-h-11 [&_button]:min-w-11" style={{ minHeight: 0 }} />
          </div>
          {notebook && <aside aria-label="Your private notes" className="flex min-h-0 w-full shrink-0 flex-col border-l border-zinc-800 md:w-80 lg:w-96">
            <div className="flex items-center gap-2 border-b border-zinc-800 p-4"><div className="flex-1"><h2 className="text-sm font-medium">Your notebook</h2><p className="mt-1 text-xs text-zinc-500">Private to you · saved to your account</p></div>
              <button type="button" aria-label="Return to pages" className={BUTTON} onClick={() => setNotebook(false)}><X className="h-4 w-4" /></button></div>
            <div className="min-h-0 flex-1 overflow-y-auto p-4">
              {!props.canAnnotate && <p className="text-sm text-zinc-400">Subscribe to add highlights and private comments to this story.</p>}
              {props.canAnnotate && !loaded && !loadError && <p role="status" className="text-sm text-zinc-400">Loading your notes…</p>}
              {loadError && <div role="alert" className="text-sm text-red-300">{loadError}<button type="button" className={BUTTON} onClick={() => setLoadVersion((v) => v + 1)}>Retry loading</button></div>}
              {draft && <form className="mb-5" onSubmit={(e) => { e.preventDefault(); if (draft.text.trim()) void save({ kind: 'comment', view, ...draft }) }}>
                <label htmlFor="reader-comment" className="text-xs text-zinc-400">{draft.quote ? 'Comment on selected words' : `Comment on page ${draft.page}`}</label>
                {draft.quote && <blockquote className="my-2 line-clamp-4 border-l-2 border-yellow-300/50 pl-3 font-serif text-sm text-zinc-300">{draft.quote.exact}</blockquote>}
                <textarea id="reader-comment" autoFocus value={draft.text} onChange={(e) => setDraft({ ...draft, text: e.target.value })} rows={4}
                  className="mt-2 w-full rounded-lg border border-zinc-700 bg-zinc-900 p-3 text-sm focus:border-lime-300 focus:outline-none" placeholder="What would you like to remember?" />
                <p className="text-right text-xs text-zinc-500">{Array.from(draft.text).length}/{MAX_COMMENT}</p>
                <div className="mt-2 flex gap-2"><button type="submit" disabled={busy || !draft.text.trim() || Array.from(draft.text).length > MAX_COMMENT} className={`${BUTTON} bg-zinc-800`}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}Save comment</button>
                  <button type="button" className={BUTTON} disabled={busy} onClick={() => setDraft(null)}>Cancel</button></div>
              </form>}
              {loaded && !currentNotes.length && <p className="py-6 text-sm leading-relaxed text-zinc-500">Select words on a page, then choose Highlight, Underline or Comment. You can also comment on the page without selecting words.</p>}
              <ul className="space-y-4">{currentNotes.map((n) => <li key={n.id} className="border-b border-zinc-800 pb-4">
                <div className="flex items-center gap-2"><button type="button" className="min-h-11 flex-1 text-left text-xs capitalize text-zinc-400 hover:text-zinc-100"
                  onClick={() => { setNotebook(false); window.setTimeout(() => { if (doc) jumpToAnnotation(doc, n) }, 100) }}>{n.kind} · Page {n.page}</button>
                  <button type="button" className={BUTTON} aria-label={`Delete ${n.kind}`} disabled={busy} onClick={() => void remove(n.id)}><Trash2 className="h-4 w-4" /></button></div>
                {n.quote && <blockquote className="border-l-2 border-yellow-300/50 pl-3 font-serif text-sm leading-relaxed text-zinc-200">{n.quote.exact}</blockquote>}
                {n.text && <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-relaxed text-zinc-400">{n.text}</p>}
                {n.quote && !found.has(n.id) && <p className="mt-2 text-xs text-zinc-500">The text has changed. Your saved quote is kept here.</p>}
              </li>)}</ul>
            </div>
          </aside>}
        </div>
        {error && <p role="alert" className="shrink-0 border-t border-zinc-800 px-4 py-2 text-xs text-red-300">{error}</p>}
        <div role="status" className="flex min-h-9 shrink-0 items-center gap-2 border-t border-zinc-800 px-4 py-2 text-xs text-zinc-500">
          {busy ? 'Saving…' : selection ? <><span className="truncate">Selected: “{selection.exact}”</span><button type="button" className="ml-auto shrink-0 text-zinc-300" onClick={() => { setSelection(null); doc?.getSelection()?.removeAllRanges() }}>Clear</button></>
            : notice || (props.canAnnotate ? 'Swipe to turn pages. Select words to annotate; Comment adds a page note.' : 'Subscribe to read the whole story and save notes.')}
        </div>
      </div>
    </dialog>
  )
}
