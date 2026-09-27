import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Check, CircleDashed, Loader2, Lock, Send, Sparkles } from 'lucide-react'
import { useWorkBase } from '../../routes/WorkSurfaceContext'
import type {
  DecideShape,
  ScheduleConfig,
  ScheduleShape,
  SymChatDetail as Detail,
  SymChatMessage,
  SymChatParticipant,
  SymChatUpdate,
} from '../../api/matchaWork/symChat'
import { KIND_LABEL, STATUS_LABEL, fmtDate, fmtTime, resolutionText, statusClass } from './format'
import { useSymChatDetail } from './useSymChatDetail'

function Bar({ value, total }: { value: number; total: number }) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0
  return (
    <div className="h-1.5 w-full rounded-full bg-w-surface2">
      <div className="h-1.5 rounded-full bg-w-accent" style={{ width: `${pct}%` }} />
    </div>
  )
}

function ScheduleShapeView({ shape, config }: { shape: ScheduleShape; config: ScheduleConfig }) {
  return (
    <div className="space-y-3">
      <p className="text-xs text-w-dim">
        {config.duration_min} min on {fmtDate(config.date)}, between {fmtTime(config.window_start)} and{' '}
        {fmtTime(config.window_end)} ({config.timezone})
      </p>
      {shape.top_slots.length === 0 ? (
        <p className="text-sm text-w-faint">No times on the table yet.</p>
      ) : (
        <ul className="space-y-2">
          {shape.top_slots.map((slot) => (
            <li key={slot.start} className="space-y-1">
              <div className="flex items-center justify-between text-sm">
                <span className={slot.start === shape.best?.start ? 'font-medium text-w-text' : 'text-w-dim'}>
                  {fmtTime(slot.start)}–{fmtTime(slot.end)}
                </span>
                <span className="text-xs text-w-faint">{slot.count}/{shape.total} can make it</span>
              </div>
              <Bar value={slot.count} total={shape.total} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function DecideShapeView({ shape }: { shape: DecideShape }) {
  if (shape.options.length === 0) return <p className="text-sm text-w-faint">No options on the table yet.</p>
  return (
    <ul className="space-y-2">
      {shape.options.map((option) => (
        <li key={option.name} className="space-y-1">
          <div className="flex items-center justify-between gap-3 text-sm">
            <span className={`truncate ${option.name === shape.leading?.name ? 'font-medium text-w-text' : 'text-w-dim'}`}>
              {option.name}
            </span>
            <span className="shrink-0 text-xs text-w-faint">
              {option.ok}/{shape.total} in
              {option.top > 0 && ` · ${option.top} top pick${option.top === 1 ? '' : 's'}`}
              {option.vetoes > 0 && <span className="text-red-400"> · {option.vetoes} veto{option.vetoes === 1 ? '' : 'es'}</span>}
            </span>
          </div>
          <Bar value={option.vetoes > 0 ? 0 : option.ok} total={shape.total} />
        </li>
      ))}
    </ul>
  )
}

function ShapeCard({ detail }: { detail: Detail }) {
  const shape = detail.shape
  const hasShape = 'kind' in shape
  return (
    <section className="rounded-xl border border-w-line bg-w-surface p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-w-faint">Where the group stands</h2>
        {hasShape && <span className="text-xs text-w-faint">{shape.responded}/{shape.total} responded</span>}
      </div>
      {detail.status === 'resolved' && detail.resolution && (
        <div className="flex items-center gap-2 rounded-lg bg-emerald-500/10 px-3 py-2 text-sm text-emerald-400">
          <Check size={14} className="shrink-0" />
          <span>Settled: <span className="font-medium">{resolutionText(detail.resolution)}</span>. Invites sent.</span>
        </div>
      )}
      {hasShape && shape.kind === 'schedule' && <ScheduleShapeView shape={shape} config={detail.config as ScheduleConfig} />}
      {hasShape && shape.kind === 'decide' && <DecideShapeView shape={shape} />}
    </section>
  )
}

function Participants({ people }: { people: SymChatParticipant[] }) {
  return (
    <ul className="flex flex-wrap gap-1.5">
      {people.map((p) => (
        <li
          key={p.user_id}
          className="inline-flex items-center gap-1 rounded-full border border-w-line px-2 py-0.5 text-[11px] text-w-dim"
          title={p.responded ? 'Responded' : 'Hasn’t responded yet'}
        >
          {p.responded ? <Check size={11} className="text-emerald-400" /> : <CircleDashed size={11} className="text-w-faint" />}
          {p.is_me ? 'You' : p.name}
          {p.is_organizer && <span className="text-w-faint">· organizer</span>}
        </li>
      ))}
    </ul>
  )
}

function UpdatesFeed({ updates }: { updates: SymChatUpdate[] }) {
  return (
    <section className="space-y-2">
      <h2 className="text-[11px] font-semibold uppercase tracking-wider text-w-faint">Updates</h2>
      <ol className="space-y-1.5">
        {updates.map((u) => (
          <li key={u.seq} className="flex gap-2 text-sm text-w-dim">
            <Sparkles size={13} className="mt-0.5 shrink-0 text-w-accent" />
            <span>{u.content}</span>
          </li>
        ))}
      </ol>
    </section>
  )
}

function TunnelChat({ messages, open, sending, sendError, onSend }: {
  messages: SymChatMessage[]
  open: boolean
  sending: boolean
  sendError: string | null
  onSend: (text: string) => Promise<boolean>
}) {
  const [draft, setDraft] = useState('')
  const endRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: 'end' })
  }, [messages.length])

  async function submit(e: FormEvent) {
    e.preventDefault()
    const text = draft
    if (!text.trim()) return
    setDraft('')
    const ok = await onSend(text)
    if (!ok) setDraft(text)
  }

  return (
    <section className="flex min-h-0 flex-col rounded-xl border border-w-line bg-w-surface">
      <div className="flex items-center gap-1.5 border-b border-w-line px-4 py-2 text-[11px] text-w-faint">
        <Lock size={11} /> Only you and the assistant see this
      </div>
      <div className="max-h-[45vh] min-h-[8rem] space-y-2 overflow-y-auto px-4 py-3">
        {messages.length === 0 && (
          <p className="text-sm text-w-faint">Tell the assistant what works for you — in your own words.</p>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <p
              className={`max-w-[80%] whitespace-pre-wrap rounded-lg px-3 py-1.5 text-sm ${
                m.role === 'user' ? 'bg-w-accent text-w-on-accent' : 'bg-w-surface2 text-w-text'
              }`}
            >
              {m.content}
            </p>
          </div>
        ))}
        {sending && <Loader2 size={14} className="animate-spin text-w-faint" aria-label="Assistant is thinking" />}
        <div ref={endRef} />
      </div>
      {sendError && <p role="alert" className="px-4 pb-1 text-xs text-red-400">{sendError}</p>}
      <form onSubmit={submit} className="flex items-center gap-2 border-t border-w-line px-3 py-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={!open || sending}
          maxLength={2000}
          placeholder={open ? 'e.g. “I’m free after 2 but not 3:30–4”' : 'This sym-chat is closed'}
          aria-label="Message the assistant"
          className="flex-1 rounded-md border border-w-line bg-w-surface2/60 px-3 py-1.5 text-sm text-w-text placeholder:text-w-faint outline-none focus:border-w-accent/50 disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={!open || sending || !draft.trim()}
          className="rounded-md bg-w-accent p-2 text-w-on-accent transition-colors hover:bg-w-accent-hi disabled:opacity-40"
          aria-label="Send"
        >
          <Send size={14} />
        </button>
      </form>
    </section>
  )
}

export default function SymChatDetail() {
  const { chatId } = useParams<{ chatId: string }>()
  const base = useWorkBase()
  const { detail, loading, error, sending, sendError, send, cancel } = useSymChatDetail(chatId)

  if (loading && !detail) {
    return <div className="flex flex-1 items-center justify-center"><Loader2 size={18} className="animate-spin text-w-faint" /></div>
  }
  if (!detail) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-2 text-sm text-w-dim">
        <p>{error ?? 'Sym-chat not found'}</p>
        <Link to={`${base}/sym-chat`} className="text-w-accent hover:underline">Back to sym-chats</Link>
      </div>
    )
  }

  const open = detail.status === 'open'
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-2xl space-y-4 px-4 py-5">
        <header className="space-y-2">
          <Link to={`${base}/sym-chat`} className="inline-flex items-center gap-1 text-xs text-w-faint hover:text-w-dim">
            <ArrowLeft size={12} /> Sym-chats
          </Link>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h1 className="truncate text-lg font-semibold text-w-text">{detail.title}</h1>
              <p className="text-xs text-w-faint">{KIND_LABEL[detail.kind]}</p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${statusClass(detail.status)}`}>
                {STATUS_LABEL[detail.status]}
              </span>
              {detail.is_organizer && open && (
                <button
                  onClick={() => { if (window.confirm('Cancel this sym-chat for everyone?')) void cancel() }}
                  className="rounded-md border border-w-line px-2 py-0.5 text-[11px] text-w-dim hover:text-w-text"
                >
                  Cancel
                </button>
              )}
            </div>
          </div>
          {detail.objective && <p className="text-sm text-w-dim">{detail.objective}</p>}
          <Participants people={detail.participants} />
        </header>

        <ShapeCard detail={detail} />
        <UpdatesFeed updates={detail.updates} />
        <TunnelChat messages={detail.messages} open={open} sending={sending} sendError={sendError} onSend={send} />
      </div>
    </div>
  )
}
