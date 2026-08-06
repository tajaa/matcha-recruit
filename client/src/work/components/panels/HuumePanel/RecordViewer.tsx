import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Briefcase, BadgeCheck, FileText, Loader2, User } from 'lucide-react'
import { getHuumeRecord, getHuumeRecordForCompany } from '../../../api/matchaWork/huume'
import type { HuumeRecordChipTone, HuumeRecordView } from '../../../types'

interface RecordViewerProps {
  /** Omit when there's no thread in scope (e.g. the company-wide Assets
   * page) — falls back to the company-scoped fetch, same server-side view. */
  threadId?: string
  recordType: string
  recordId: string
  lightMode?: boolean
  /** True while Huume is streaming a turn. Each `huume_records` entry
   * carries a `{record_type, record_id, label, opened_at}` reference, never
   * the view itself — so refetch on each true→false edge, same reasoning as
   * LegalMatterViewer. */
  streaming?: boolean
}

// The server always fills a meta row's `value` (missing data renders "—"
// server-side — see record_view.py's builders) so there's nothing to hide
// here; this only needs to render.
function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide opacity-50">{label}</div>
      <div className="font-mono text-xs">{value}</div>
    </div>
  )
}

function Prose({ children }: { children?: string | null }) {
  if (!children) return null
  return <p className="max-w-[65ch] whitespace-pre-wrap text-sm leading-relaxed">{children}</p>
}

const RECORD_ICON: Record<string, typeof AlertTriangle> = {
  incident: AlertTriangle, er_case: Briefcase, employee: User, credential: BadgeCheck,
  ems_event: AlertTriangle,
}
export function recordIcon(recordType: string, size = 12) {
  const Icon = RECORD_ICON[recordType] ?? FileText
  return <Icon size={size} />
}

const CHIP_TONE: Record<HuumeRecordChipTone, string> = {
  red: 'border-red-800 bg-red-950/40 text-red-300',
  orange: 'border-orange-800 bg-orange-950/40 text-orange-300',
  amber: 'border-amber-800 bg-amber-950/40 text-amber-300',
  emerald: 'border-emerald-800 bg-emerald-950/40 text-emerald-300',
  zinc: 'border-zinc-700 bg-zinc-800/40 text-zinc-300',
}
const CHIP_TONE_LIGHT: Record<HuumeRecordChipTone, string> = {
  red: 'border-red-300 bg-red-50 text-red-700',
  orange: 'border-orange-300 bg-orange-50 text-orange-700',
  amber: 'border-amber-300 bg-amber-50 text-amber-700',
  emerald: 'border-emerald-300 bg-emerald-50 text-emerald-700',
  zinc: 'border-zinc-300 bg-zinc-50 text-zinc-700',
}

/** Renders whatever `show_record` staged — one generic viewer for every
 * record type Huume can open (incident, er_case, employee, credential, …).
 * The server does the per-type work (`services/huume/record_view.py`) and
 * normalizes it to {title, chips, meta, sections, link}; adding a record
 * type never touches this file. Fetched client-side via the admin's own
 * auth (GET .../huume/record) — the same access they'd have on the record's
 * own page, a deliberately wider view than the model ever gets in chat. */
export default function RecordViewer({ threadId, recordType, recordId, lightMode, streaming }: RecordViewerProps) {
  const [view, setView] = useState<HuumeRecordView | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setView(threadId
        ? await getHuumeRecord(threadId, recordType, recordId)
        : await getHuumeRecordForCompany(recordType, recordId))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load the record')
    } finally {
      setLoading(false)
    }
  }, [threadId, recordType, recordId])

  useEffect(() => { void load() }, [load])

  const wasStreaming = useRef(streaming)
  useEffect(() => {
    if (wasStreaming.current && !streaming) void load()
    wasStreaming.current = streaming
  }, [streaming, load])

  const muted = 'text-zinc-500'
  const border = lightMode ? 'border-zinc-200' : 'border-zinc-800'
  const boxBorder = lightMode ? 'border-zinc-300' : 'border-zinc-700'
  const chipTone = lightMode ? CHIP_TONE_LIGHT : CHIP_TONE

  if (loading) {
    return (
      <div className="flex w-full flex-1 items-center justify-center">
        <Loader2 size={18} className={`animate-spin ${muted}`} />
      </div>
    )
  }

  if (error || !view) {
    return (
      <div className="flex w-full flex-1 items-center justify-center px-4 text-center">
        <p className={`text-sm ${muted}`}>{error ?? 'Failed to load the record'}</p>
      </div>
    )
  }

  return (
    <div className="flex w-full flex-1 flex-col gap-3 overflow-y-auto p-4">
      <div className={`rounded border p-2.5 font-mono ${boxBorder}`}>
        <div className="flex flex-wrap items-center gap-1.5">
          {recordIcon(view.record_type, 13)}
          <span className="text-xs font-semibold tracking-wide">{view.title}</span>
        </div>
        {view.chips.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {view.chips.map((c, i) => (
              <span key={i} className={`rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${chipTone[c.tone]}`}>
                {c.label}
              </span>
            ))}
          </div>
        )}
        {view.subtitle && <div className={`mt-1 text-xs ${muted}`}>{view.subtitle}</div>}
      </div>

      {view.meta.length > 0 && (
        <div className="grid grid-cols-2 gap-x-4 gap-y-2">
          {view.meta.map((m, i) => <Meta key={i} label={m.label} value={m.value} />)}
        </div>
      )}

      {view.sections.map((s, i) => (
        <div key={i} className={s.items ? `rounded border p-2.5 ${boxBorder}` : undefined}>
          <div className="mb-1 text-[10px] uppercase tracking-wide opacity-70">{s.label}</div>
          {s.body && <Prose>{s.body}</Prose>}
          {s.items && (
            <ul className="space-y-1 text-xs">
              {s.items.map((item, j) => <li key={j}>{item}</li>)}
            </ul>
          )}
        </div>
      ))}

      <div className={`mt-1 border-t pt-2 ${border}`}>
        <Link to={view.link} className="text-xs font-medium text-orange-500 hover:text-orange-400">
          Open record →
        </Link>
      </div>
    </div>
  )
}
