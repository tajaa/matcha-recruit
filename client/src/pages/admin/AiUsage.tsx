import { useState } from 'react'
import { AlertCircle, ChevronDown, ChevronRight, Cpu, RefreshCw, X } from 'lucide-react'
import { useAsync } from '../../hooks/useAsync'
import { getAiUsageCalls, getAiUsageSummary, getAiUsageTimeseries } from '../../api/admin/aiUsage'
import type {
  AiUsageCall,
  AiUsageFeatureRollup,
  AiUsageModelRollup,
  AiUsagePoint,
  AiUsageStatus,
  AiUsageSummary,
} from '../../types/aiUsage'

const RANGES: { label: string; hours: number }[] = [
  { label: '24h', hours: 24 },
  { label: '7d', hours: 168 },
  { label: '30d', hours: 720 },
]

const PAGE_SIZE = 50
const STATUS_CHIPS: { label: string; value: AiUsageStatus | '' }[] = [
  { label: 'All', value: '' },
  { label: 'ok', value: 'ok' },
  { label: 'error', value: 'error' },
  { label: 'timeout', value: 'timeout' },
]

type Selection = { kind: 'feature' | 'model'; value: string } | null

function fmtCost(v: number | null): string {
  if (v == null) return '—'
  return v >= 1 ? `$${v.toFixed(2)}` : `$${v.toFixed(4)}`
}

