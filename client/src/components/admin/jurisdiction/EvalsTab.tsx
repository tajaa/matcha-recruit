import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../../../api/client'
import { Button } from '../../ui'

// ── Types ─────────────────────────────────────────────────────────────────────

type Subscores = {
  completeness: number | null
  accuracy: number | null
  authority: number | null
  freshness: number | null
  tagging: number | null
}

type ScorecardCell = {
  jurisdiction_id: string
  jurisdiction_label: string | null
  industry: string | null
  composite: number | null
  onboarding_ready: boolean | null
  status: string | null
  subscores: Partial<Subscores>
  blocking: string[]
  measured_at: string | null
}

type EvalRun = {
  id: string
  suites: string[]
  status: string
  trigger_source: string
  totals: Record<string, unknown> | null
  error_text: string | null
  started_at: string | null
  finished_at: string | null
}

type Finding = {
  id: string
  suite: string
  finding_type: string
  severity: 'critical' | 'warn' | 'info'
  jurisdiction_label: string | null
  requirement_key: string | null
  category: string | null
  industry: string | null
  expected: Record<string, unknown> | null
  observed: Record<string, unknown> | null
  status: string
  created_at: string | null
}

type RunDetail = {
  run: EvalRun
  finding_counts: { finding_type: string; severity: string; count: number }[]
  total: number
  findings: Finding[]
}

type CoreChecklist = {
  score: number
  present: number
  total: number
  complete: boolean
  items: { category: string; key: string; present: boolean }[]
}

type Readiness = {
  found: boolean
  status: string
  ready?: boolean
  industry: string
  depth?: 'core' | 'full'
  composite: number | null
  subscores: Partial<Subscores>
  blocking: string[]
  missing_keys: Record<string, string[]>
  golden_fact_count: number
  open_critical_findings: number
  core_checklist: CoreChecklist | null
}

type GoldenFact = {
  jurisdiction: string
  requirement_key: string
  category: string
  comparator: string
  severity: string
  effective_from: string
  effective_to: string | null
  authority_url: string
  curated_by: string
  verified_by: string | null
  notes: string | null
  state: 'active' | 'pending' | 'expired'
}

type GoldenResponse = { facts: GoldenFact[]; total: number; active: number; unverified: number }

const SUITES = ['completeness', 'tagging', 'golden', 'authority', 'baseline'] as const
type Suite = (typeof SUITES)[number]

type BaselineItem = {
  category: string
  key: string
  citation: string
  authority_url: string
  applies_note: string
  present: boolean
}
type BaselineJurisdiction = {
  label: string
  jurisdiction_found: boolean
  expected: number
  present: number
  score: number | null
  items: BaselineItem[]
}

const INDUSTRIES = [
  'manufacturing',
  'healthcare',
  'healthcare:oncology',
  'biotech',
  'hospitality',
  'retail',
  'technology',
  'fast food',
]

/** Industries with a curated <=30-key must-have checklist. Others only have the full sweep. */
const CORE_INDUSTRIES = new Set(['manufacturing', 'healthcare'])

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Unmeasured renders as a dash, never as zero — the eval must not imply a verdict it never reached. */
function scoreColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return 'text-zinc-600'
  if (score >= 90) return 'text-emerald-400'
  if (score >= 75) return 'text-amber-400'
  return 'text-red-400'
}

function scoreCellBg(score: number | null | undefined): string {
  if (score === null || score === undefined) return 'bg-zinc-800/40'
  if (score >= 90) return 'bg-emerald-500/20'
  if (score >= 75) return 'bg-amber-500/20'
  if (score >= 50) return 'bg-orange-500/20'
  return 'bg-red-500/20'
}

function fmtScore(score: number | null | undefined): string {
  return score === null || score === undefined ? '—' : String(Math.round(score))
}

