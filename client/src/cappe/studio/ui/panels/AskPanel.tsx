import { useEffect, useRef, useState, type ClipboardEvent, type DragEvent, type KeyboardEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ArrowUp, BookOpen, ImagePlus, Loader2, RotateCcw, Sparkles, Upload, X } from 'lucide-react'
import { useStudio } from '../../store/store'
import type { AskLink } from '../../api'
import { COMMANDS } from '../commands'
import { useCtx } from '../context'
import { GUIDE } from '../guideContent'
import { conversation, MAX_QUESTION, preparePicture, SUGGESTIONS, useConversation, type Picture, type Turn } from '../ask/conversation'

/** Commands an answer may name but never offers as a button: they take
 *  something away, so the person does them from the menus. */
const NO_BUTTON = new Set(['cut', 'delete', 'page-delete', 'close'])
const PICTURE_TYPES = ['image/jpeg', 'image/png', 'image/webp']

/** An answer's Markdown, sized for the 300 px panel. Links show as text: a
 *  click in the Studio never leaves it. A picture shows as its words, never
 *  loaded: an answer can't make the browser fetch an address it names. */
function Answer({ text }: { text: string }) {
  return (
    <div className="space-y-1.5 text-xs leading-relaxed text-zinc-200 [&_code]:rounded [&_code]:bg-black/40 [&_code]:px-1 [&_h1]:font-semibold [&_h2]:font-semibold [&_h3]:font-semibold [&_ol]:list-decimal [&_ol]:space-y-1 [&_ol]:pl-4 [&_strong]:font-semibold [&_strong]:text-white [&_ul]:list-disc [&_ul]:space-y-1 [&_ul]:pl-4">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
        a: ({ children }) => <span className="underline">{children}</span>,
        img: ({ alt }) => (alt ? <span className="italic text-zinc-400">[{alt}]</span> : null),
      }}>
        {text}
      </ReactMarkdown>
    </div>
  )
}

function Links({ links }: { links: AskLink[] }) {
  const c = useCtx()
  // Whether each command can run now, as one string, so a drag doesn't redraw the answers.
  const enabled = useStudio(c.store, (s) => links.map((l) => {
    const cmd = l.kind === 'command' ? COMMANDS.find((x) => x.id === l.id) : undefined
    return !cmd?.enabled || cmd.enabled(s) ? '1' : '0'
  }).join(''))
  const buttons = links.flatMap((l, i) => {
    if (l.kind === 'guide') {
      const section = GUIDE.find((g) => g.id === l.id)
      return section ? [{ key: `g:${l.id}`, label: `Guide: ${section.title}`, keys: '', guide: true, enabled: true,
        run: () => c.store.set({ guide: section.id }) }] : []
    }
    const cmd = COMMANDS.find((x) => x.id === l.id)
    if (!cmd || NO_BUTTON.has(cmd.id)) return []
    return [{ key: `c:${l.id}`, label: cmd.label, keys: cmd.keys ?? '', guide: false,
      enabled: enabled[i] === '1', run: () => cmd.run(c) }]
  })
  if (!buttons.length) return null
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {buttons.map((b) => (
        <button key={b.key} type="button" onClick={b.run} disabled={!b.enabled}
          title={b.enabled ? undefined : 'Not available right now: select what it works on first.'}
          className="inline-flex items-center gap-1 rounded border border-zinc-700 px-2 py-0.5 text-[11px] text-zinc-200 hover:border-emerald-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-40">
          {b.guide && <BookOpen className="h-3 w-3" />}{b.label}
          {b.keys && <span className="text-zinc-500">{b.keys}</span>}
        </button>
      ))}
    </div>
  )
}

function TurnView({ turn, last, onRetry }: { turn: Turn; last: boolean; onRetry: () => void }) {
  return (
    <div className="space-y-2">
      <div className="ml-6 rounded-lg bg-zinc-800 px-3 py-2 text-xs text-zinc-100">
        {turn.picture && (
          <div className="mb-2 flex items-end gap-2">
            <figure className="min-w-0">
              <img src={turn.picture.preview} alt="Your reference picture" className="max-h-24 rounded" />
              <figcaption className="mt-0.5 text-[10px] text-zinc-500">The look you want</figcaption>
            </figure>
            {turn.current && (
              <figure className="min-w-0">
                <img src={turn.current.preview} alt="Your design, as sent" className="max-h-24 rounded border border-zinc-700" />
                <figcaption className="mt-0.5 text-[10px] text-zinc-500">Yours now</figcaption>
              </figure>
            )}
          </div>
        )}
        <p className="whitespace-pre-wrap">{turn.q}</p>
      </div>
      {turn.a !== null && (
        <div>
          <Answer text={turn.a} />
          <Links links={turn.links} />
        </div>
      )}
      {turn.error && (
        <p role="alert" className="text-xs text-red-300">
          {turn.error}{' '}
          {last && <button type="button" onClick={onRetry} className="text-emerald-400 hover:text-emerald-300">Try again</button>}
        </p>
      )}
      {turn.a === null && !turn.error && (
        <p className="flex items-center gap-1.5 text-xs text-zinc-400"><Loader2 className="h-3 w-3 animate-spin" />Thinking…</p>
      )}
    </div>
  )
}

