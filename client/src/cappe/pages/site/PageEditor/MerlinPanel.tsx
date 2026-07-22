import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { AlertCircle, Check, Eye, History, Image, Loader2, Lock, Paperclip, Pencil, Plus, Search, Sparkles, Trash2, Wand2, X } from 'lucide-react'
import { usePremium } from './DesignPrimitives'
import { dHead } from './styles'
import {
  MERLIN_MAX_WIDTH,
  MERLIN_MIN_WIDTH,
  MERLIN_TIERS,
  type MerlinStep,
  type MerlinTierChoice,
  type useMerlin,
} from './useMerlin'

/** Toolbar toggle only — the panel itself is `MerlinDrawer`, rendered by
 *  index.tsx as a flex sibling of the preview/canvas (same docking pattern as
 *  ThemeMenu/ThemeDrawer), so its width composes into the layout row instead
 *  of overlaying it. */
export function MerlinButton({ open, setOpen }: { open: boolean; setOpen: (fn: (o: boolean) => boolean) => void }) {
  return (
    <button
      onClick={() => setOpen((o) => !o)}
      className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium ${open ? 'border-emerald-500 text-emerald-400' : 'border-zinc-700 text-zinc-300 hover:bg-zinc-800'}`}
    >
      <Sparkles className="h-4 w-4" /> Merlin
    </button>
  )
}

/** Markdown, restyled for a 320-560px dark chat column. Merlin's prose is short
 *  but does use lists and inline code (field paths, color tokens), which read as
 *  literal asterisks and backticks when rendered raw. */
function Markdown({ children }: { children: string }) {
  return (
    <div className="space-y-1.5 [&_a]:text-emerald-400 [&_a]:underline [&_code]:rounded [&_code]:bg-black/30 [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-[11px] [&_li]:ml-4 [&_li]:list-disc [&_strong]:font-semibold">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  )
}

const STEP_ICONS = {
  ops: Wand2,
  screenshot: Eye,
  inspect: Search,
  critique: Eye,
  image: Image,
} as const

/** The agent loop's trace for a turn: what it applied, what it rendered, what
 *  it looked at. This is the visible difference between Merlin guessing and
 *  Merlin checking its own work, so it's shown rather than hidden behind a
 *  toggle — but compactly, above the reply it explains. */
function StepTrail({ steps, live }: { steps: MerlinStep[]; live?: boolean }) {
  if (!steps.length) return null
  return (
    <div className="mb-1.5 space-y-1 border-l border-zinc-700/70 pl-2">
      {steps.map((s, i) => {
        const Icon = STEP_ICONS[s.kind] ?? Wand2
        const last = live && i === steps.length - 1
        return (
          <div key={i} className="flex items-start gap-1.5 text-[11px] text-zinc-500">
            <Icon className={`mt-[2px] h-3 w-3 shrink-0 ${last ? 'text-emerald-400' : ''}`} />
            <div className="min-w-0">
              <span className={last ? 'text-zinc-300' : ''}>{s.label}</span>
              {s.image_url && (
                <a href={s.image_url} target="_blank" rel="noreferrer" className="mt-1 block">
                  <img
                    src={s.image_url}
                    alt="Rendered preview Merlin reviewed"
                    className="max-h-28 w-full rounded border border-zinc-700 object-cover object-top"
                  />
                </a>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

/** The conversation switcher. Conversations are per page and server-persisted,
 *  so this is the only way back to an older thread. */
function ConversationMenu({ merlin }: { merlin: ReturnType<typeof useMerlin> }) {
  const { conversations, conversationId, openConversation, newConversation, renameConversation, deleteConversation } = merlin
  const [listOpen, setListOpen] = useState(false)
  const [renaming, setRenaming] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const boxRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!listOpen) return
    const onDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setListOpen(false)
    }
    window.addEventListener('mousedown', onDown)
    return () => window.removeEventListener('mousedown', onDown)
  }, [listOpen])

  const current = conversations.find((c) => c.id === conversationId)

  return (
    <div ref={boxRef} className="relative">
      <button
        onClick={() => setListOpen((o) => !o)}
        className="flex max-w-[9rem] items-center gap-1 rounded p-0.5 text-[11px] text-zinc-400 hover:text-zinc-200"
        title="Conversations"
      >
        <History className="h-3.5 w-3.5 shrink-0" />
        <span className="truncate">{current?.title ?? 'New conversation'}</span>
      </button>
      {listOpen && (
        <div className="absolute right-0 z-20 mt-1 max-h-72 w-64 overflow-y-auto rounded-lg border border-zinc-700 bg-zinc-900 p-1 shadow-xl">
          <button
            onClick={() => { newConversation(); setListOpen(false) }}
            className="flex w-full items-center gap-1.5 rounded px-2 py-1.5 text-left text-xs text-emerald-400 hover:bg-zinc-800"
          >
            <Plus className="h-3.5 w-3.5" /> New conversation
          </button>
          {conversations.length > 0 && <div className="my-1 border-t border-zinc-800" />}
          {conversations.map((c) => (
            <div key={c.id} className="group flex items-center gap-1 rounded px-1 hover:bg-zinc-800">
              {renaming === c.id ? (
                <input
                  autoFocus
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onBlur={() => { void renameConversation(c.id, draft); setRenaming(null) }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') { void renameConversation(c.id, draft); setRenaming(null) }
                    if (e.key === 'Escape') setRenaming(null)
                  }}
                  className="min-w-0 flex-1 rounded border border-zinc-700 bg-zinc-950 px-1.5 py-1 text-xs text-zinc-100 outline-none focus:border-emerald-500"
                />
              ) : (
                <>
                  <button
                    onClick={() => { void openConversation(c.id); setListOpen(false) }}
                    className={`min-w-0 flex-1 truncate py-1.5 text-left text-xs ${c.id === conversationId ? 'font-medium text-emerald-300' : 'text-zinc-300'}`}
                  >
                    {c.title}
                  </button>
                  <button
                    onClick={() => { setRenaming(c.id); setDraft(c.title) }}
                    className="shrink-0 p-1 text-zinc-600 opacity-0 hover:text-zinc-200 group-hover:opacity-100"
                    title="Rename"
                  >
                    <Pencil className="h-3 w-3" />
                  </button>
                  <button
                    onClick={() => void deleteConversation(c.id)}
                    className="shrink-0 p-1 text-zinc-600 opacity-0 hover:text-red-400 group-hover:opacity-100"
                    title="Delete"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function MerlinDrawer({ merlin }: { merlin: ReturnType<typeof useMerlin> }) {
  const premium = usePremium()
  const {
    open, setOpen, messages, send, sending, error, tier, setTier, width, setWidth,
    newConversation, status, liveSteps,
    attachments, addAttachment, removeAttachment, attachmentUploading, attachmentError,
  } = merlin
  const [input, setInput] = useState('')
  const listRef = useRef<HTMLDivElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  // A locked tier could still be sitting in localStorage from a lapsed plan —
  // show it selected but send lite, matching what the server would clamp to.
  const tierLocked = (t: MerlinTierChoice) => !premium && MERLIN_TIERS.find((x) => x.id === t)?.premium === true

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(() => false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, setOpen])

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, sending])

  // Drag the left edge to resize. Listeners live on the window (not the
  // handle) so the drag survives the pointer outrunning the 4px strip.
  const startResize = (e: React.MouseEvent) => {
    e.preventDefault()
    const onMove = (ev: MouseEvent) => setWidth(window.innerWidth - ev.clientX)
    const onUp = () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      document.body.style.userSelect = ''
    }
    document.body.style.userSelect = 'none'
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  if (!open) return null

  const submit = () => {
    if (sending || !input.trim()) return
    send(input)
    setInput('')
  }

  return (
    <div
      className="relative flex shrink-0 flex-col overflow-hidden border-l border-zinc-800 bg-zinc-900"
      style={{ width }}
    >
      <div
        onMouseDown={startResize}
        title={`Drag to resize (${MERLIN_MIN_WIDTH}–${MERLIN_MAX_WIDTH}px)`}
        className="absolute inset-y-0 left-0 z-10 w-1 cursor-col-resize hover:bg-emerald-500/40"
      />
      <div className="flex items-center justify-between border-b border-zinc-800 p-3">
        <p className={dHead}>Merlin</p>
        <div className="flex items-center gap-1">
          <ConversationMenu merlin={merlin} />
          {messages.length > 0 && (
            <button onClick={newConversation} className="rounded p-0.5 text-zinc-500 hover:text-zinc-200" title="New conversation">
              <Plus className="h-4 w-4" />
            </button>
          )}
          <button onClick={() => setOpen(() => false)} className="rounded p-0.5 text-zinc-500 hover:text-zinc-200" title="Close (Esc)"><X className="h-4 w-4" /></button>
        </div>
      </div>

      <>
          <div ref={listRef} className="flex-1 space-y-3 overflow-y-auto p-3">
            {messages.length === 0 && (
              <p className="text-xs text-zinc-500">
                Tell Merlin what to change — "make the hero darker", "add an FAQ section", "swap the brand color for something warmer".
                Edits apply live to the preview; nothing saves until you hit Save. ⌘Z undoes a turn's edits
                (an AI-generated image applies as its own step, right after).
              </p>
            )}
            {messages.map((m, i) => (
              <div key={m.id ?? i} className={m.role === 'user' ? 'ml-6' : 'mr-2'}>
                {m.steps && <StepTrail steps={m.steps} />}
                {m.attachments && m.attachments.length > 0 && (
                  <div className="mb-1 flex flex-wrap justify-end gap-1">
                    {m.attachments.map((a, j) => (
                      <img key={j} src={a.url} alt="Attached" className="h-12 w-12 rounded border border-zinc-700 object-cover" />
                    ))}
                  </div>
                )}
                <div className={`rounded-lg px-3 py-2 text-sm ${m.role === 'user' ? 'bg-emerald-500/10 text-emerald-100' : 'bg-zinc-800 text-zinc-100'}`}>
                  {m.role === 'assistant' ? <Markdown>{m.content}</Markdown> : m.content}
                </div>
                {/* Ground truth beats the model's prose: it has claimed
                    effects it never produced, so say plainly when a turn
                    changed nothing. */}
                {m.noChanges && (
                  <p className="mt-1 text-[11px] font-medium text-amber-300/90">No changes applied.</p>
                )}
                {m.role === 'assistant' && m.tier && (
                  <p className="mt-0.5 text-[10px] text-zinc-600">
                    {m.routed ? 'Auto → ' : ''}
                    {MERLIN_TIERS.find((t) => t.id === m.tier)?.label ?? m.tier}
                  </p>
                )}
                {m.results && m.results.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {m.results.map((r, j) => (
                      <span
                        key={j}
                        className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] ${
                          r.ok ? 'border-emerald-700/40 bg-emerald-500/[0.08] text-emerald-300' : 'border-amber-700/40 bg-amber-500/[0.08] text-amber-300'
                        }`}
                      >
                        {r.ok ? <Check className="h-2.5 w-2.5" /> : <AlertCircle className="h-2.5 w-2.5" />}
                        {r.summary}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {sending && (
              <div className="mr-2">
                {/* On an agent turn the trace IS the progress indicator —
                    "Thinking…" for 90s with nothing else says less than
                    "Applied 4 changes / Rendered desktop preview". */}
                <StepTrail steps={liveSteps} live />
                <div className="flex items-center gap-2 rounded-lg bg-zinc-800 px-3 py-2 text-sm text-zinc-400">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" /> {status ?? 'Thinking…'}
                </div>
              </div>
            )}
            {error && <p className="text-xs text-red-400">{error}</p>}
          </div>

          <div className="border-t border-zinc-800 p-3">
            {/* Model tier. Lite is free on every plan; the rest need Pro/Business.
                Locked options stay visible (and selectable) — the server clamps
                to lite — so the upgrade path is discoverable instead of hidden. */}
            <div className="mb-2 flex rounded-lg border border-zinc-700 p-0.5">
              {MERLIN_TIERS.map((t) => {
                const locked = tierLocked(t.id)
                return (
                  <button
                    key={t.id}
                    onClick={() => setTier(t.id)}
                    title={locked ? `${t.hint} — Pro/Business only` : t.hint}
                    className={`flex flex-1 items-center justify-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium ${
                      tier === t.id ? 'bg-emerald-500 text-zinc-950' : 'text-zinc-400 hover:text-zinc-200'
                    }`}
                  >
                    {locked && <Lock className="h-2.5 w-2.5" />} {t.label}
                  </button>
                )
              })}
            </div>
            {tierLocked(tier) && (
              <p className="mb-2 text-[11px] text-amber-300/90">
                {MERLIN_TIERS.find((t) => t.id === tier)?.label} needs Pro or Business — running on Lite.
              </p>
            )}
            {attachments.length > 0 && (
              <div className="mb-2 flex flex-wrap gap-1.5">
                {attachments.map((a, i) => (
                  <div key={i} className="group relative">
                    <img src={a.url} alt="Attached" className="h-12 w-12 rounded border border-zinc-700 object-cover" />
                    <button
                      onClick={() => removeAttachment(i)}
                      className="absolute -right-1 -top-1 rounded-full bg-zinc-900 p-0.5 text-zinc-400 opacity-0 group-hover:opacity-100 hover:text-red-400"
                      title="Remove"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}
            {attachmentError && <p className="mb-1 text-[11px] text-red-400">{attachmentError}</p>}
            <div className="flex gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() } }}
                placeholder="Describe a change, or attach a photo…"
                rows={2}
                className="w-full resize-none rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
              />
            </div>
            <div className="mt-2 flex gap-2">
              <input
                ref={fileRef}
                type="file"
                accept="image/jpeg,image/png,image/gif,image/webp"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) void addAttachment(file)
                  e.target.value = ''
                }}
              />
              <button
                onClick={() => fileRef.current?.click()}
                disabled={attachmentUploading || attachments.length >= 4}
                title="Attach a photo — place it, use it as a style reference, or generate variations of it"
                className="flex items-center justify-center rounded-lg border border-zinc-700 px-3 py-1.5 text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
              >
                {attachmentUploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Paperclip className="h-4 w-4" />}
              </button>
              <button
                onClick={submit}
                disabled={sending || !input.trim()}
                className="flex-1 rounded-lg bg-emerald-500 px-3 py-1.5 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-50"
              >
                {sending ? 'Sending…' : 'Send'}
              </button>
            </div>
          </div>
      </>
    </div>
  )
}
