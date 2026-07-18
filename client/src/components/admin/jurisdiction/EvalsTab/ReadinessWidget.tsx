import { useCallback, useState } from 'react'
import { api } from '../../../../api/client'
import { Button } from '../../../ui'
import { CoreChecklistPanel } from './ChecklistByCategory'
import { CORE_INDUSTRIES, INDUSTRIES } from './constants'
import { fmtScore, scoreColor, statusBadge } from './helpers'
import type { Readiness } from './types'

export function ReadinessWidget() {
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
