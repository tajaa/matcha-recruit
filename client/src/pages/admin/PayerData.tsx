import { useState, useEffect, useCallback } from 'react'
import { Button } from '../../components/ui'
import {
  fetchPayerOverview,
  fetchPayerIntegrity,
  runPayerStalenessCheck,
  runCmsIngest,
} from '../../api/compliance'
import type { PayerOverviewResponse, PayerIntegrityResponse } from '../../api/compliance'

type Tab = 'overview' | 'integrity' | 'changelog'

function Section({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  const [open, setOpen] = useState(count > 0)
  return (
    <div className="border border-zinc-700/50 rounded-lg overflow-hidden">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center justify-between px-4 py-3 bg-zinc-800/50 hover:bg-zinc-800 text-left">
        <span className="text-sm font-medium text-zinc-200">{title}</span>
        <div className="flex items-center gap-2">
          <span className={`px-2 py-0.5 text-xs font-bold rounded ${count > 0 ? 'bg-red-500/20 text-red-400' : 'bg-zinc-700 text-zinc-500'}`}>{count}</span>
          <span className="text-zinc-600">{open ? '▾' : '▸'}</span>
        </div>
      </button>
      {open && <div className="p-1">{children}</div>}
    </div>
  )
}

export default function PayerData() {
  const [tab, setTab] = useState<Tab>('overview')
  const [overview, setOverview] = useState<PayerOverviewResponse | null>(null)
  const [integrity, setIntegrity] = useState<PayerIntegrityResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState<string | null>(null)

  const loadOverview = useCallback(() => {
    setLoading(true)
    fetchPayerOverview().then(setOverview).catch(() => {}).finally(() => setLoading(false))
  }, [])

  const loadIntegrity = useCallback(() => {
    fetchPayerIntegrity().then(setIntegrity).catch(() => {})
  }, [])

  useEffect(() => { loadOverview() }, [loadOverview])
  useEffect(() => { if (tab === 'integrity' || tab === 'changelog') loadIntegrity() }, [tab, loadIntegrity])

  const handleStalenessCheck = async () => {
    setRunning('staleness')
    try {
      const r = await runPayerStalenessCheck()
      alert(`Created ${r.alerts_created} alerts, resolved ${r.alerts_resolved}, found ${r.stale_found} stale`)
      loadIntegrity()
    } catch { /* ignore */ }
    finally { setRunning(null) }
  }

  const handleCmsIngest = async () => {
    setRunning('ingest')
    try {
      const r = await runCmsIngest()
      alert(`CMS ingest complete: ${JSON.stringify(r)}`)
      loadOverview()
      loadIntegrity()
    } catch { /* ignore */ }
    finally { setRunning(null) }
  }

  const o = overview

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-4">
      <div>
        <h1 className="text-xl font-bold text-zinc-100">Payer Data</h1>
        <p className="text-sm text-zinc-500">Medical coverage policies — Medicare NCDs/LCDs and commercial payer research</p>
      </div>

      {/* KPI Bar */}
      {o && (
        <div className="grid grid-cols-5 gap-3">
          {[
            { label: 'Policies', value: o.total.toLocaleString() },
            { label: 'Payers', value: o.payer_count.toLocaleString() },
            { label: 'Covered', value: o.coverage.covered.toLocaleString(), color: 'text-emerald-400' },
            { label: 'Stale >90d', value: o.staleness.warning.toLocaleString(), color: o.staleness.warning > 0 ? 'text-amber-400' : 'text-emerald-400' },
            { label: 'Last Ingest', value: o.last_ingest ? new Date(o.last_ingest).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' }) : '—' },
          ].map(s => (
            <div key={s.label} className="border border-zinc-800 rounded-lg px-3 py-3">
              <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">{s.label}</p>
              <p className={`text-2xl font-bold tracking-tight mt-0.5 ${'color' in s && s.color ? s.color : 'text-zinc-100'}`}>{s.value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div className="flex items-center gap-1">
        {([
          { id: 'overview' as Tab, label: 'Overview' },
          { id: 'integrity' as Tab, label: 'Integrity' },
          { id: 'changelog' as Tab, label: 'Change Log' },
        ]).map(t => (
          <Button key={t.id} variant={tab === t.id ? 'secondary' : 'ghost'} size="sm" onClick={() => setTab(t.id)}>{t.label}</Button>
        ))}
        <div className="ml-auto flex gap-2">
          <Button variant="ghost" size="sm" disabled={running === 'ingest'} onClick={handleCmsIngest}>
            {running === 'ingest' ? 'Ingesting...' : 'Run CMS Ingest'}
          </Button>
          <Button variant="ghost" size="sm" onClick={loadOverview}>Refresh</Button>
        </div>
      </div>

      {loading ? (
        <div className="text-zinc-500 py-12 text-center">Loading...</div>
      ) : (
        <>
          {/* Overview */}
          {tab === 'overview' && o && (
            <div className="space-y-4">
              {/* Field completeness */}
              <div className="border border-zinc-800 rounded-lg p-4">
                <h3 className="text-xs text-zinc-400 uppercase tracking-wide mb-3">Field Completeness</h3>
                <div className="grid grid-cols-3 gap-4">
                  {[
                    { label: 'Clinical Criteria', pct: o.field_completeness.clinical_criteria_pct },
                    { label: 'Procedure Codes', pct: o.field_completeness.procedure_codes_pct },
                    { label: 'Source URL', pct: o.field_completeness.source_url_pct },
                  ].map(f => (
                    <div key={f.label}>
                      <div className="flex justify-between text-xs mb-1">
                        <span className="text-zinc-400">{f.label}</span>
                        <span className={f.pct >= 80 ? 'text-emerald-400' : f.pct >= 50 ? 'text-amber-400' : 'text-red-400'}>{f.pct}%</span>
                      </div>
                      <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                        <div className={`h-full rounded-full ${f.pct >= 80 ? 'bg-emerald-500' : f.pct >= 50 ? 'bg-amber-500' : 'bg-red-500'}`} style={{ width: `${f.pct}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Coverage breakdown */}
              <div className="border border-zinc-800 rounded-lg p-4">
                <h3 className="text-xs text-zinc-400 uppercase tracking-wide mb-3">Coverage Status</h3>
                <div className="flex gap-6 text-sm">
                  <div><span className="text-emerald-400 font-bold">{o.coverage.covered}</span> <span className="text-zinc-500">covered</span></div>
                  <div><span className="text-amber-400 font-bold">{o.coverage.conditional}</span> <span className="text-zinc-500">conditional</span></div>
                  <div><span className="text-red-400 font-bold">{o.coverage.not_covered}</span> <span className="text-zinc-500">not covered</span></div>
                </div>
              </div>

              {/* By payer */}
              <div className="border border-zinc-800 rounded-lg p-4">
                <h3 className="text-xs text-zinc-400 uppercase tracking-wide mb-3">By Payer</h3>
                <table className="w-full text-sm">
                  <thead className="text-zinc-500 text-xs uppercase">
                    <tr>
                      <th className="text-left py-1 px-2">Payer</th>
                      <th className="text-right py-1 px-2">Policies</th>
                      <th className="text-right py-1 px-2">Covered</th>
                      <th className="text-right py-1 px-2">Conditional</th>
                    </tr>
                  </thead>
                  <tbody>
                    {o.by_payer.map(p => (
                      <tr key={p.payer} className="border-t border-zinc-800/30">
                        <td className="py-1.5 px-2 text-zinc-200">{p.payer}</td>
                        <td className="py-1.5 px-2 text-right font-mono text-zinc-400">{p.count}</td>
                        <td className="py-1.5 px-2 text-right font-mono text-emerald-400">{p.covered}</td>
                        <td className="py-1.5 px-2 text-right font-mono text-amber-400">{p.conditional}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Integrity */}
          {tab === 'integrity' && integrity && (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <Button variant="ghost" size="sm" disabled={running === 'staleness'} onClick={handleStalenessCheck}>
                  {running === 'staleness' ? 'Running...' : 'Run Staleness Check'}
                </Button>
              </div>

              <Section title="Stale Policies" count={integrity.stale_count}>
                {integrity.stale_policies.length === 0 ? (
                  <div className="px-4 py-3 text-sm text-zinc-500">No stale policies</div>
                ) : (
                  <table className="w-full text-xs">
                    <thead className="text-zinc-500 uppercase bg-zinc-800/30">
                      <tr>
                        <th className="px-3 py-2 text-left">Payer</th>
                        <th className="px-3 py-2 text-left">Policy</th>
                        <th className="px-3 py-2 text-left">Title</th>
                        <th className="px-3 py-2 text-center">Days</th>
                        <th className="px-3 py-2 text-left">Level</th>
                      </tr>
                    </thead>
                    <tbody>
                      {integrity.stale_policies.map(s => (
                        <tr key={s.id} className="border-t border-zinc-800/30">
                          <td className="px-3 py-1.5 text-zinc-300">{s.payer}</td>
                          <td className="px-3 py-1.5 font-mono text-zinc-400">{s.policy_number}</td>
                          <td className="px-3 py-1.5 text-zinc-400 max-w-xs truncate">{s.title}</td>
                          <td className="px-3 py-1.5 text-center font-mono">{s.days_since_verified}</td>
                          <td className="px-3 py-1.5">
                            <span className={s.level === 'critical' ? 'text-red-400 font-bold' : 'text-yellow-400'}>{s.level.toUpperCase()}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Section>

              <Section title="Missing Fields" count={integrity.missing_fields_count}>
                {integrity.missing_fields.length === 0 ? (
                  <div className="px-4 py-3 text-sm text-zinc-500">All fields complete</div>
                ) : (
                  <table className="w-full text-xs">
                    <thead className="text-zinc-500 uppercase bg-zinc-800/30">
                      <tr>
                        <th className="px-3 py-2 text-left">Policy</th>
                        <th className="px-3 py-2 text-left">Title</th>
                        <th className="px-3 py-2 text-left">Missing</th>
                      </tr>
                    </thead>
                    <tbody>
                      {integrity.missing_fields.slice(0, 50).map(m => (
                        <tr key={m.id} className="border-t border-zinc-800/30">
                          <td className="px-3 py-1.5 font-mono text-zinc-400">{m.policy_number}</td>
                          <td className="px-3 py-1.5 text-zinc-400 max-w-xs truncate">{m.title}</td>
                          <td className="px-3 py-1.5 text-red-400 text-[11px]">{m.missing.join(', ')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Section>

              <Section title="Low Confidence" count={integrity.low_confidence_count}>
                {integrity.low_confidence.length === 0 ? (
                  <div className="px-4 py-3 text-sm text-zinc-500">No low-confidence policies</div>
                ) : (
                  <table className="w-full text-xs">
                    <thead className="text-zinc-500 uppercase bg-zinc-800/30">
                      <tr>
                        <th className="px-3 py-2 text-left">Payer</th>
                        <th className="px-3 py-2 text-left">Policy</th>
                        <th className="px-3 py-2 text-left">Title</th>
                        <th className="px-3 py-2 text-center">Confidence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {integrity.low_confidence.map(lc => (
                        <tr key={lc.id} className="border-t border-zinc-800/30">
                          <td className="px-3 py-1.5 text-zinc-300">{lc.payer}</td>
                          <td className="px-3 py-1.5 font-mono text-zinc-400">{lc.policy_number}</td>
                          <td className="px-3 py-1.5 text-zinc-400 max-w-xs truncate">{lc.title}</td>
                          <td className="px-3 py-1.5 text-center font-mono text-red-400">{(lc.confidence * 100).toFixed(0)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Section>
            </div>
          )}

          {/* Change Log */}
          {tab === 'changelog' && integrity && (
            <div className="space-y-4">
              <Section title="Recent Changes (30 days)" count={integrity.recent_changes_count}>
                {integrity.recent_changes.length === 0 ? (
                  <div className="px-4 py-3 text-sm text-zinc-500">No recent changes — run CMS Ingest to detect updates</div>
                ) : (
                  <table className="w-full text-xs">
                    <thead className="text-zinc-500 uppercase bg-zinc-800/30">
                      <tr>
                        <th className="px-3 py-2 text-left">Policy</th>
                        <th className="px-3 py-2 text-left">Field</th>
                        <th className="px-3 py-2 text-left">Old Value</th>
                        <th className="px-3 py-2 text-left">Source</th>
                        <th className="px-3 py-2 text-left">Date</th>
                      </tr>
                    </thead>
                    <tbody>
                      {integrity.recent_changes.map(c => (
                        <tr key={c.id} className="border-t border-zinc-800/30">
                          <td className="px-3 py-1.5">
                            <span className="font-mono text-zinc-400">{c.policy_number}</span>
                            <span className="text-zinc-600 ml-1">{c.title}</span>
                          </td>
                          <td className="px-3 py-1.5 text-amber-400">{c.field}</td>
                          <td className="px-3 py-1.5 text-zinc-500 max-w-xs truncate">{c.old_value || '—'}</td>
                          <td className="px-3 py-1.5 text-zinc-500">{c.source}</td>
                          <td className="px-3 py-1.5 text-zinc-500">{c.changed_at ? new Date(c.changed_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Section>
            </div>
          )}
        </>
      )}
    </div>
  )
}
