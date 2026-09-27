import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Check, Loader2, Search, X } from 'lucide-react'
import {
  createSymChat,
  searchSymChatPeople,
  type SymChatDetail,
  type SymChatKind,
  type SymChatPerson,
} from '../../api/matchaWork/symChat'
import { KIND_LABEL } from './format'

const DURATIONS = [15, 30, 45, 60, 90, 120]
const MAX_INVITEES = 19

function localToday(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

function viewerTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/Los_Angeles'
  } catch {
    return 'America/Los_Angeles'
  }
}

const inputClass =
  'w-full rounded-md border border-w-line bg-w-surface2/60 px-3 py-1.5 text-sm text-w-text placeholder:text-w-faint outline-none focus:border-w-accent/50'

export default function NewSymChatModal({ onClose, onCreated }: {
  onClose: () => void
  onCreated: (chat: SymChatDetail) => void
}) {
  const [kind, setKind] = useState<SymChatKind>('schedule')
  const [title, setTitle] = useState('')
  const [objective, setObjective] = useState('')
  const [date, setDate] = useState(localToday)
  const [windowStart, setWindowStart] = useState('09:00')
  const [windowEnd, setWindowEnd] = useState('17:00')
  const [duration, setDuration] = useState(30)
  const [optionsText, setOptionsText] = useState('')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SymChatPerson[]>([])
  const [selected, setSelected] = useState<SymChatPerson[]>([])
  const [searching, setSearching] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const searchRef = useRef(0)

  useEffect(() => {
    const request = ++searchRef.current
    const timer = window.setTimeout(() => {
      setSearching(true)
      searchSymChatPeople(query)
        .then((res) => { if (request === searchRef.current) setResults(res.people) })
        .catch(() => { if (request === searchRef.current) setResults([]) })
        .finally(() => { if (request === searchRef.current) setSearching(false) })
    }, query ? 250 : 0)
    return () => window.clearTimeout(timer)
  }, [query])

  function toggle(person: SymChatPerson) {
    setSelected((prev) => prev.some((p) => p.id === person.id)
      ? prev.filter((p) => p.id !== person.id)
      : prev.length >= MAX_INVITEES ? prev : [...prev, person])
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!title.trim() || selected.length === 0) return
    setSaving(true)
    setError(null)
    try {
      const config = kind === 'schedule'
        ? { date, window_start: windowStart, window_end: windowEnd, duration_min: duration, timezone: viewerTimezone() }
        : { options: optionsText.split('\n').map((o) => o.trim()).filter(Boolean) }
      const chat = await createSymChat({
        kind,
        title: title.trim(),
        objective: objective.trim(),
        participant_ids: selected.map((p) => p.id),
        config,
      })
      onCreated(chat)
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : 'Could not create the sym-chat')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4" role="dialog" aria-label="New sym-chat">
      <form onSubmit={submit} className="max-h-[90vh] w-full max-w-lg space-y-4 overflow-y-auto rounded-xl border border-w-line bg-w-surface p-5">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-w-text">New sym-chat</h2>
          <button type="button" onClick={onClose} className="text-w-faint hover:text-w-text" aria-label="Close"><X size={16} /></button>
        </div>

        <div className="grid grid-cols-2 gap-2">
          {(Object.keys(KIND_LABEL) as SymChatKind[]).map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setKind(k)}
              aria-pressed={kind === k}
              className={`rounded-lg border px-3 py-2 text-sm transition-colors ${
                kind === k ? 'border-w-accent bg-w-accent/10 text-w-text' : 'border-w-line text-w-dim hover:bg-w-surface2'
              }`}
            >
              {KIND_LABEL[k]}
            </button>
          ))}
        </div>

        <label className="block space-y-1">
          <span className="text-xs text-w-dim">Title</span>
          <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} required
            placeholder={kind === 'schedule' ? 'Quarterly planning sync' : 'Team lunch spot'} className={inputClass} />
        </label>
        <label className="block space-y-1">
          <span className="text-xs text-w-dim">Objective (optional)</span>
          <textarea value={objective} onChange={(e) => setObjective(e.target.value)} maxLength={500} rows={2}
            placeholder="What should everyone know?" className={inputClass} />
        </label>

        {kind === 'schedule' ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <label className="col-span-2 block space-y-1 sm:col-span-1">
              <span className="text-xs text-w-dim">Date</span>
              <input type="date" value={date} min={localToday()} onChange={(e) => setDate(e.target.value)} required className={inputClass} />
            </label>
            <label className="block space-y-1">
              <span className="text-xs text-w-dim">From</span>
              <input type="time" step={900} value={windowStart} onChange={(e) => setWindowStart(e.target.value)} required className={inputClass} />
            </label>
            <label className="block space-y-1">
              <span className="text-xs text-w-dim">To</span>
              <input type="time" step={900} value={windowEnd} onChange={(e) => setWindowEnd(e.target.value)} required className={inputClass} />
            </label>
            <label className="block space-y-1">
              <span className="text-xs text-w-dim">Length</span>
              <select value={duration} onChange={(e) => setDuration(Number(e.target.value))} className={inputClass}>
                {DURATIONS.map((d) => <option key={d} value={d}>{d} min</option>)}
              </select>
            </label>
          </div>
        ) : (
          <label className="block space-y-1">
            <span className="text-xs text-w-dim">Starting options (one per line, optional — people can propose more)</span>
            <textarea value={optionsText} onChange={(e) => setOptionsText(e.target.value)} rows={3} className={inputClass} />
          </label>
        )}

        <div className="space-y-2">
          <span className="text-xs text-w-dim">People</span>
          {selected.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {selected.map((p) => (
                <button key={p.id} type="button" onClick={() => toggle(p)}
                  className="inline-flex items-center gap-1 rounded-full bg-w-surface2 px-2 py-0.5 text-xs text-w-text">
                  {p.name} <X size={11} />
                </button>
              ))}
            </div>
          )}
          <div className="relative">
            <Search size={13} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-w-faint" />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search your company…"
              aria-label="Search people" className={`${inputClass} pl-8`} />
            {searching && <Loader2 size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 animate-spin text-w-faint" />}
          </div>
          <div className="max-h-40 space-y-0.5 overflow-y-auto">
            {results.length === 0 && !searching && <p className="py-2 text-center text-xs text-w-faint">No one found</p>}
            {results.map((p) => {
              const on = selected.some((s) => s.id === p.id)
              return (
                <button key={p.id} type="button" onClick={() => toggle(p)}
                  className={`flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left ${on ? 'bg-w-accent/10' : 'hover:bg-w-surface2'}`}>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm text-w-text">{p.name}</span>
                    <span className="block truncate text-[11px] text-w-faint">{p.email}</span>
                  </span>
                  {on && <Check size={13} className="shrink-0 text-w-accent" />}
                </button>
              )
            })}
          </div>
        </div>

        {error && <p role="alert" className="text-xs text-red-400">{error}</p>}

        <button type="submit" disabled={saving || !title.trim() || selected.length === 0}
          className="w-full rounded-lg bg-w-accent py-2 text-sm font-medium text-w-on-accent transition-colors hover:bg-w-accent-hi disabled:opacity-50">
          {saving
            ? <Loader2 size={15} className="mx-auto animate-spin" />
            : selected.length === 0
              ? 'Pick at least one person'
              : `Start with ${selected.length} ${selected.length === 1 ? 'person' : 'people'}`}
        </button>
      </form>
    </div>
  )
}