function fmtTokens(v: number | null): string {
  if (v == null) return '—'
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}k`
  return String(v)
}

function fmtMs(v: number | null): string {
  if (v == null) return '—'
  return `${Math.round(v)}ms`
}

function fmtPct(v: number): string {
  return `${(v * 100).toFixed(1)}%`
}

function relTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime()
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  return `${d}d ago`
}

const STATUS_BADGE: Record<AiUsageStatus, string> = {
  ok: 'bg-zinc-700/40 text-zinc-300 border-zinc-600/40',
  timeout: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  error: 'bg-red-500/15 text-red-300 border-red-500/30',
}

function StatCard({
  label,
  value,
  sub,
  onClick,
  active,
}: {
  label: string
  value: string
  sub?: string
  onClick?: () => void
  active?: boolean
}) {
  const Tag = onClick ? 'button' : 'div'
  return (
    <Tag
      onClick={onClick}
      className={`text-left p-3 rounded-lg border transition-colors ${
        active
          ? 'bg-zinc-800 border-zinc-600'
          : 'border-zinc-800 bg-zinc-900/40' + (onClick ? ' hover:border-zinc-700' : '')
      }`}
    >
      <p className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</p>
      <p className="text-2xl font-semibold mt-0.5 text-zinc-100">{value}</p>
      {sub && <p className="text-[11px] text-zinc-500 mt-0.5">{sub}</p>}
    </Tag>
  )
}

function Bars({ points }: { points: AiUsagePoint[] }) {
  const max = Math.max(0.0001, ...points.map((p) => p.cost_usd ?? 0))
  return (
    <div className="flex items-end gap-0.5 h-24">
      {points.map((p, i) => {
        const h = Math.max(2, Math.round(((p.cost_usd ?? 0) / max) * 96))
        const hasErrors = p.errors > 0
        return (
          <div
            key={i}
            title={`${new Date(p.at).toLocaleString()} — ${p.calls} calls, ${fmtCost(p.cost_usd)}${hasErrors ? `, ${p.errors} errors` : ''}`}
            className={`flex-1 rounded-sm ${hasErrors ? 'bg-amber-500/60' : 'bg-emerald-500/50'} hover:opacity-80 transition-opacity`}
            style={{ height: `${h}px` }}
          />
        )
      })}
    </div>
  )
}

function RollupTable<T extends { calls: number; cost_usd: number | null; input_tokens: number; output_tokens: number; thinking_tokens: number; error_rate: number; p95_latency_ms: number | null }>({
  rows,
  labelKey,
  labelHeader,
  selectedLabel,
  onSelect,
}: {
  rows: T[]
  labelKey: (r: T) => string
  labelHeader: string
  selectedLabel: string | null
  onSelect: (label: string) => void
}) {
  if (rows.length === 0) {
    return <p className="p-6 text-center text-sm text-zinc-500">No calls in the selected window.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[10px] uppercase tracking-wider text-zinc-500 border-b border-zinc-800">
            <th className="py-2 px-3">{labelHeader}</th>
            <th className="py-2 px-3 text-right">Calls</th>
            <th className="py-2 px-3 text-right">Cost</th>
            <th className="py-2 px-3 text-right">In</th>
            <th className="py-2 px-3 text-right">Out</th>
            <th className="py-2 px-3 text-right">Thinking</th>
            <th className="py-2 px-3 text-right">Err %</th>
            <th className="py-2 px-3 text-right">p95</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800/50">
          {rows.map((r, i) => {
            const label = labelKey(r)
            const selected = selectedLabel === label
            return (
              <tr
                key={i}
                onClick={() => onSelect(label)}
                className={`cursor-pointer transition-colors ${selected ? 'bg-zinc-800 ring-1 ring-inset ring-emerald-700/40' : 'hover:bg-zinc-800/20'}`}
              >
                <td className="py-2 px-3 font-mono text-zinc-200">{label}</td>
                <td className="py-2 px-3 text-right text-zinc-300">{r.calls}</td>
                <td className="py-2 px-3 text-right text-zinc-100">{fmtCost(r.cost_usd)}</td>
                <td className="py-2 px-3 text-right text-zinc-400">{fmtTokens(r.input_tokens)}</td>
                <td className="py-2 px-3 text-right text-zinc-400">{fmtTokens(r.output_tokens)}</td>
                <td className="py-2 px-3 text-right text-zinc-400">{fmtTokens(r.thinking_tokens)}</td>
                <td className={`py-2 px-3 text-right ${r.error_rate > 0 ? 'text-amber-400' : 'text-zinc-500'}`}>
                  {fmtPct(r.error_rate)}
                </td>
                <td className="py-2 px-3 text-right text-zinc-500">{fmtMs(r.p95_latency_ms)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function CallLogRow({ call, isOpen, onToggle }: { call: AiUsageCall; isOpen: boolean; onToggle: () => void }) {
  return (
    <div>
      <button onClick={onToggle} className="w-full text-left px-3 py-2 hover:bg-zinc-800/20 transition-colors">
        <div className="flex items-center gap-3 text-sm">
          <span className="shrink-0 text-zinc-500">
            {isOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </span>
          <span className="shrink-0 w-16 text-[11px] text-zinc-500">{relTime(call.created_at)}</span>
          <span
            className={`shrink-0 text-[9px] font-medium uppercase px-1.5 py-0.5 rounded border ${STATUS_BADGE[call.status]}`}
          >
            {call.status}
          </span>
          <span className="min-w-0 flex-1 font-mono text-zinc-200 truncate">
            {call.feature} <span className="text-zinc-600">·</span> {call.model}
          </span>
          <span className="shrink-0 text-[11px] text-zinc-500 w-20 text-right">{call.method}</span>
          <span className="shrink-0 text-[11px] text-zinc-400 w-14 text-right">{fmtTokens(call.input_tokens)}</span>
          <span className="shrink-0 text-[11px] text-zinc-400 w-14 text-right">{fmtTokens(call.output_tokens)}</span>
          <span className="shrink-0 text-[11px] text-zinc-400 w-14 text-right">{fmtTokens(call.cached_tokens)}</span>
          <span className="shrink-0 text-[11px] text-zinc-100 w-16 text-right">{fmtCost(call.cost_usd)}</span>
          <span className="shrink-0 text-[11px] text-zinc-500 w-16 text-right">{fmtMs(call.latency_ms)}</span>
        </div>
      </button>
      {isOpen && (
        <div className="px-3 pb-3 pl-11 space-y-2 bg-zinc-900/30">
          <div className="flex items-center gap-3 text-[10px] text-zinc-500 font-mono flex-wrap">
            <span>id: {call.id}</span>
            <span>at: {new Date(call.created_at).toLocaleString()}</span>
            <span>thinking: {fmtTokens(call.thinking_tokens)}</span>
          </div>
          {call.error && (
            <pre className="text-[11px] font-mono text-red-300/90 bg-zinc-950/80 p-3 rounded border border-zinc-800 overflow-x-auto whitespace-pre-wrap">
              {call.error}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}

type PageData = {
  summary: AiUsageSummary | null
  timeseries: { bucket: 'hour' | 'day'; points: AiUsagePoint[] }
}

const EMPTY_DATA: PageData = {
  summary: null,
  timeseries: { bucket: 'hour', points: [] },
}

export default function AiUsage() {
  const [sinceHours, setSinceHours] = useState(24)
  const [selection, setSelection] = useState<Selection>(null)
  const [statusFilter, setStatusFilter] = useState<AiUsageStatus | ''>('')
  const [page, setPage] = useState(0)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  // Combined fetch for the page-level rollups (mirrors ServerErrors.tsx's
  // Promise.all pattern): a single reload keeps the stat cards, chart, and
  // both tables in sync instead of drifting independently.
  const { data, loading, error, reload } = useAsync(
    async () => {
      const [summary, timeseries] = await Promise.all([
        getAiUsageSummary(sinceHours),
        getAiUsageTimeseries(sinceHours),
      ])
      return { summary, timeseries }
    },
    [sinceHours],
    EMPTY_DATA,
  )
  const { summary, timeseries } = data
  const totals = summary?.totals

  // Separate fetch for the call log: it's interaction-driven (selection,
  // status, page) rather than page-level, so it doesn't belong in the
  // combined fetch above — selecting a row shouldn't re-fetch the chart.
  const {
    data: callLog,
    loading: callLogLoading,
    error: callLogError,
    reload: reloadCallLog,
  } = useAsync(
    () =>
      getAiUsageCalls({
        sinceHours,
        feature: selection?.kind === 'feature' ? selection.value : undefined,
        model: selection?.kind === 'model' ? selection.value : undefined,
        status: statusFilter || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
    [sinceHours, selection, statusFilter, page],
    { total: 0, items: [] as AiUsageCall[] },
  )

  function selectFeature(feature: string) {
    setPage(0)
    setSelection((s) => (s?.kind === 'feature' && s.value === feature ? null : { kind: 'feature', value: feature }))
  }
  function selectModel(model: string) {
    setPage(0)
    setSelection((s) => (s?.kind === 'model' && s.value === model ? null : { kind: 'model', value: model }))
  }
  function toggleStatus(status: AiUsageStatus | '') {
    setPage(0)
    setStatusFilter((s) => (s === status ? '' : status))
  }
  function toggleExpand(id: number) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }
  function refreshAll() {
    reload()
    reloadCallLog()
  }

  const totalPages = Math.max(1, Math.ceil(callLog.total / PAGE_SIZE))

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <div className="flex items-center gap-2">
            <Cpu size={20} className="text-emerald-500" />
            <h1 className="text-xl font-semibold text-zinc-100">AI Usage</h1>
          </div>
          <p className="text-sm text-zinc-500 mt-0.5">
            Model calls across every feature — Gemini today, provider-general by design.
          </p>
        </div>
        <button
          onClick={refreshAll}
          disabled={loading || callLogLoading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-800 text-zinc-200 text-xs font-medium hover:bg-zinc-700 disabled:opacity-50 transition-colors"
        >
          <RefreshCw size={12} className={loading || callLogLoading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      <div className="flex items-center gap-2 mb-4">
        {RANGES.map((r) => (
          <button
            key={r.hours}
            onClick={() => {
              setSinceHours(r.hours)
              setPage(0)
            }}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
              sinceHours === r.hours
                ? 'bg-zinc-800 border-zinc-600 text-zinc-100'
                : 'border-zinc-800 text-zinc-400 hover:border-zinc-700'
            }`}
          >
            {r.label}
          </button>
        ))}
      </div>

      {error && (
        <p className="mb-4 text-sm text-red-400">Couldn't load AI usage: {error}</p>
      )}

      {totals && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 mb-4">
          <StatCard label="Cost" value={fmtCost(totals.cost_usd)} />
          <StatCard label="Calls" value={String(totals.calls)} />
          <StatCard label="Tokens in" value={fmtTokens(totals.input_tokens)} />
          <StatCard label="Tokens out" value={fmtTokens(totals.output_tokens)} />
          <StatCard
            label="Error rate"
            value={fmtPct(totals.error_rate)}
            sub={`${totals.errors} errors — click to filter`}
            active={statusFilter === 'error'}
            onClick={() => toggleStatus('error')}
          />
          <StatCard label="p95 latency" value={fmtMs(totals.p95_latency_ms)} />
        </div>
      )}

      {totals && totals.unknown_cost_calls > 0 && (
        <p className="mb-4 text-xs text-amber-300/90 flex items-center gap-1.5">
          <AlertCircle size={12} />
          {totals.unknown_cost_calls} call(s) have unknown cost (unpriced model, or a timeout/error with no
          token count) — the total above is undercounted.
        </p>
      )}

      {timeseries.points.length > 0 && (
        <div className="mb-6 p-3 rounded-lg border border-zinc-800 bg-zinc-900/40">
          <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2">
            Cost by {timeseries.bucket}
          </p>
          <Bars points={timeseries.points} />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <div className="rounded-xl border border-zinc-800 overflow-hidden">
          <p className="px-3 pt-3 pb-1 text-xs font-semibold uppercase tracking-wider text-zinc-500">
            By feature — click a row to drill in
          </p>
          <RollupTable<AiUsageFeatureRollup>
            rows={summary?.by_feature ?? []}
            labelKey={(r) => r.feature}
            labelHeader="Feature"
            selectedLabel={selection?.kind === 'feature' ? selection.value : null}
            onSelect={selectFeature}
          />
        </div>
        <div className="rounded-xl border border-zinc-800 overflow-hidden">
          <p className="px-3 pt-3 pb-1 text-xs font-semibold uppercase tracking-wider text-zinc-500">
            By model — click a row to drill in
          </p>
          <RollupTable<AiUsageModelRollup>
            rows={summary?.by_model ?? []}
            labelKey={(r) => r.model}
            labelHeader="Model"
            selectedLabel={selection?.kind === 'model' ? selection.value : null}
            onSelect={selectModel}
          />
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-500">Call log</h2>
          <div className="flex items-center gap-2 flex-wrap">
            {selection && (
              <button
                onClick={() => setSelection(null)}
                className="flex items-center gap-1 px-2 py-1 rounded-full text-[11px] bg-emerald-500/10 text-emerald-300 border border-emerald-700/40"
              >
                {selection.kind}: {selection.value} <X size={10} />
              </button>
            )}
            <div className="flex rounded-lg border border-zinc-800 p-0.5">
              {STATUS_CHIPS.map((s) => (
                <button
                  key={s.label}
                  onClick={() => toggleStatus(s.value)}
                  className={`px-2 py-1 rounded-md text-[11px] font-medium transition-colors ${
                    statusFilter === s.value ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
            <span className="text-[11px] text-zinc-500">
              {callLog.items.length} of {callLog.total}
            </span>
          </div>
        </div>

        {callLogError && (
          <p className="mb-2 text-sm text-red-400">Couldn't load call log: {callLogError}</p>
        )}

        <div className="rounded-xl border border-zinc-800 overflow-hidden">
          {callLog.items.length === 0 ? (
            <p className="p-6 text-center text-sm text-zinc-500">No calls match the current filters.</p>
          ) : (
            <div className="divide-y divide-zinc-800">
              {callLog.items.map((c) => (
                <CallLogRow key={c.id} call={c} isOpen={expanded.has(c.id)} onToggle={() => toggleExpand(c.id)} />
              ))}
            </div>
          )}
        </div>

        {callLog.total > PAGE_SIZE && (
          <div className="flex items-center justify-center gap-3 mt-3">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="px-3 py-1 rounded-lg text-xs bg-zinc-800 text-zinc-300 hover:bg-zinc-700 disabled:opacity-40"
            >
              Prev
            </button>
            <span className="text-[11px] text-zinc-500">
              page {page + 1} of {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="px-3 py-1 rounded-lg text-xs bg-zinc-800 text-zinc-300 hover:bg-zinc-700 disabled:opacity-40"
            >
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