function statusBadge(status: string | null | undefined) {
  const map: Record<string, string> = {
    READY: 'bg-emerald-500/20 text-emerald-300',
    DEGRADED: 'bg-amber-500/20 text-amber-300',
    NOT_READY: 'bg-red-500/20 text-red-300',
  }
  const cls = map[status || ''] || 'bg-zinc-700 text-zinc-400'
  return <span className={`px-2 py-0.5 rounded text-[11px] font-bold ${cls}`}>{status || 'UNMEASURED'}</span>
}

function severityBadge(severity: string) {
  const map: Record<string, string> = {
    critical: 'bg-red-500/20 text-red-400',
    warn: 'bg-amber-500/20 text-amber-400',
    info: 'bg-zinc-700 text-zinc-400',
  }
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase ${map[severity] || ''}`}>
      {severity}
    </span>
  )
}

// ── Readiness widget ──────────────────────────────────────────────────────────

/**
 * The <=30-key must-have list, rendered in full. Small on purpose: the full sweep
 * expects 201 keys for manufacturing, which nobody can check by hand, so a wrong
 * expectation set would never be spotted. Every row here is individually auditable.
 */
function CoreChecklistPanel({ checklist }: { checklist: CoreChecklist }) {
  const byCategory = useMemo(() => {
    const groups = new Map<string, CoreChecklist['items']>()
    for (const item of checklist.items) {
      const bucket = groups.get(item.category)
      if (bucket) bucket.push(item)
      else groups.set(item.category, [item])
    }
    return [...groups.entries()]
  }, [checklist])

  return (
    <div className="border border-zinc-800 rounded-lg p-3">
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-medium text-zinc-300">
          Core checklist — every miss is critical
        </p>
        <p className={`text-sm font-bold ${scoreColor(checklist.score)}`}>
          {checklist.present}/{checklist.total}
        </p>
      </div>
      <div className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
        {byCategory.map(([category, items]) => (
          <div key={category}>
            <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-0.5">{category}</p>
            <ul>
              {items.map((item) => (
                <li key={item.key} className="flex items-baseline gap-1.5 text-xs">
                  <span
                    aria-hidden
                    className={item.present ? 'text-emerald-400' : 'text-red-400'}
                  >
                    {item.present ? '✓' : '✗'}
                  </span>
                  <span className={item.present ? 'text-zinc-400' : 'text-red-300'}>
                    {item.key}
                  </span>
                  <span className="sr-only">{item.present ? 'present' : 'missing'}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  )
}

function BaselinePanel() {
  const [data, setData] = useState<BaselineJurisdiction[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.get<{ jurisdictions: BaselineJurisdiction[] }>('/admin/jurisdictions/evals/baseline-checklist')
      .then((r) => setData(r.jurisdictions))
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
  }, [])

  if (error) return <p className="text-xs text-red-400">{error}</p>
  if (!data) return <p className="text-xs text-zinc-500">Loading…</p>

  return (
    <div className="space-y-4">
      <p className="text-xs text-zinc-500">
        The enumerated federal + CA-state labor obligations a general employer owes, scored against
        each base jurisdiction's own catalog. Every miss is a critical gap carrying the citation to
        research next — the checkable answer to "is federal/state actually done?".
      </p>
      {data.map((jur) => {
        const byCategory = [...jur.items.reduce((m, i) => {
          const b = m.get(i.category); if (b) b.push(i); else m.set(i.category, [i]); return m
        }, new Map<string, BaselineItem[]>()).entries()]
        return (
          <div key={jur.label} className="border border-zinc-800 rounded-lg p-3">
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-medium text-zinc-200">{jur.label}</p>
              <p className={`text-sm font-bold ${scoreColor(jur.score)}`}>
                {jur.present}/{jur.expected}
              </p>
            </div>
            {!jur.jurisdiction_found && (
              <p className="text-[11px] text-amber-400 mb-2">No jurisdiction record found.</p>
            )}
            <div className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
              {byCategory.map(([category, items]) => (
                <div key={category}>
                  <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-0.5">{category}</p>
                  <ul>
                    {items.map((item) => (
                      <li key={item.key} className="flex items-baseline gap-1.5 text-xs">
                        <span aria-hidden className={item.present ? 'text-emerald-400' : 'text-red-400'}>
                          {item.present ? '✓' : '✗'}
                        </span>
                        <a
                          href={item.authority_url}
                          target="_blank"
                          rel="noreferrer"
                          className={`${item.present ? 'text-zinc-400' : 'text-red-300'} hover:underline`}
                          title={`${item.citation}${item.applies_note ? ' — ' + item.applies_note : ''}`}
                        >
                          {item.key}
                        </a>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function ReadinessWidget() {
  const [industry, setIndustry] = useState('manufacturing')
  const [state, setState] = useState('CA')
  const [city, setCity] = useState('Los Angeles')
  const [depth, setDepth] = useState<'core' | 'full'>('core')
  const [data, setData] = useState<Readiness | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const hasCore = CORE_INDUSTRIES.has(industry)
  const effectiveDepth = hasCore ? depth : 'full'

  const check = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({ industry, state, depth: effectiveDepth })
      if (city.trim()) params.set('city', city.trim())
      setData(await api.get<Readiness>(`/admin/jurisdictions/evals/onboarding-readiness?${params}`))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Readiness check failed')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [industry, state, city, effectiveDepth])

  const missingCount = data ? Object.values(data.missing_keys || {}).reduce((n, ks) => n + ks.length, 0) : 0

  return (
    <div className="border border-zinc-800 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-zinc-200 mb-1">Onboarding readiness</h3>
      <p className="text-xs text-zinc-500 mb-3">
        Can a company in this industry onboard into this location with the data we hold?
      </p>

      <div className="flex flex-wrap items-end gap-2 mb-4">
        <label className="flex flex-col gap-1">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500">Industry</span>
          <select
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            className="bg-zinc-900 border border-zinc-700 rounded px-2 py-1.5 text-sm text-zinc-200"
          >
            {INDUSTRIES.map((i) => (
              <option key={i} value={i}>{i}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500">State</span>
          <input
            value={state}
            onChange={(e) => setState(e.target.value.toUpperCase())}
            maxLength={2}
            className="bg-zinc-900 border border-zinc-700 rounded px-2 py-1.5 text-sm text-zinc-200 w-16"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500">City (blank = state)</span>
          <input
            value={city}
            onChange={(e) => setCity(e.target.value)}
            className="bg-zinc-900 border border-zinc-700 rounded px-2 py-1.5 text-sm text-zinc-200 w-44"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500">Depth</span>
          <select
            value={effectiveDepth}
            onChange={(e) => setDepth(e.target.value as 'core' | 'full')}
            disabled={!hasCore}
            title={hasCore ? undefined : `No core checklist curated for ${industry}`}
            className="bg-zinc-900 border border-zinc-700 rounded px-2 py-1.5 text-sm text-zinc-200 disabled:opacity-50"
          >
            <option value="core">Core (≤30 keys)</option>
            <option value="full">Full sweep</option>
          </select>
        </label>
        <Button size="sm" onClick={check} disabled={loading || !state.trim()}>
          {loading ? 'Checking…' : 'Check'}
        </Button>
      </div>

      {!hasCore && (
        <p className="text-[11px] text-zinc-500 mb-3">
          No core checklist for <span className="text-zinc-400">{industry}</span> — scoring the full
          registry sweep. Core sets exist for manufacturing and healthcare.
        </p>
      )}

      {error && <p className="text-sm text-red-400">{error}</p>}

      {data && !data.found && (
        <p className="text-sm text-amber-400">No jurisdiction record exists for this location.</p>
      )}

      {data && data.found && (
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            {statusBadge(data.status)}
            <span className={`text-2xl font-bold ${scoreColor(data.composite)}`}>{fmtScore(data.composite)}</span>
            <span className="text-xs text-zinc-500">composite</span>
          </div>

          <div className="grid grid-cols-5 gap-2">
            {(['completeness', 'accuracy', 'authority', 'freshness', 'tagging'] as const).map((k) => (
              <div key={k} className="border border-zinc-800 rounded px-2 py-2">
                <p className="text-[10px] uppercase tracking-wider text-zinc-500">{k}</p>
                <p className={`text-lg font-bold ${scoreColor(data.subscores[k])}`}>
                  {fmtScore(data.subscores[k])}
                </p>
              </div>
            ))}
          </div>

          {data.blocking.length > 0 && (
            <div>
              <p className="text-xs font-medium text-zinc-400 mb-1">Blocking</p>
              <ul className="space-y-1">
                {data.blocking.map((b) => (
                  <li key={b} className="text-xs text-red-300 flex gap-1.5">
                    <span aria-hidden>•</span>
                    <span>{b}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {data.core_checklist && <CoreChecklistPanel checklist={data.core_checklist} />}

          {data.depth === 'full' && missingCount > 0 && (
            <details className="text-xs">
              <summary className="cursor-pointer text-zinc-400">
                Full sweep: {missingCount} missing key{missingCount === 1 ? '' : 's'} across{' '}
                {Object.keys(data.missing_keys).length} categories
              </summary>
              <div className="mt-2 space-y-1.5 max-h-64 overflow-y-auto">
                {Object.entries(data.missing_keys).map(([cat, keys]) => (
                  <div key={cat}>
                    <span className="text-zinc-300 font-medium">{cat}</span>
                    <span className="text-zinc-600"> — {keys.join(', ')}</span>
                  </div>
                ))}
              </div>
            </details>
          )}

          <p className="text-[11px] text-zinc-600">
            {data.golden_fact_count} golden fact{data.golden_fact_count === 1 ? '' : 's'} asserted ·{' '}
            {data.open_critical_findings} open critical finding
            {data.open_critical_findings === 1 ? '' : 's'}
          </p>
        </div>
      )}
    </div>
  )
}

// ── Scorecard heatmap ─────────────────────────────────────────────────────────

function Scorecard({ cells }: { cells: ScorecardCell[] }) {
  const [selected, setSelected] = useState<ScorecardCell | null>(null)

  const { jurisdictions, industries, byKey } = useMemo(() => {
    const jMap = new Map<string, string>()
    const iSet = new Set<string>()
    const map = new Map<string, ScorecardCell>()
    for (const c of cells) {
      jMap.set(c.jurisdiction_id, c.jurisdiction_label || c.jurisdiction_id)
      if (c.industry) iSet.add(c.industry)
      map.set(`${c.jurisdiction_id}|${c.industry}`, c)
    }
    return {
      jurisdictions: [...jMap.entries()].sort((a, b) => a[1].localeCompare(b[1])),
      industries: [...iSet].sort(),
      byKey: map,
    }
  }, [cells])

  if (!cells.length) {
    return (
      <p className="text-sm text-zinc-500 border border-zinc-800 rounded-lg p-6 text-center">
        No scorecard yet. Trigger a run to populate it.
      </p>
    )
  }

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto border border-zinc-800 rounded-lg">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-800">
              <th className="text-left px-3 py-2 text-[10px] uppercase tracking-wider text-zinc-500 font-medium sticky left-0 bg-zinc-950">
                Jurisdiction
              </th>
              {industries.map((i) => (
                <th key={i} className="px-2 py-2 text-[10px] uppercase tracking-wider text-zinc-500 font-medium">
                  {i}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {jurisdictions.map(([jid, label]) => (
              <tr key={jid} className="border-b border-zinc-900">
                <td className="px-3 py-1.5 text-zinc-300 whitespace-nowrap sticky left-0 bg-zinc-950">{label}</td>
                {industries.map((ind) => {
                  const cell = byKey.get(`${jid}|${ind}`)
                  return (
                    <td key={ind} className="px-1 py-1">
                      <button
                        onClick={() => cell && setSelected(cell)}
                        disabled={!cell}
                        className={`w-full rounded px-2 py-1 font-medium ${scoreCellBg(cell?.composite)} ${scoreColor(cell?.composite)} ${cell ? 'hover:ring-1 hover:ring-zinc-600' : 'cursor-default'}`}
                      >
                        {fmtScore(cell?.composite)}
                      </button>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selected && (
        <div className="border border-zinc-700 rounded-lg p-4">
          <div className="flex items-start justify-between mb-3">
            <div>
              <p className="text-sm font-semibold text-zinc-200">
                {selected.jurisdiction_label} · {selected.industry}
              </p>
              <p className="text-[11px] text-zinc-500">measured {selected.measured_at?.slice(0, 10)}</p>
            </div>
            <div className="flex items-center gap-2">
              {statusBadge(selected.status)}
              <Button variant="ghost" size="sm" onClick={() => setSelected(null)}>Close</Button>
            </div>
          </div>
          <div className="grid grid-cols-5 gap-2 mb-3">
            {(['completeness', 'accuracy', 'authority', 'freshness', 'tagging'] as const).map((k) => (
              <div key={k} className="border border-zinc-800 rounded px-2 py-2">
                <p className="text-[10px] uppercase tracking-wider text-zinc-500">{k}</p>
                <p className={`text-lg font-bold ${scoreColor(selected.subscores[k])}`}>
                  {fmtScore(selected.subscores[k])}
                </p>
              </div>
            ))}
          </div>
          {selected.blocking?.length > 0 && (
            <ul className="space-y-1">
              {selected.blocking.map((b) => (
                <li key={b} className="text-xs text-red-300">• {b}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

// ── Findings ──────────────────────────────────────────────────────────────────

function FindingsTable({ detail, onResolved }: { detail: RunDetail; onResolved: () => void }) {
  const [severity, setSeverity] = useState('')
  const [suite, setSuite] = useState('')

  const rows = detail.findings.filter(
    (f) => (!severity || f.severity === severity) && (!suite || f.suite === suite),
  )

  const resolve = async (id: string, status: string) => {
    await api.post(`/admin/jurisdictions/evals/findings/${id}/resolve`, { status })
    onResolved()
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {detail.finding_counts.map((c) => (
          <span
            key={`${c.finding_type}-${c.severity}`}
            className="px-2 py-1 rounded border border-zinc-800 text-[11px] text-zinc-400"
          >
            {c.finding_type} {severityBadge(c.severity)} <strong className="text-zinc-200">{c.count}</strong>
          </span>
        ))}
      </div>

      <div className="flex gap-2">
        <select
          value={severity}
          onChange={(e) => setSeverity(e.target.value)}
          className="bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-200"
        >
          <option value="">All severities</option>
          <option value="critical">Critical</option>
          <option value="warn">Warn</option>
          <option value="info">Info</option>
        </select>
        <select
          value={suite}
          onChange={(e) => setSuite(e.target.value)}
          className="bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-200"
        >
          <option value="">All suites</option>
          {SUITES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <span className="text-xs text-zinc-500 self-center">
          showing {rows.length} of {detail.total}
        </span>
      </div>

      <div className="border border-zinc-800 rounded-lg overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-zinc-900/50">
            <tr>
              {['Severity', 'Type', 'Jurisdiction', 'Key', 'Detail', ''].map((h) => (
                <th key={h} className="text-left px-3 py-2 text-[10px] uppercase tracking-wider text-zinc-500">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((f) => (
              <tr key={f.id} className="border-t border-zinc-900">
                <td className="px-3 py-2">{severityBadge(f.severity)}</td>
                <td className="px-3 py-2 text-zinc-300 whitespace-nowrap">{f.finding_type}</td>
                <td className="px-3 py-2 text-zinc-400 whitespace-nowrap">{f.jurisdiction_label || '—'}</td>
                <td className="px-3 py-2 text-zinc-400 font-mono">{f.requirement_key || '—'}</td>
                <td className="px-3 py-2 text-zinc-500 max-w-md truncate">
                  {f.observed ? JSON.stringify(f.observed) : '—'}
                </td>
                <td className="px-3 py-2 whitespace-nowrap">
                  {f.status === 'open' ? (
                    <div className="flex gap-1">
                      <Button variant="ghost" size="sm" onClick={() => resolve(f.id, 'confirmed')}>Confirm</Button>
                      <Button variant="ghost" size="sm" onClick={() => resolve(f.id, 'dismissed')}>Dismiss</Button>
                    </div>
                  ) : (
                    <span className="text-zinc-600">{f.status}</span>
                  )}
                </td>
              </tr>
            ))}
            {!rows.length && (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-zinc-600">No findings match.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Golden panel ──────────────────────────────────────────────────────────────

function GoldenPanel() {
  const [data, setData] = useState<GoldenResponse | null>(null)

  useEffect(() => {
    api.get<GoldenResponse>('/admin/jurisdictions/evals/golden').then(setData).catch(() => {})
  }, [])

  if (!data) return <p className="text-sm text-zinc-600">Loading golden facts…</p>

  const stateCls: Record<string, string> = {
    active: 'text-emerald-400',
    pending: 'text-zinc-500',
    expired: 'text-red-400',
  }

  return (
    <div className="space-y-3">
      <div className="flex gap-4 text-xs text-zinc-400">
        <span><strong className="text-zinc-200">{data.total}</strong> facts</span>
        <span><strong className="text-emerald-400">{data.active}</strong> active today</span>
        <span>
          <strong className={data.unverified ? 'text-amber-400' : 'text-zinc-200'}>{data.unverified}</strong>{' '}
          awaiting human verification
        </span>
      </div>
      {data.unverified > 0 && (
        <p className="text-xs text-amber-400/80 border border-amber-500/30 rounded px-3 py-2">
          Unverified facts are asserted against the catalog but were drafted, not confirmed against the
          primary source by a human. Verify them before trusting the accuracy subscore.
        </p>
      )}
      <div className="border border-zinc-800 rounded-lg overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-zinc-900/50">
            <tr>
              {['State', 'Jurisdiction', 'Key', 'Comparator', 'Window', 'Source', 'Verified'].map((h) => (
                <th key={h} className="text-left px-3 py-2 text-[10px] uppercase tracking-wider text-zinc-500">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.facts.map((f) => (
              <tr key={`${f.jurisdiction}-${f.requirement_key}-${f.effective_from}`} className="border-t border-zinc-900">
                <td className={`px-3 py-2 font-medium ${stateCls[f.state]}`}>{f.state}</td>
                <td className="px-3 py-2 text-zinc-400">{f.jurisdiction}</td>
                <td className="px-3 py-2 text-zinc-300 font-mono">{f.requirement_key}</td>
                <td className="px-3 py-2 text-zinc-500">{f.comparator}</td>
                <td className="px-3 py-2 text-zinc-500">
                  {f.effective_from} → {f.effective_to || '∞'}
                </td>
                <td className="px-3 py-2">
                  <a href={f.authority_url} target="_blank" rel="noreferrer" className="text-blue-400 hover:underline">
                    source
                  </a>
                </td>
                <td className="px-3 py-2 text-zinc-500">{f.verified_by || <span className="text-amber-400">—</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────

type View = 'scorecard' | 'runs' | 'golden' | 'baseline'

export default function EvalsTab() {
  const [view, setView] = useState<View>('scorecard')
  const [cells, setCells] = useState<ScorecardCell[]>([])
  const [runs, setRuns] = useState<EvalRun[]>([])
  const [selectedRun, setSelectedRun] = useState<RunDetail | null>(null)
  const [suites, setSuites] = useState<Suite[]>(['completeness', 'tagging', 'golden'])
  const [triggering, setTriggering] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadScorecard = useCallback(() => {
    api.get<{ cells: ScorecardCell[] }>('/admin/jurisdictions/evals/scorecard')
      .then((r) => setCells(r.cells))
      .catch(() => {})
  }, [])

  const loadRuns = useCallback(() => {
    api.get<{ runs: EvalRun[] }>('/admin/jurisdictions/evals/runs')
      .then((r) => setRuns(r.runs))
      .catch(() => {})
  }, [])

  useEffect(() => {
    loadScorecard()
    loadRuns()
  }, [loadScorecard, loadRuns])

  const openRun = async (id: string) => {
    setSelectedRun(await api.get<RunDetail>(`/admin/jurisdictions/evals/runs/${id}`))
  }

  const trigger = async () => {
    setTriggering(true)
    setError(null)
    try {
      await api.post('/admin/jurisdictions/evals/run', { suites })
      // The run is async on both paths; poll the run list rather than block.
      setTimeout(() => { loadRuns(); loadScorecard() }, 2500)
      setView('runs')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to trigger run')
    } finally {
      setTriggering(false)
    }
  }

  const toggleSuite = (s: Suite) =>
    setSuites((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]))

  return (
    <div className="space-y-5">
      <ReadinessWidget />

      <div className="border border-zinc-800 rounded-lg p-4">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
          <div>
            <h3 className="text-sm font-semibold text-zinc-200">Run evals</h3>
            <p className="text-xs text-zinc-500">
              Read-only over the catalog. `authority` fetches every distinct citation URL and runs on the
              worker.
            </p>
          </div>
          <Button size="sm" onClick={trigger} disabled={triggering || !suites.length}>
            {triggering ? 'Starting…' : 'Run'}
          </Button>
        </div>
        <div className="flex flex-wrap gap-2">
          {SUITES.map((s) => (
            <button
              key={s}
              onClick={() => toggleSuite(s)}
              className={`px-2.5 py-1 rounded text-xs border ${
                suites.includes(s)
                  ? 'border-emerald-600/50 bg-emerald-500/10 text-emerald-300'
                  : 'border-zinc-700 text-zinc-500'
              }`}
            >
              {s}
            </button>
          ))}
        </div>
        {error && <p className="text-xs text-red-400 mt-2">{error}</p>}
      </div>

      <div className="flex gap-1">
        {(['scorecard', 'runs', 'golden', 'baseline'] as View[]).map((v) => (
          <Button key={v} variant={view === v ? 'secondary' : 'ghost'} size="sm" onClick={() => setView(v)}>
            {v[0].toUpperCase() + v.slice(1)}
          </Button>
        ))}
      </div>

      {view === 'scorecard' && <Scorecard cells={cells} />}

      {view === 'golden' && <GoldenPanel />}

      {view === 'baseline' && <BaselinePanel />}

      {view === 'runs' && (
        <div className="space-y-4">
          <div className="border border-zinc-800 rounded-lg overflow-hidden">
            <table className="w-full text-xs">
              <thead className="bg-zinc-900/50">
                <tr>
                  {['Started', 'Suites', 'Status', 'Findings', ''].map((h) => (
                    <th key={h} className="text-left px-3 py-2 text-[10px] uppercase tracking-wider text-zinc-500">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id} className="border-t border-zinc-900">
                    <td className="px-3 py-2 text-zinc-400">{r.started_at?.slice(0, 16).replace('T', ' ')}</td>
                    <td className="px-3 py-2 text-zinc-500">{r.suites.join(', ')}</td>
                    <td className="px-3 py-2">
                      <span
                        className={
                          r.status === 'completed'
                            ? 'text-emerald-400'
                            : r.status === 'failed'
                              ? 'text-red-400'
                              : 'text-amber-400'
                        }
                      >
                        {r.status}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-zinc-300">
                      {(r.totals?.findings as number | undefined) ?? '—'}
                    </td>
                    <td className="px-3 py-2">
                      <Button variant="ghost" size="sm" onClick={() => openRun(r.id)}>View</Button>
                    </td>
                  </tr>
                ))}
                {!runs.length && (
                  <tr>
                    <td colSpan={5} className="px-3 py-6 text-center text-zinc-600">No runs yet.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {selectedRun && (
            <FindingsTable detail={selectedRun} onResolved={() => openRun(selectedRun.run.id)} />
          )}
        </div>
      )}
    </div>
  )
}
