import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { Activity, Loader2, AlertCircle, Users, DollarSign, Globe } from 'lucide-react'
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, ReferenceLine,
} from 'recharts'
import { Card } from '../../components/ui'
import { HelpHint } from '../../components/broker/HelpHint'
import { fetchBookRiskCurve } from '../../api/riskIndex'
import { computeWeightedBookRisk, computeBookLoss, buildLossCurve, type LossPoint } from '../../utils/bookRisk'
import type { BookRiskCurve, BookRiskClient, ExposureBasis } from '../../types/riskIndex'
import { RISK_BAND_TONE, RISK_CONFIDENCE_TONE, EPL_BANDS } from '../../types/riskIndex'

const BAND_ORDER = ['strong', 'adequate', 'developing', 'exposed'] as const
const BAND_LABEL: Record<string, string> = { strong: 'Strong', adequate: 'Adequate', developing: 'Developing', exposed: 'Exposed' }
const BAND_COLOR: Record<string, string> = Object.fromEntries(EPL_BANDS.map((b) => [b.key, b.color]))

const keyOf = (c: BookRiskClient) => `${c.source}:${c.id}`

function fmtUsd(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`
  if (n >= 1_000) return `$${Math.round(n / 1000)}K`
  return `$${Math.round(n)}`
}
function fmtWeight(n: number, basis: ExposureBasis): string {
  return basis === 'headcount' ? `${n.toLocaleString()} emp` : fmtUsd(n)
}

type LossTipProps = { active?: boolean; payload?: Array<{ payload: LossPoint }> }
function LossTip({ active, payload }: LossTipProps) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  const pct = p.exceed >= 0.1 ? (p.exceed * 100).toFixed(0) : (p.exceed * 100).toFixed(1)
  return (
    <div className="bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-xs shadow-lg">
      <div className="text-zinc-100 font-medium">Annual loss ≥ {fmtUsd(p.x)}</div>
      <div className="text-zinc-400 mt-0.5"><span className="font-mono text-zinc-200">{pct}%</span> chance the book loses at least this</div>
    </div>
  )
}

export default function BrokerRiskCurve() {
  const [data, setData] = useState<BookRiskCurve | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [basis, setBasis] = useState<ExposureBasis>('headcount')

  useEffect(() => {
    fetchBookRiskCurve()
      .then((d) => { setData(d); setSelected(new Set(d.clients.map(keyOf))) })
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [])

  const selectedClients = useMemo(
    () => (data ? data.clients.filter((c) => selected.has(keyOf(c))) : []),
    [data, selected],
  )
  const series = useMemo(() => buildLossCurve(selectedClients, basis), [selectedClients, basis])
  const loss = useMemo(() => computeBookLoss(selectedClients, basis), [selectedClients, basis])
  const agg = useMemo(() => computeWeightedBookRisk(selectedClients, basis), [selectedClients, basis])

  function toggle(k: string) {
    setSelected((prev) => { const n = new Set(prev); if (n.has(k)) n.delete(k); else n.add(k); return n })
  }

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>
  if (error || !data) return (
    <div className="flex flex-col items-center justify-center h-64 text-zinc-500">
      <AlertCircle className="h-8 w-8 mb-2" /><p className="text-sm">Unable to load your book risk curve.</p>
    </div>
  )

  const clients = data.clients
  const hasBasis = (c: BookRiskClient) => {
    const v = basis === 'headcount' ? c.headcount : c.annual_premium
    return !!(v && v > 0)
  }
  const excluded = selectedClients.filter((c) => !hasBasis(c)).length

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight flex items-center gap-2">
            <Activity className="h-5 w-5 text-zinc-400" /> Book Risk Curve
            <HelpHint text="Your book's modeled annual loss distribution (log-normal). Expected loss ≈ exposure × loss ratio; each client's risk index drives its volatility, so a couple of risky accounts fatten the right tail. The solid line is expected loss, the dashed line the 99th-percentile (1-in-100) loss. Check/uncheck clients to reshape it — carve a sub-book to market, or see how one risky account fattens the tail. Directional, not a priced actuarial estimate." />
          </h1>
          <p className="text-sm text-zinc-500 mt-1">
            {clients.length} scored client{clients.length === 1 ? '' : 's'}
            {data.counts.external > 0 && ` · ${data.counts.external} off-platform`}
            {' · '}selected {selectedClients.length}
          </p>
        </div>
      </div>

      {clients.length === 0 ? (
        <Card className="p-8 text-center">
          <p className="text-sm text-zinc-400">No scored clients in your book yet.</p>
          <p className="text-xs text-zinc-600 mt-1">Clients gain a risk index once they have WC, EPL, or compliance data on file.</p>
        </Card>
      ) : (
        <>
          {/* Aggregate cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Card className="p-4">
              <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold inline-flex items-center gap-1">Expected annual loss
                <HelpHint text="Expected loss = the AVERAGE yearly loss if you ran this book many times — a long-run average, not a forecast for this one year. Computed as each client's exposure × a 65% loss ratio, summed. It's where the curve is centred (the green line). Half of years come in under it, half over." />
              </div>
              <div className="text-3xl font-light font-mono mt-1 text-zinc-100">{loss.expected_loss > 0 ? fmtUsd(loss.expected_loss) : '—'}</div>
              <div className="text-[10px] text-zinc-600">{loss.modeled_count} client{loss.modeled_count === 1 ? '' : 's'} modeled · {basis}</div>
            </Card>
            <Card className="p-4">
              <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold inline-flex items-center gap-1">PML · 99th pct
                <HelpHint text="PML = Probable Maximum Loss: a realistic worst-case year, not the average. At the 99th percentile it's a roughly 1-in-100-year bad year — you'd expect to lose more than this only about 1 year in 100. It's the far-right tail of the curve (red line). Carriers set limits and price the tail off this number, so risky accounts that stretch it cost real premium." />
              </div>
              <div className="text-3xl font-light font-mono mt-1 text-amber-400">{loss.pml99 > 0 ? fmtUsd(loss.pml99) : '—'}</div>
              <div className="text-[10px] text-zinc-600">1-in-100-yr tail loss</div>
            </Card>
            <Card className="p-4">
              <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold inline-flex items-center gap-1">Book risk index · weighted
                <HelpHint text="Risk index = a 0–100 score of how insurable a client looks (higher = safer), rolled up from their Workers' Comp, EPL and compliance data. This is the exposure-weighted average across the selected book — big accounts count more — so it tells you the risk quality of where your headcount/premium actually sits, not just a simple client average." />
              </div>
              <div className={`text-3xl font-light font-mono mt-1 ${agg.weighted_band ? RISK_BAND_TONE[agg.weighted_band] ?? 'text-zinc-200' : 'text-zinc-600'}`}>
                {agg.weighted_mean ?? '—'}
              </div>
              <div className={`text-[10px] uppercase tracking-widest font-bold ${agg.weighted_band ? RISK_BAND_TONE[agg.weighted_band] ?? 'text-zinc-500' : 'text-zinc-600'}`}>
                {agg.weighted_band ?? 'no exposure data'}
              </div>
            </Card>
            <Card className="p-4">
              <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold inline-flex items-center gap-1">Selected exposure
                <HelpHint text="Exposure = the size measure that drives loss — total headcount (or annual premium) across the checked clients. More exposure means more potential loss, so this is what scales the whole loss curve up or down." />
              </div>
              <div className="text-3xl font-light font-mono mt-1 text-zinc-200">{fmtWeight(agg.total_weight, basis)}</div>
              <div className="text-[10px] text-zinc-600">{selectedClients.length} of {clients.length} clients</div>
            </Card>
          </div>

          {/* Band mix strip */}
          <Card className="p-3">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold inline-flex items-center gap-1">Exposure by risk band
                <HelpHint text="How your book's headcount/premium splits across the four risk bands — Strong (green) → Exposed (red). A book heavy in Developing/Exposed is concentrated in risky accounts even if the average looks fine." />
              </span>
              <div className="flex flex-wrap gap-x-3">
                {BAND_ORDER.map((b) => (agg.band_mix[b] ?? 0) > 0 ? (
                  <span key={b} className="text-[9px] text-zinc-500 inline-flex items-center gap-1">
                    <span className="h-1.5 w-1.5 rounded-full" style={{ background: BAND_COLOR[b] }} />{BAND_LABEL[b]} {Math.round((agg.band_mix[b] ?? 0) * 100)}%
                  </span>
                ) : null)}
              </div>
            </div>
            <div className="flex h-2.5 rounded-full overflow-hidden bg-zinc-800">
              {BAND_ORDER.map((b) => {
                const pct = (agg.band_mix[b] ?? 0) * 100
                return pct > 0 ? <div key={b} style={{ width: `${pct}%`, background: BAND_COLOR[b] }} title={`${BAND_LABEL[b]} ${pct.toFixed(0)}%`} /> : null
              })}
            </div>
          </Card>

          {/* Controls */}
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-zinc-600 uppercase tracking-widest font-bold mr-1 inline-flex items-center gap-1">Weight by
                <HelpHint text="Which exposure measure drives the loss model. Headcount uses ~$1,200 premium/employee; Premium uses the recorded annual WC premium. Clients missing the chosen measure drop out of the curve (still listed)." />
              </span>
              {(['headcount', 'premium'] as ExposureBasis[]).map((b) => (
                <button key={b} onClick={() => setBasis(b)}
                  className={`inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg border transition-colors ${basis === b ? 'bg-zinc-100 text-zinc-900 border-zinc-100' : 'text-zinc-300 border-zinc-700 hover:border-zinc-500'}`}>
                  {b === 'headcount' ? <Users className="h-3.5 w-3.5" /> : <DollarSign className="h-3.5 w-3.5" />}
                  {b === 'headcount' ? 'Headcount' : 'Premium'}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <button onClick={() => setSelected(new Set(clients.map(keyOf)))} className="text-xs text-zinc-300 hover:text-zinc-100 px-2 py-1 rounded-lg border border-zinc-700 hover:border-zinc-500">All</button>
              <button onClick={() => setSelected(new Set())} className="text-xs text-zinc-300 hover:text-zinc-100 px-2 py-1 rounded-lg border border-zinc-700 hover:border-zinc-500">Clear</button>
              <span className="text-zinc-700">·</span>
              {BAND_ORDER.map((b) => (
                <button key={b} onClick={() => setSelected(new Set(clients.filter((c) => c.band === b).map(keyOf)))}
                  className="text-[11px] px-2 py-1 rounded-lg border border-zinc-800 hover:border-zinc-600 inline-flex items-center gap-1">
                  <span className="h-1.5 w-1.5 rounded-full" style={{ background: BAND_COLOR[b] }} />{BAND_LABEL[b]}
                </button>
              ))}
            </div>
          </div>

          {/* Chart — modeled aggregate annual loss distribution (log-normal) */}
          <Card className="p-5">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold inline-flex items-center gap-1">Modeled annual loss distribution
                <HelpHint text="How to read it: the curve is the chance of each annual-loss outcome — taller = more likely. The hump near the green line is your most-likely loss; the long right tail is the rare severe year. A longer, fatter tail = a riskier book (a few exposed accounts stretch it right). Hover any point for the odds of the book losing at least that much." />
              </span>
              <span className="text-[10px] text-zinc-600 font-mono">X = annual loss · Y = likelihood</span>
            </div>
            <div className="flex items-center gap-4 mb-2 text-[10px] text-zinc-500 flex-wrap">
              <span className="inline-flex items-center gap-1.5"><span className="inline-block w-4 border-t-2 border-dashed border-emerald-400" /> Expected loss</span>
              <span className="inline-flex items-center gap-1.5"><span className="inline-block w-4 border-t-2 border-dashed border-red-400" /> PML 99% (tail)</span>
              <span className="inline-flex items-center gap-1.5">
                <span className="inline-block h-2 w-14 rounded" style={{ background: 'linear-gradient(90deg,#34d399,#f59e0b,#ef4444)' }} />
                smaller / likely → severe / rare
              </span>
            </div>
            <div className="h-[300px]">
              {series.length === 0 ? (
                <div className="flex items-center justify-center h-full text-sm text-zinc-600">Select clients with exposure ({basis}) to model the loss curve.</div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={series} margin={{ top: 14, right: 28, bottom: 6, left: 0 }}>
                    <defs>
                      <linearGradient id="bookGrad" x1="0" y1="0" x2="1" y2="0">
                        <stop offset="0%" stopColor="#34d399" stopOpacity={0.35} />
                        <stop offset="60%" stopColor="#f59e0b" stopOpacity={0.25} />
                        <stop offset="100%" stopColor="#ef4444" stopOpacity={0.3} />
                      </linearGradient>
                    </defs>
                    <XAxis type="number" dataKey="x" domain={[0, 'dataMax']} tickFormatter={(v) => fmtUsd(v as number)}
                      tick={{ fill: '#71717a', fontSize: 10 }} axisLine={{ stroke: '#27272a' }} tickLine={false} interval="preserveStartEnd" />
                    <YAxis tick={false} axisLine={false} tickLine={false} width={8} />
                    <Tooltip content={<LossTip />} />
                    {loss.expected_loss > 0 && (
                      <ReferenceLine x={loss.expected_loss} stroke="#10b981" strokeDasharray="4 4" strokeWidth={1.5}
                        label={{ value: 'expected', position: 'top', fill: '#10b981', fontSize: 9 }} />
                    )}
                    {loss.pml99 > 0 && (
                      <ReferenceLine x={loss.pml99} stroke="#ef4444" strokeDasharray="4 4" strokeWidth={1.5}
                        label={{ value: 'PML 99%', position: 'top', fill: '#ef4444', fontSize: 9 }} />
                    )}
                    <Area type="monotone" dataKey="density" stroke="#e4e4e7" strokeWidth={1.5} fill="url(#bookGrad)" dot={false} isAnimationActive={false} />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </div>
            <div className="text-[10px] text-zinc-600 mt-2 flex flex-wrap items-center gap-1">
              <span>Modeled: expected loss ≈ {basis === 'premium' ? 'premium' : 'headcount × ~$1,200'} × 65% loss ratio; volatility scales with each client's risk index. Directional, not a priced estimate.</span>
              <HelpHint text="Loss ratio = the share of premium expected to be paid out as claims; ~65% is a typical permissible Workers' Comp loss ratio, so expected loss ≈ premium × 0.65. Volatility = how much actual losses swing year to year — we scale it by each client's risk index, so exposed clients widen the tail and strong ones tighten it." />
              {excluded > 0 && <span>· {excluded} selected client{excluded === 1 ? '' : 's'} not modeled (no {basis} on file).</span>}
            </div>
          </Card>

          {/* Non-Pro upsell */}
          {!data.is_pro && (
            <Card className="p-3 border-emerald-500/20 bg-emerald-500/[0.04]">
              <p className="text-xs text-zinc-400 inline-flex items-center gap-2">
                <Globe className="h-3.5 w-3.5 text-emerald-500" />
                This curve covers your on-platform book. <Link to="/broker/account" className="text-emerald-400 hover:underline">Broker Pro</Link> folds in your off-platform clients too.
              </p>
            </Card>
          )}

          {/* Client list */}
          <Card className="p-0 overflow-hidden">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-800/60 bg-zinc-900/40">
                  <th className="px-4 py-2.5 w-8"></th>
                  <th className="px-4 py-2.5 text-[11px] font-medium text-zinc-500 uppercase tracking-wider">Client</th>
                  <th className="px-4 py-2.5 text-[11px] font-medium text-zinc-500 uppercase tracking-wider">Industry</th>
                  <th className="px-4 py-2.5 text-[11px] font-medium text-zinc-500 uppercase tracking-wider text-right">Risk</th>
                  <th className="px-4 py-2.5 text-[11px] font-medium text-zinc-500 uppercase tracking-wider text-right">{basis === 'headcount' ? 'Headcount' : 'Premium'}</th>
                </tr>
              </thead>
              <tbody>
                {clients.map((c) => {
                  const k = keyOf(c)
                  const on = selected.has(k)
                  const missing = !hasBasis(c)
                  return (
                    <tr key={k} className={`border-b border-zinc-800/30 last:border-0 hover:bg-zinc-900/30 ${on ? '' : 'opacity-50'}`}>
                      <td className="px-4 py-2.5">
                        <input type="checkbox" checked={on} onChange={() => toggle(k)}
                          className="rounded border-zinc-600 bg-zinc-800 text-emerald-500 focus:ring-emerald-500" />
                      </td>
                      <td className="px-4 py-2.5 text-zinc-200">
                        {c.name}
                        {c.source === 'external' && <span className="ml-2 text-[9px] uppercase tracking-wider text-emerald-500 font-bold">External</span>}
                      </td>
                      <td className="px-4 py-2.5 text-zinc-500 text-xs">{c.industry ?? '—'}</td>
                      <td className={`px-4 py-2.5 text-right font-mono ${RISK_BAND_TONE[c.band] ?? 'text-zinc-400'}`}>
                        {c.index} <span className="text-[10px] uppercase">{BAND_LABEL[c.band] ?? c.band}</span>
                        {c.confidence && c.confidence !== 'high' && (
                          <span className={`ml-1.5 inline-block h-1.5 w-1.5 rounded-full bg-current align-middle ${RISK_CONFIDENCE_TONE[c.confidence]}`}
                            title={`${c.confidence} confidence — some inputs rest on directional or thin data`} />
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono text-zinc-400">
                        {missing ? <span className="text-[10px] text-zinc-600 normal-case">no {basis}</span>
                          : fmtWeight(basis === 'headcount' ? (c.headcount as number) : (c.annual_premium as number), basis)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </div>
  )
}
