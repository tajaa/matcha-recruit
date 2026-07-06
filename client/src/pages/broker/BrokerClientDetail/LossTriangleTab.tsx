import { useState, useEffect, useRef } from 'react'
import { Plus, FileDown, Loader2, Upload, Trash2 } from 'lucide-react'
import { Card } from '../../../components/ui'
import {
  fetchClientLossDevelopment, parseClientLossRun, commitClientLossRun,
  deleteClientLossRunSnapshot, downloadClientLossDevelopment,
} from '../../../api/broker'
import type { LossDevelopment, LossRunDraftPeriod } from '../../../types/lossDevelopment'
import { LOSS_LINES } from '../../../types/lossDevelopment'
import { fmtMoney } from '../../../types/limitAdequacy'

export function LossTriangleTab({ companyId }: { companyId: string }) {
  const [dev, setDev] = useState<LossDevelopment | null>(null)
  const [loading, setLoading] = useState(true)
  const [dl, setDl] = useState(false)
  const [adding, setAdding] = useState(false)

  function load() {
    setLoading(true)
    fetchClientLossDevelopment(companyId).then(setDev).catch(() => setDev(null)).finally(() => setLoading(false))
  }
  useEffect(load, [companyId])

  if (loading) return <Loader2 className="h-5 w-5 text-zinc-500 animate-spin" />
  if (!dev) return <Card className="p-5"><p className="text-sm text-zinc-500">No loss-development data.</p></Card>

  const linesWithData = dev.lines.filter((l) => l.periods.length > 0)
  return (
    <Card className="p-5 space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-sm font-medium text-zinc-200">Loss Development Triangle</h3>
          <p className="text-[11px] text-zinc-500 max-w-xl">Same policy years valued at multiple dates → development factors → projected ultimate. The gap to ultimate is adverse development (reserve adequacy).</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button onClick={() => setAdding((v) => !v)} className="inline-flex items-center gap-1 text-xs text-zinc-300 hover:text-zinc-100 px-2.5 py-1.5 rounded-lg border border-zinc-700"><Plus className="h-3.5 w-3.5" /> Add loss run</button>
          <button onClick={async () => { setDl(true); try { await downloadClientLossDevelopment(companyId) } finally { setDl(false) } }} disabled={dl}
            className="inline-flex items-center gap-1.5 text-xs text-zinc-900 bg-zinc-100 hover:bg-white rounded-lg px-3 py-1.5 font-medium disabled:opacity-50">
            {dl ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileDown className="h-3.5 w-3.5" />} Loss-dev packet
          </button>
        </div>
      </div>

      {adding && <LossRunForm companyId={companyId} onDone={(d) => { setDev(d); setAdding(false) }} onCancel={() => setAdding(false)} />}

      {linesWithData.length === 0 ? (
        <p className="text-sm text-zinc-600">No loss runs on file. Add at least two valuations of the same policy years to build a triangle.</p>
      ) : linesWithData.map((ln) => {
        const mats = Array.from(new Set(ln.periods.flatMap((p) => p.points.map((pt) => pt.maturity)))).sort((a, b) => a - b)
        const s = ln.summary
        return (
          <div key={ln.line} className="space-y-2">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-semibold text-zinc-300 uppercase tracking-wide">{ln.label}</h4>
              <span className="text-[11px] text-zinc-500">
                reported {fmtMoney(s.total_latest_incurred)} → ultimate {fmtMoney(s.total_ultimate)}{' '}
                <span className={s.total_adverse_development > 0 ? 'text-red-400' : 'text-emerald-400'}>
                  ({s.total_adverse_development > 0 ? '+' : ''}{fmtMoney(s.total_adverse_development)}, {s.adverse_pct}%)
                </span>{' '}
                {s.reserve_confidence === 'low' ? (
                  <span className="text-amber-500/80">· low confidence (thin development history)</span>
                ) : s.total_ultimate_low !== null && s.total_ultimate_high !== null ? (
                  <span className="text-zinc-600">· {fmtMoney(s.total_ultimate_low)}–{fmtMoney(s.total_ultimate_high)} range ({s.reserve_confidence})</span>
                ) : null}
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-[10px] text-zinc-600 uppercase border-b border-zinc-800">
                    <th className="text-left font-medium py-1 pr-2">Policy yr</th>
                    {mats.map((m) => <th key={m} className="text-right font-medium px-2">{m}mo</th>)}
                    <th className="text-right font-medium px-2">Ultimate</th>
                    <th className="text-right font-medium px-2">Adverse</th>
                  </tr>
                </thead>
                <tbody>
                  {ln.periods.map((p) => {
                    const byMat = Object.fromEntries(p.points.map((pt) => [pt.maturity, pt]))
                    return (
                      <tr key={p.period_label} className="border-b border-zinc-800/30">
                        <td className="py-1 pr-2 text-zinc-200">{p.period_label}</td>
                        {mats.map((m) => <td key={m} className="px-2 text-right font-mono text-zinc-300">{byMat[m] ? fmtMoney(byMat[m].incurred) : ''}</td>)}
                        <td className="px-2 text-right font-mono text-zinc-100">
                          {fmtMoney(p.ultimate)}
                          {p.reserve_confidence === 'low' ? (
                            <div className="text-[9px] font-sans text-amber-500/70 normal-case">low confidence</div>
                          ) : p.ultimate_low !== null && p.ultimate_high !== null && p.ultimate_low !== p.ultimate_high ? (
                            <div className="text-[9px] font-sans text-zinc-600 normal-case">±{fmtMoney((p.ultimate_high - p.ultimate_low) / 2)}</div>
                          ) : null}
                        </td>
                        <td className={`px-2 text-right font-mono ${p.adverse_development > 0 ? 'text-red-400' : 'text-zinc-500'}`}>{p.adverse_development > 0 ? '+' : ''}{fmtMoney(p.adverse_development)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <p className="text-[10px] text-zinc-600">
              Age-to-age (simple avg): {ln.factors.length ? ln.factors.map((f) => `${f.from_maturity}→${f.to_maturity}mo ${f.factor}`).join(' · ') : 'need ≥2 valuations'} · {s.valuations} valuation(s)
            </p>
          </div>
        )
      })}

      {dev.snapshots.length > 0 && (
        <div className="pt-2 border-t border-zinc-800/40">
          <div className="text-[10px] text-zinc-600 uppercase tracking-wide mb-1">Loss runs on file</div>
          <div className="space-y-0.5">
            {dev.snapshots.map((s) => (
              <div key={s.id} className="flex items-center gap-2 text-[11px] text-zinc-500 py-0.5">
                <span className="font-mono text-zinc-400">{s.valuation_date}</span>
                <span>{s.line.toUpperCase()} {s.policy_period_label}</span>
                <span className="font-mono">{fmtMoney(s.paid + s.reserved)}</span>
                <span className="text-zinc-700">· {s.claim_count} claims</span>
                <button onClick={async () => setDev(await deleteClientLossRunSnapshot(companyId, s.id))} className="ml-auto text-zinc-600 hover:text-red-400"><Trash2 className="h-3.5 w-3.5" /></button>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  )
}

function emptyLossPeriod(): LossRunDraftPeriod {
  return { policy_period_label: '', policy_period_start: null, claim_count: 0, open_count: 0, paid: 0, reserved: 0 }
}

function LossRunForm({ companyId, onDone, onCancel }: { companyId: string; onDone: (d: LossDevelopment) => void; onCancel: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [valuationDate, setValuationDate] = useState('')
  const [line, setLine] = useState('wc')
  const [periods, setPeriods] = useState<LossRunDraftPeriod[]>([emptyLossPeriod()])
  const [parsing, setParsing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setParsing(true); setMsg(null)
    try {
      const draft = await parseClientLossRun(companyId, file)
      if (!draft.available) { setMsg('Could not extract — enter the figures manually.'); return }
      if (draft.valuation_date) setValuationDate(draft.valuation_date)
      if (draft.line) setLine(draft.line)
      if (draft.periods.length) setPeriods(draft.periods)
      setMsg(`Extracted ${draft.periods.length} policy period(s) — confirm and commit.`)
    } catch { setMsg('Upload failed. Use a PDF under 15 MB.') } finally {
      setParsing(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  function patch(i: number, p: Partial<LossRunDraftPeriod>) {
    setPeriods((ps) => ps.map((r, idx) => (idx === i ? { ...r, ...p } : r)))
  }
  function num(s: string): number { const v = parseFloat(s.replace(/[$,\s]/g, '')); return Number.isFinite(v) ? v : 0 }

  async function commit() {
    if (!valuationDate) { setMsg('Set the valuation (as-of) date.'); return }
    const cleaned = periods.filter((p) => p.policy_period_label.trim())
    if (!cleaned.length) { setMsg('Add at least one policy period.'); return }
    setBusy(true)
    try { onDone(await commitClientLossRun(companyId, { valuation_date: valuationDate, line, source: 'broker-entry', periods: cleaned })) }
    finally { setBusy(false) }
  }

  return (
    <div className="bg-zinc-900/60 border border-zinc-800 rounded-xl p-3 space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <button onClick={() => fileRef.current?.click()} disabled={parsing} className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg px-2.5 py-1.5 disabled:opacity-50">
          {parsing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />} Upload loss-run PDF
        </button>
        <input ref={fileRef} type="file" accept="application/pdf,.pdf" onChange={onFile} className="hidden" />
        <label className="text-[10px] text-zinc-500 uppercase ml-2">As-of date</label>
        <input type="date" value={valuationDate} onChange={(e) => setValuationDate(e.target.value)} className="bg-zinc-900 border border-zinc-700 rounded-lg px-2 py-1 text-xs text-zinc-200" />
        <select value={line} onChange={(e) => setLine(e.target.value)} className="bg-zinc-900 border border-zinc-700 rounded-lg px-2 py-1 text-xs text-zinc-200">
          {LOSS_LINES.map((l) => <option key={l.key} value={l.key}>{l.label}</option>)}
        </select>
      </div>
      {msg && <div className="text-[11px] text-amber-400">{msg}</div>}
      <div className="space-y-1">
        <div className="grid grid-cols-[1fr_5rem_5rem_4rem_4rem_auto] gap-1 text-[9px] text-zinc-600 uppercase px-1">
          <span>Policy yr</span><span className="text-right">Paid</span><span className="text-right">Reserved</span><span className="text-right">Claims</span><span className="text-right">Open</span><span></span>
        </div>
        {periods.map((p, i) => (
          <div key={i} className="grid grid-cols-[1fr_5rem_5rem_4rem_4rem_auto] gap-1 items-center">
            <input value={p.policy_period_label} onChange={(e) => patch(i, { policy_period_label: e.target.value })} placeholder="2023" className="bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-200" />
            <input value={p.paid || ''} onChange={(e) => patch(i, { paid: num(e.target.value) })} placeholder="0" className="bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-200 text-right font-mono" />
            <input value={p.reserved || ''} onChange={(e) => patch(i, { reserved: num(e.target.value) })} placeholder="0" className="bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-200 text-right font-mono" />
            <input value={p.claim_count || ''} onChange={(e) => patch(i, { claim_count: Math.round(num(e.target.value)) })} placeholder="0" className="bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-200 text-right font-mono" />
            <input value={p.open_count || ''} onChange={(e) => patch(i, { open_count: Math.round(num(e.target.value)) })} placeholder="0" className="bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-200 text-right font-mono" />
            <button onClick={() => setPeriods((ps) => ps.filter((_, idx) => idx !== i))} className="text-zinc-600 hover:text-red-400 p-1"><Trash2 className="h-3.5 w-3.5" /></button>
          </div>
        ))}
        <button onClick={() => setPeriods((ps) => [...ps, emptyLossPeriod()])} className="inline-flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-100"><Plus className="h-3.5 w-3.5" /> Add policy year</button>
      </div>
      <div className="flex items-center gap-2 pt-1">
        <button onClick={commit} disabled={busy} className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg px-3 py-1.5 disabled:opacity-50">
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />} Commit valuation
        </button>
        <button onClick={onCancel} className="text-xs text-zinc-400 hover:text-zinc-100 px-3 py-1.5 rounded-lg border border-zinc-700">Cancel</button>
      </div>
    </div>
  )
}
