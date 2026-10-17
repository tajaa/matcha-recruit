import { AdminButton, AdminFilterBar, AdminSection, AdminSelect } from './AdminUI'
import type { ReactNode } from 'react'
import { useState } from 'react'
import { ChevronDown, ChevronRight, RefreshCw } from 'lucide-react'
import { AdminPageHeader } from './AdminPageHeader'

type Kind = { key: string; label: string; color: string; count: number }
type Summary = { id: string; kind: string; title: ReactNode; subtitle?: ReactNode; at: string | null; email?: string | null; status?: number | null; badges?: ReactNode; resolved?: boolean }
type Details = { actions?: ReactNode; trace?: { label: string; value: string }; context?: Record<string, unknown> | null; fields?: { label: string; value: ReactNode }[]; footer?: ReactNode }

function relativeTime(iso: string | null) {
  if (!iso) return '—'
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  return hours < 24 ? `${hours}h ago` : `${Math.floor(hours / 24)}d ago`
}

function CodeBlock({ children }: { children: string }) {
  return <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 font-mono text-xs text-zinc-300">{children}</pre>
}

export function ErrorConsole<T>({ title, description, loading, error, onRefresh, kinds, selectedKind, onKindChange, filters, items, summary, details, top }: {
  title: string
  description: ReactNode
  loading: boolean
  error?: string | null
  onRefresh: () => void
  kinds: Kind[]
  selectedKind: string
  onKindChange: (kind: string) => void
  filters: ReactNode
  items: T[]
  summary: (item: T) => Summary
  details: (item: T) => Details
  top: { id: string; kind: string; count: number; title: ReactNode; at: string | null }[]
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  function toggle(id: string) {
    setExpanded((prev) => { const next = new Set(prev); if (next.has(id)) next.delete(id); else next.add(id); return next })
  }
  function badge(key: string) {
    const kind = kinds.find((item) => item.key === key)
    return <span className={`rounded border px-2 py-0.5 text-xs ${kind?.color ?? 'border-zinc-700 text-zinc-400'}`}>{kind?.label ?? key}</span>
  }
  return <div className="space-y-8">
    <AdminPageHeader title={title} description={description} actions={<AdminButton onClick={onRefresh} disabled={loading}><RefreshCw size={14} className={loading ? 'animate-spin' : ''} />Refresh</AdminButton>} />
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      {kinds.slice(0, 4).map((kind) => <button key={kind.key} type="button" aria-label={`${kind.label} ${kind.count}`} aria-pressed={selectedKind === kind.key} onClick={() => onKindChange(selectedKind === kind.key ? '' : kind.key)} className={`rounded-lg border bg-zinc-900/50 p-4 text-left ${selectedKind === kind.key ? 'border-emerald-500' : 'border-zinc-800 hover:border-zinc-600'}`}>
        <span className="block text-xs text-zinc-500">{kind.label}</span>
        <span className="mt-1 block text-2xl font-semibold tabular-nums text-zinc-100">{kind.count}</span>
      </button>)}
    </div>
    <AdminFilterBar>{filters}{selectedKind && <AdminButton variant="ghost" onClick={() => onKindChange('')}>Clear kind filter</AdminButton>}</AdminFilterBar>
    <section className="divide-y divide-zinc-800 rounded-lg border border-zinc-800">
      {loading && !items.length ? <p className="p-6 text-sm text-zinc-500">Loading…</p>
        : error && !items.length ? <p role="alert" className="p-6 text-sm text-red-400">{error}</p>
        : !items.length ? <p className="p-6 text-sm text-zinc-500">No errors in the selected window.</p>
        : items.map((item) => {
          const row = summary(item), open = expanded.has(row.id)
          const detail = open ? details(item) : null
          return <div key={row.id} className={row.resolved ? 'opacity-60' : ''}>
            <button type="button" aria-expanded={open} onClick={() => toggle(row.id)} className="flex w-full items-start gap-3 p-4 text-left hover:bg-zinc-900/30">
              {open ? <ChevronDown size={16} className="mt-1 shrink-0 text-zinc-500" /> : <ChevronRight size={16} className="mt-1 shrink-0 text-zinc-500" />}
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-500">{badge(row.kind)}{row.badges}{row.status != null && <span>{row.status}</span>}<span>{relativeTime(row.at)}</span>{row.email && <span>{row.email}</span>}</div>
                <p className="mt-2 break-words text-sm text-zinc-200">{row.title}</p>
                {row.subtitle && <p className="mt-1 truncate font-mono text-xs text-zinc-500">{row.subtitle}</p>}
              </div>
            </button>
            {detail && <div className="space-y-4 px-4 pb-4 md:pl-11">
              {detail.actions && <div className="flex flex-wrap items-center gap-2">{detail.actions}</div>}
              {detail.trace && <AdminSection title={detail.trace.label}><CodeBlock>{detail.trace.value}</CodeBlock></AdminSection>}
              {detail.context && Object.keys(detail.context).length > 0 && <AdminSection title="Context"><CodeBlock>{JSON.stringify(detail.context, null, 2)}</CodeBlock></AdminSection>}
              {detail.fields?.map((field) => <div key={field.label}><p className="text-xs text-zinc-500">{field.label}</p><div className="mt-1 break-all font-mono text-xs text-zinc-300">{field.value}</div></div>)}
              {detail.footer}
            </div>}
          </div>
        })}
    </section>
    {top.length > 0 && <AdminSection title="Most frequent errors"><div className="divide-y divide-zinc-800 rounded-lg border border-zinc-800">
      {top.slice(0, 10).map((row) => <div key={row.id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-xs"><span className="font-mono text-zinc-400">{row.count}×</span>{badge(row.kind)}<p className="min-w-0 flex-1 truncate text-zinc-300">{row.title}</p><span className="text-zinc-500">{relativeTime(row.at)}</span></div>)}
    </div></AdminSection>}
  </div>
}

export function ErrorTimeFilter({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  return <AdminSelect aria-label="Error time window" value={value} onChange={(event) => onChange(Number(event.target.value))}>
    <option value={1}>Last hour</option><option value={24}>Last 24 hours</option><option value={168}>Last 7 days</option><option value={720}>Last 30 days</option>
  </AdminSelect>
}
