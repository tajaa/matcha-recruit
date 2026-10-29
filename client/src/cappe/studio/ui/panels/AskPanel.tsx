import { useEffect, useRef, useState, type ClipboardEvent, type DragEvent, type KeyboardEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ArrowUp, BookOpen, CircleStop, ImagePlus, Loader2, RotateCcw, Sparkles, Undo2, Upload, WandSparkles, X } from 'lucide-react'
import { useStudio } from '../../store/store'
import type { AskLink } from '../../api'
import { COMMANDS } from '../commands'
import { useCtx } from '../context'
import { GUIDE } from '../guideContent'
import { conversation, MAX_QUESTION, MERLIN_ROUNDS, MERLIN_SUGGESTIONS, preparePicture, SUGGESTIONS, useConversation,
  type Picture, type Turn } from '../ask/conversation'

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

const STAGE = { looking: 'Looking at your page…', designing: 'Designing…', applying: 'Making the changes…' } as const

/** What Merlin did with a request: each round's words and changes, what it
 *  is doing now (with Stop), and Undo Merlin while one undo takes it all back. */
function MerlinView({ turn, last, onRetry }: { turn: Turn; last: boolean; onRetry: () => void }) {
  const c = useCtx()
  const conv = conversation(c.store)
  const run = turn.merlin!
  // Redrawn as the document changes: Undo Merlin is offered only while nothing else has.
  const changes = useStudio(c.store, () => c.store.changes)
  const made = run.rounds.reduce((n, r) => n + r.did, 0)
  const canUndo = !run.stage && !run.undone && run.changes !== null && run.changes === changes
  return (
    <div className="space-y-2">
      {run.rounds.map((r, k) => (
        <div key={k}>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-violet-300">Merlin · round {k + 1}</p>
          {r.say && <Answer text={r.say} />}
          <p className="mt-0.5 text-[10px] text-zinc-500">
            {r.did ? `${r.did} change${r.did === 1 ? '' : 's'}` : 'No changes'}
            {r.skipped ? ` · ${r.skipped} it couldn’t make` : ''}
          </p>
        </div>
      ))}
      {run.stage && (
        <p role="status" className="flex items-center gap-1.5 text-xs text-zinc-400">
          <Loader2 className="h-3 w-3 animate-spin" />
          {run.stopped ?? <>{STAGE[run.stage]} <span className="text-zinc-600">Round {Math.min(run.rounds.length + 1, MERLIN_ROUNDS)} of {MERLIN_ROUNDS}</span></>}
          {!run.stopped && (
            <button type="button" onClick={() => conv.stop()}
              className="ml-auto inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-zinc-300 hover:bg-zinc-800 hover:text-white">
              <CircleStop className="h-3 w-3" />Stop
            </button>
          )}
        </p>
      )}
      {!run.stage && run.stopped && <p className="text-xs text-amber-300">{run.stopped}</p>}
      {turn.error && (
        <p role="alert" className="text-xs text-red-300">
          {turn.error}{' '}
          {last && <button type="button" onClick={onRetry} className="text-emerald-400 hover:text-emerald-300">Try again</button>}
        </p>
      )}
      {!run.stage && (made > 0 || run.undone || (!turn.error && !run.stopped)) && (
        <div className="flex items-center gap-2 text-[11px] text-zinc-400">
          <span>{run.undone ? 'Undone: your page is as it was.' : made ? `Merlin made ${made} change${made === 1 ? '' : 's'}.` : 'Merlin left the page as it was.'}</span>
          {canUndo && (
            <button type="button" onClick={() => conv.undoMerlin(c, turn.id)}
              className="ml-auto inline-flex items-center gap-1 rounded border border-zinc-700 px-2 py-0.5 text-zinc-200 hover:border-violet-400 hover:text-white">
              <Undo2 className="h-3 w-3" />Undo Merlin
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function TurnView({ turn, last, onRetry }: { turn: Turn; last: boolean; onRetry: () => void }) {
  return (
    <div className="space-y-2">
      <div className={`ml-6 rounded-lg px-3 py-2 text-xs text-zinc-100 ${turn.merlin ? 'bg-violet-950/60' : 'bg-zinc-800'}`}>
        {(turn.picture || (turn.merlin && turn.current)) && (
          <div className="mb-2 flex items-end gap-2">
            {turn.picture && (
              <figure className="min-w-0">
                <img src={turn.picture.preview} alt="Your reference picture" className="max-h-24 rounded" />
                <figcaption className="mt-0.5 text-[10px] text-zinc-500">The look you want</figcaption>
              </figure>
            )}
            {turn.current && (
              <figure className="min-w-0">
                <img src={turn.current.preview} alt={turn.merlin ? 'Your page before Merlin' : 'Your design, as sent'}
                  className="max-h-24 rounded border border-zinc-700" />
                <figcaption className="mt-0.5 text-[10px] text-zinc-500">{turn.merlin ? 'Before' : 'Yours now'}</figcaption>
              </figure>
            )}
          </div>
        )}
        <p className="whitespace-pre-wrap">{turn.q}</p>
      </div>
      {turn.merlin ? <MerlinView turn={turn} last={last} onRetry={onRetry} /> : <AskView turn={turn} last={last} onRetry={onRetry} />}
    </div>
  )
}

function AskView({ turn, last, onRetry }: { turn: Turn; last: boolean; onRetry: () => void }) {
  return (
    <>
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
    </>
  )
}

/** Ask the Studio: questions about using the Studio or about the page in
 *  view, answered from the guide and the page (ui/ask/conversation.ts).
 *  Answers explain; the person makes every change. In Merlin mode the
 *  request is designed instead: Merlin changes the page itself. */
export function AskPanel() {
  const c = useCtx()
  const conv = conversation(c.store)
  const { turns, busy, focus, draft, mode } = useConversation(c.store)
  const merlin = mode === 'merlin'
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
    void (merlin ? conv.design(c, q, picture) : conv.ask(c, q, picture))
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
            {merlin ? (
              <>
                <p>Merlin designs the page in view for you. Say what you want, or drop a picture of a look you like: Merlin makes the changes, looks at the result and refines it, up to three times.</p>
                <p>It restyles, moves and adds, but never writes your story’s words or deletes anything. One ⌘Z, or Undo Merlin, takes the whole design back.</p>
              </>
            ) : (
              <>
                <p>Ask how to do something in the Studio, or how to make this page look the way you want.</p>
                <p>To match a look: select the part of your page, then drop, paste or attach a screenshot of a magazine you like and ask how to make yours look like it.</p>
              </>
            )}
            {(merlin ? MERLIN_SUGGESTIONS : SUGGESTIONS).map((q) => (
              // Ask answers straight away; Merlin changes the page, so its suggestion only fills the box.
              <button key={q} type="button" onClick={() => (merlin ? conv.prompt(q) : send(q))} disabled={busy || preparing}
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
        <div role="radiogroup" aria-label="What happens when you send" className="mb-1.5 flex rounded-md bg-zinc-900 p-0.5 text-[11px]">
          {([['ask', 'Ask', 'Answers: you make the changes'], ['merlin', 'Merlin', 'Merlin makes the changes for you']] as const).map(([m, label, hint]) => (
            <button key={m} type="button" role="radio" aria-checked={mode === m} title={hint} disabled={busy}
              onClick={() => conv.setMode(m)}
              className={`flex flex-1 items-center justify-center gap-1 rounded px-2 py-1 disabled:opacity-60 ${mode === m
                ? m === 'merlin' ? 'bg-violet-600 text-white' : 'bg-zinc-700 text-white' : 'text-zinc-400 hover:text-white'}`}>
              {m === 'merlin' ? <WandSparkles className="h-3 w-3" /> : <Sparkles className="h-3 w-3" />}{label}
            </button>
          ))}
        </div>
        <div className={`flex items-end gap-1.5 rounded-md border bg-zinc-950 px-2 py-1.5 ${merlin ? 'border-violet-700 focus-within:border-violet-400' : 'border-zinc-700 focus-within:border-emerald-500'}`}>
          <textarea ref={box} value={text} rows={2} maxLength={MAX_QUESTION} aria-label={merlin ? 'What Merlin should design' : 'Your question'}
            placeholder={merlin ? 'Tell Merlin what to design…' : 'How do I…?'} onChange={(e) => setText(e.target.value)} onKeyDown={onKey} onPaste={onPaste}
            className="max-h-32 min-h-[2.5rem] flex-1 resize-none bg-transparent text-xs text-zinc-100 placeholder:text-zinc-600 focus:outline-none" />
          <input ref={file} type="file" accept={PICTURE_TYPES.join(',')} className="hidden" aria-label="Attach a picture"
            onChange={(e) => { void attach(e.target.files?.[0]); e.target.value = '' }} />
          <button type="button" onClick={() => file.current?.click()} aria-label="Attach a picture" title="Attach a picture of the look you want"
            className="rounded p-1 text-zinc-400 hover:bg-zinc-800 hover:text-white"><ImagePlus className="h-4 w-4" /></button>
          <button type="button" onClick={() => send()} disabled={busy || preparing || !text.trim()} aria-label={merlin ? 'Design it' : 'Ask'}
            className={`rounded p-1 text-white disabled:opacity-40 ${merlin ? 'bg-violet-600 hover:bg-violet-500' : 'bg-emerald-600 hover:bg-emerald-500'}`}>
            {merlin ? <WandSparkles className="h-4 w-4" /> : <ArrowUp className="h-4 w-4" />}
          </button>
        </div>
        <p className="mt-1 px-1 text-[10px] text-zinc-600">{merlin
          ? 'Merlin uses AI and changes your page as it works. Check what it did; Undo Merlin or ⌘Z takes it back.'
          : 'Answers come from AI and can be wrong. Nothing on your page changes until you change it.'}</p>
      </div>
    </section>
  )
}