/** Ask the Studio: questions about using the Studio or about the page in
 *  view, answered from the guide and the page (ui/ask/conversation.ts).
 *  Answers explain; the person makes every change. */
export function AskPanel() {
  const c = useCtx()
  const conv = conversation(c.store)
  const { turns, busy, focus, draft } = useConversation(c.store)
  const [text, setText] = useState('')
  // Words "Ask about this" started the question with: put in the box once,
  // and taken, so closing and opening the panel doesn't put it back.
  const [seenDraft, setSeenDraft] = useState<typeof draft>(null)
  if (draft && draft !== seenDraft) {
    setSeenDraft(draft)
    setText(draft.text)
  }
  useEffect(() => {
    if (draft) conv.taken()
  }, [draft, conv])
  const [over, setOver] = useState(false)
  const [picture, setPicture] = useState<Picture | null>(null)
  const [pictureError, setPictureError] = useState<string | null>(null)
  // A picture being read and made smaller: Ask waits for it. Each attach
  // (and each send or removal) is a new generation; a late one is dropped.
  const [preparing, setPreparing] = useState(false)
  const generation = useRef(0)
  useEffect(() => () => { generation.current++ }, [])
  const box = useRef<HTMLTextAreaElement>(null)
  const list = useRef<HTMLDivElement>(null)
  const file = useRef<HTMLInputElement>(null)

  useEffect(() => { box.current?.focus() }, [focus])
  useEffect(() => {
    const el = list.current
    if (el) el.scrollTop = el.scrollHeight
  }, [turns])

  const send = (q = text) => {
    if (!q.trim() || busy || preparing) return
    void conv.ask(c, q, picture)
    conv.taken()
    setText('')
    setPicture(null)
    generation.current++
  }
  const dropPicture = () => {
    generation.current++
    setPicture(null)
    setPreparing(false)
  }
  const attach = async (f: File | null | undefined) => {
    setPictureError(null)
    if (!f) return
    if (!PICTURE_TYPES.includes(f.type)) { setPictureError('Attach a JPEG, PNG or WebP picture.'); return }
    const mine = ++generation.current
    setPicture(null)
    setPreparing(true)
    try {
      const ready = await preparePicture(f)
      if (generation.current === mine) setPicture(ready)
    } catch {
      if (generation.current === mine) setPictureError('That picture couldn’t be read.')
    } finally {
      if (generation.current === mine) setPreparing(false)
    }
  }
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send() }
  }
  const onPaste = (e: ClipboardEvent<HTMLTextAreaElement>) => {
    const pasted = [...e.clipboardData.files].find((f) => f.type.startsWith('image/'))
    if (pasted) { e.preventDefault(); void attach(pasted) }
  }
  const close = () => c.store.set((s) => ({ panels: s.panels.filter((p) => p !== 'ask') }))
  // A screenshot or a saved picture dropped anywhere on the panel is the reference.
  const files = (e: DragEvent) => [...e.dataTransfer.types].includes('Files')
  const dragOver = (e: DragEvent) => {
    if (!files(e)) return
    e.preventDefault()
    e.dataTransfer.dropEffect = 'copy'
    setOver(true)
  }
  const dragLeave = (e: DragEvent) => {
    if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOver(false)
  }
  const drop = (e: DragEvent) => {
    setOver(false)
    if (!files(e)) {
      // A picture dragged out of another web page comes as its address only.
      if ([...e.dataTransfer.types].includes('text/uri-list')) {
        e.preventDefault()
        setPictureError('Save that picture first, or copy it and paste it here.')
      }
      return
    }
    e.preventDefault()
    const f = [...e.dataTransfer.files].find((x) => x.type.startsWith('image/'))
    if (f) void attach(f)
    else setPictureError('Drop a JPEG, PNG or WebP picture.')
  }

  return (
    <section aria-label="Ask the Studio" onDragOver={dragOver} onDragLeave={dragLeave} onDrop={drop}
      className={`relative flex min-h-[380px] flex-1 flex-col border-b border-zinc-800 ${over ? 'ring-2 ring-inset ring-emerald-500' : ''}`}>
      {over && (
        <div aria-hidden className="pointer-events-none absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 bg-zinc-950/85 text-xs text-emerald-300">
          <Upload className="h-5 w-5" />Drop the picture of the look you want
        </div>
      )}
      <div className="flex items-center justify-between px-4 py-2">
        <h3 className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
          <Sparkles className="h-3 w-3 text-emerald-400" />Ask the Studio
        </h3>
        <div className="flex items-center gap-1">
          {turns.length > 0 && (
            <button type="button" onClick={() => conv.clear()} disabled={busy} aria-label="Start over" title="Start over"
              className="rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-white disabled:opacity-40"><RotateCcw className="h-3.5 w-3.5" /></button>
          )}
          <button type="button" onClick={close} aria-label="Close Ask the Studio" title="Close"
            className="rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-white"><X className="h-3.5 w-3.5" /></button>
        </div>
      </div>
      <div ref={list} className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 pb-3">
        {turns.length === 0 ? (
          <div className="space-y-2 text-xs text-zinc-400">
            <p>Ask how to do something in the Studio, or how to make this page look the way you want.</p>
            <p>To match a look: select the part of your page, then drop, paste or attach a screenshot of a magazine you like and ask how to make yours look like it.</p>
            {SUGGESTIONS.map((q) => (
              <button key={q} type="button" onClick={() => send(q)} disabled={busy || preparing}
                className="block w-full rounded border border-zinc-800 px-2.5 py-1.5 text-left text-zinc-300 hover:border-emerald-500 hover:text-white">{q}</button>
            ))}
          </div>
        ) : turns.map((t, i) => <TurnView key={t.id} turn={t} last={i === turns.length - 1} onRetry={() => void conv.retry(c)} />)}
      </div>
      <div className="border-t border-zinc-800 p-2">
        {picture && (
          <div className="mb-2 flex items-center gap-2">
            <img src={picture.preview} alt="The picture to send" className="h-10 rounded" />
            <button type="button" onClick={dropPicture} aria-label="Remove the picture"
              className="rounded p-0.5 text-zinc-400 hover:text-white"><X className="h-3.5 w-3.5" /></button>
          </div>
        )}
        {preparing && (
          <p role="status" className="mb-1 flex items-center gap-1 text-[11px] text-zinc-400">
            <Loader2 className="h-3 w-3 animate-spin" />Getting the picture ready…
            <button type="button" onClick={dropPicture} className="ml-1 underline hover:text-white">Cancel</button>
          </p>
        )}
        {pictureError && <p role="alert" className="mb-1 text-[11px] text-red-300">{pictureError}</p>}
        {!picture && !preparing && (
          <button type="button" onClick={() => file.current?.click()}
            className="mb-2 flex w-full items-center justify-center gap-1.5 rounded-md border border-dashed border-zinc-700 px-2 py-1.5 text-[11px] text-zinc-400 hover:border-emerald-500 hover:text-white">
            <ImagePlus className="h-3.5 w-3.5" />Drop, paste or choose a picture of the look you want
          </button>
        )}
        <div className="flex items-end gap-1.5 rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1.5 focus-within:border-emerald-500">
          <textarea ref={box} value={text} rows={2} maxLength={MAX_QUESTION} aria-label="Your question"
            placeholder="How do I…?" onChange={(e) => setText(e.target.value)} onKeyDown={onKey} onPaste={onPaste}
            className="max-h-32 min-h-[2.5rem] flex-1 resize-none bg-transparent text-xs text-zinc-100 placeholder:text-zinc-600 focus:outline-none" />
          <input ref={file} type="file" accept={PICTURE_TYPES.join(',')} className="hidden" aria-label="Attach a picture"
            onChange={(e) => { void attach(e.target.files?.[0]); e.target.value = '' }} />
          <button type="button" onClick={() => file.current?.click()} aria-label="Attach a picture" title="Attach a picture of the look you want"
            className="rounded p-1 text-zinc-400 hover:bg-zinc-800 hover:text-white"><ImagePlus className="h-4 w-4" /></button>
          <button type="button" onClick={() => send()} disabled={busy || preparing || !text.trim()} aria-label="Ask"
            className="rounded bg-emerald-600 p-1 text-white hover:bg-emerald-500 disabled:opacity-40"><ArrowUp className="h-4 w-4" /></button>
        </div>
        <p className="mt-1 px-1 text-[10px] text-zinc-600">Answers come from AI and can be wrong. Nothing on your page changes until you change it.</p>
      </div>
    </section>
  )
}
