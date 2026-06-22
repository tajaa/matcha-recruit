import { useState, useEffect, type FormEvent, type ChangeEvent, type ReactNode } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Loader2, AlertCircle, Gauge, Shield, Upload, Link2 as LinkIcon, CheckCircle2, Clock, CircleDashed } from 'lucide-react'
import { Card } from '../../components/ui'
import { HelpHint } from '../../components/broker/HelpHint'
import { SubmissionPanel } from '../../components/broker/SubmissionPanel'
import {
  fetchExternalClientDetail, saveExternalWc, saveExternalEplAttestation,
  downloadExternalSubmission, fetchExternalCoverageGap, parseExternalLossRun,
  createExternalIntakeLink,
} from '../../api/broker'
import type { ExternalClientDetail, ExternalEplFactor, EplAttestationStatus } from '../../types/broker'
import { RISK_BAND_TONE } from '../../types/riskIndex'

const WC_TONE: Record<string, string> = {
  critical: 'text-red-400', at_risk: 'text-orange-400', fair: 'text-amber-400',
  good: 'text-emerald-400', unknown: 'text-zinc-600',
}
const EPL_TONE: Record<string, string> = {
  strong: 'text-emerald-400', adequate: 'text-amber-400', developing: 'text-orange-400', exposed: 'text-red-400',
}
const EPL_BAND_LABEL: Record<string, string> = { strong: 'Strong', adequate: 'Adequate', developing: 'Developing', exposed: 'Exposed' }
const DOT: Record<string, string> = { strong: 'bg-emerald-500', partial: 'bg-amber-500', gap: 'bg-red-500' }
const ATTEST_OPTS = [
  { value: 'unknown', label: 'Not reviewed' },
  { value: 'in_place', label: 'In place' },
  { value: 'partial', label: 'Partial' },
  { value: 'gap', label: 'Gap' },
]
const inputCls = 'w-full bg-zinc-900 border border-zinc-800 rounded-lg px-2.5 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-600'

// loss-run snapshot fields (key, label, kind)
const WC_FIELDS: { k: string; label: string; type?: string }[] = [
  { k: 'period_label', label: 'Policy period', type: 'text' },
  { k: 'recordable_cases', label: 'Recordable cases' },
  { k: 'dart_cases', label: 'DART cases' },
  { k: 'lost_days', label: 'Lost days' },
  { k: 'restricted_days', label: 'Restricted days' },
  { k: 'ct_cases', label: 'Cumulative-trauma' },
  { k: 'acute_cases', label: 'Acute' },
  { k: 'post_termination_cases', label: 'Post-termination' },
  { k: 'lost_time_open', label: 'Lost-time open' },
  { k: 'lost_time_resolved', label: 'Lost-time resolved' },
  { k: 'avg_days_to_rtw', label: 'Avg days to RTW' },
  { k: 'current_emr', label: 'Experience mod', type: 'number-dec' },
  { k: 'carrier', label: 'Carrier', type: 'text' },
  { k: 'annual_premium', label: 'Annual premium' },
]

function rateTone(t: string) { return t === 'increase' ? 'text-red-400' : t === 'decrease' ? 'text-emerald-400' : 'text-zinc-400' }

function fmtDate(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

// Submission-status pill on the intake card — lets the broker confirm the EPL
// answers are the client's own and how current they are.
function IntakeStatusBadge({ intake }: { intake: ExternalClientDetail['intake'] }) {
  if (intake.status === 'submitted') {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-emerald-400">
        <CheckCircle2 className="h-3.5 w-3.5" /> Client submitted {fmtDate(intake.submitted_at)}
      </span>
    )
  }
  if (intake.status === 'pending') {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-amber-400">
        <Clock className="h-3.5 w-3.5" /> Awaiting client response
        {intake.pending_expires_at && <span className="text-zinc-600">· link expires {fmtDate(intake.pending_expires_at)}</span>}
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-zinc-500">
      <CircleDashed className="h-3.5 w-3.5" /> No intake link sent yet
    </span>
  )
}

export default function BrokerExternalClientDetail() {
  const { clientId } = useParams<{ clientId: string }>()
  const [data, setData] = useState<ExternalClientDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [editWc, setEditWc] = useState(false)
  const [wcForm, setWcForm] = useState<Record<string, string>>({})
  const [savingWc, setSavingWc] = useState(false)
  const [savingEpl, setSavingEpl] = useState<string | null>(null)
  const [parsing, setParsing] = useState(false)
  const [parseErr, setParseErr] = useState<string | null>(null)
  const [intakeUrl, setIntakeUrl] = useState<string | null>(null)
  const [intakeBusy, setIntakeBusy] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!clientId) return
    setLoading(true); setError(false)
    fetchExternalClientDetail(clientId).then(setData).catch(() => setError(true)).finally(() => setLoading(false))
  }, [clientId])

  function openWcEditor() {
    if (!data) return
    const w = data.wc
    setWcForm({
      period_label: w.period_label ?? '', recordable_cases: String(w.recordable_cases), dart_cases: String(w.dart_cases),
      lost_days: String(w.lost_days), restricted_days: '0', ct_cases: String(w.claim_breakdown.cumulative_trauma),
      acute_cases: String(w.claim_breakdown.acute), post_termination_cases: String(w.post_termination_cases),
      lost_time_open: String(w.rtw.open), lost_time_resolved: String(w.rtw.resolved),
      avg_days_to_rtw: w.rtw.avg_days_to_rtw != null ? String(w.rtw.avg_days_to_rtw) : '',
      current_emr: w.current_emr != null ? String(w.current_emr) : '', carrier: w.carrier ?? '',
      annual_premium: w.annual_premium != null ? String(w.annual_premium) : '',
    })
    setEditWc(true)
  }

  async function genIntakeLink() {
    if (!clientId) return
    setIntakeBusy(true); setCopied(false)
    try {
      const res = await createExternalIntakeLink(clientId)
      setIntakeUrl(`${window.location.origin}${res.path}`)
    } catch { /* noop */ } finally { setIntakeBusy(false) }
  }

  async function onLossRunFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''  // allow re-selecting the same file
    if (!file || !clientId) return
    setParsing(true); setParseErr(null)
    try {
      const res = await parseExternalLossRun(clientId, file)
      const s = (k: string) => { const v = res.fields[k]; return v == null ? '' : String(v) }
      setWcForm({
        period_label: s('period_label'), recordable_cases: s('recordable_cases'), dart_cases: s('dart_cases'),
        lost_days: s('lost_days'), restricted_days: s('restricted_days'), ct_cases: s('ct_cases'),
        acute_cases: s('acute_cases'), post_termination_cases: s('post_termination_cases'),
        lost_time_open: s('lost_time_open'), lost_time_resolved: s('lost_time_resolved'),
        avg_days_to_rtw: s('avg_days_to_rtw'), current_emr: s('current_emr'),
        carrier: s('carrier'), annual_premium: s('annual_premium'),
      })
      setEditWc(true)
      if (!res.available) setParseErr('Could not read this PDF confidently — review every field before saving.')
    } catch {
      setParseErr('Parse failed. Enter the loss run manually.')
    } finally {
      setParsing(false)
    }
  }

  async function submitWc(e: FormEvent) {
    e.preventDefault()
    if (!clientId) return
    setSavingWc(true)
    const num = (k: string) => { const v = parseFloat(wcForm[k]); return Number.isFinite(v) ? v : 0 }
    const numOrNull = (k: string) => { const v = parseFloat(wcForm[k]); return Number.isFinite(v) ? v : null }
    try {
      const updated = await saveExternalWc(clientId, {
        period_label: wcForm.period_label || null,
        recordable_cases: num('recordable_cases'), dart_cases: num('dart_cases'), lost_days: num('lost_days'),
        restricted_days: num('restricted_days'), ct_cases: num('ct_cases'), acute_cases: num('acute_cases'),
        post_termination_cases: num('post_termination_cases'), lost_time_open: num('lost_time_open'),
        lost_time_resolved: num('lost_time_resolved'), avg_days_to_rtw: numOrNull('avg_days_to_rtw'),
        current_emr: numOrNull('current_emr'), carrier: wcForm.carrier || null, annual_premium: numOrNull('annual_premium'),
      })
      setData(updated); setEditWc(false)
    } catch { /* keep */ } finally { setSavingWc(false) }
  }

  async function setEpl(key: string, status: EplAttestationStatus) {
    if (!clientId) return
    setSavingEpl(key)
    try { setData(await saveExternalEplAttestation(clientId, key, { status })) }
    catch { /* keep */ } finally { setSavingEpl(null) }
  }

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>
  if (error || !data) return (
    <div className="flex flex-col items-center justify-center h-64 text-zinc-500">
      <AlertCircle className="h-8 w-8 mb-2" /><p className="text-sm">Unable to load this client.</p>
    </div>
  )

  const { client, wc, epl, risk_index: risk, intake } = data
  const benchRatio = wc.trir && wc.benchmark && wc.benchmark.trir > 0 ? wc.trir / wc.benchmark.trir : null

  return (
    <div className="space-y-6">
      <Link to="/broker/external" className="inline-flex items-center gap-1.5 text-sm text-zinc-400 hover:text-zinc-200 transition-colors">
        <ArrowLeft className="h-4 w-4" /> Back to External Book
      </Link>

      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight">{client.name}</h1>
          <p className="text-sm text-zinc-500 mt-1">
            {[client.industry, client.primary_state, client.headcount ? `${client.headcount} employees` : null].filter(Boolean).join(' · ') || 'Off-platform client'}
            <span className="ml-2 text-[10px] uppercase tracking-widest text-emerald-500 font-bold">Off-platform</span>
          </p>
          {client.note && <p className="text-xs text-zinc-600 mt-1">{client.note}</p>}
        </div>
        {risk?.index != null && (
          <div className="text-right shrink-0">
            <div className={`text-4xl font-light font-mono ${risk.band ? RISK_BAND_TONE[risk.band] ?? 'text-zinc-300' : 'text-zinc-300'}`}>{risk.index}</div>
            <div className="text-[9px] uppercase tracking-widest font-bold text-zinc-600">Risk index{risk.band ? ` · ${risk.band}` : ''}</div>
          </div>
        )}
      </div>

      {/* Client-intake link */}
      <Card className="p-4">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <LinkIcon className="h-4 w-4 text-zinc-500" />
            <span className="text-sm text-zinc-300">Client-intake link</span>
            <HelpHint text="Generate a shareable link the prospect opens to self-complete the EPL questionnaire — no account needed. Their answers feed this client's EPL score automatically." />
            <span className="ml-1 pl-3 border-l border-zinc-800"><IntakeStatusBadge intake={intake} /></span>
          </div>
          {!intakeUrl ? (
            <button onClick={genIntakeLink} disabled={intakeBusy} className="inline-flex items-center gap-1 text-xs text-zinc-300 hover:text-zinc-100 px-2.5 py-1.5 rounded-lg border border-zinc-700 hover:border-zinc-500 disabled:opacity-50">
              {intakeBusy ? 'Generating…' : 'Generate intake link'}
            </button>
          ) : (
            <div className="flex items-center gap-2 flex-1 min-w-[260px] justify-end">
              <input readOnly value={intakeUrl} className="flex-1 max-w-md bg-zinc-900 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-xs text-zinc-300 font-mono" onFocus={(e) => e.target.select()} />
              <button onClick={() => { navigator.clipboard?.writeText(intakeUrl); setCopied(true) }} className="text-xs text-zinc-300 hover:text-emerald-400 px-2 py-1.5 rounded-lg border border-zinc-700">{copied ? 'Copied' : 'Copy'}</button>
            </div>
          )}
        </div>
      </Card>

      {/* Workers' Comp */}
      <Card className="p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2"><Gauge className="h-4 w-4 text-zinc-500" /><h3 className="text-sm font-medium text-zinc-200 tracking-wide">Workers' Comp</h3>
            <HelpHint text="Keyed from the client's carrier loss run. We compute TRIR/DART vs their industry, the claim mix (cumulative-trauma / post-term / open lost-time), and overlay the state's WC rate trend — so you can show what's driving their premium and what to fix." />
          </div>
          <div className="flex items-center gap-2">
            <label className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded-lg border transition-colors ${parsing ? 'text-zinc-500 border-zinc-800 cursor-wait' : 'text-zinc-300 hover:text-zinc-100 border-zinc-700 hover:border-zinc-500 cursor-pointer'}`}>
              <Upload className="h-3.5 w-3.5" /> {parsing ? 'Parsing…' : 'Parse loss-run PDF'}
              <input type="file" accept="application/pdf" className="hidden" disabled={parsing} onChange={onLossRunFile} />
            </label>
            <button onClick={() => (editWc ? setEditWc(false) : openWcEditor())} className="text-xs text-zinc-300 hover:text-zinc-100 px-2 py-1 rounded-lg border border-zinc-700 hover:border-zinc-500 transition-colors">
              {editWc ? 'Cancel' : wc.has_data ? 'Edit loss run' : 'Enter loss run'}
            </button>
          </div>
        </div>
        {parseErr && <p className="text-[11px] text-amber-400 mb-3">{parseErr}</p>}

        {!editWc && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-px bg-white/10 border border-white/10 rounded-2xl overflow-hidden mb-4">
              <Cell label="TRIR" value={wc.trir ?? '—'} sub={benchRatio ? `${benchRatio.toFixed(1)}× bench` : 'no benchmark'} tone={WC_TONE[wc.severity_band]} />
              <Cell label="DART" value={wc.dart_rate ?? '—'} />
              <Cell label="Recordables" value={wc.recordable_cases} sub={`${wc.dart_cases} DART`} />
              <Cell label="Exp. Mod" value={wc.current_emr != null ? wc.current_emr.toFixed(2) : '—'}
                tone={wc.current_emr != null ? (wc.current_emr > 1 ? 'text-red-400' : wc.current_emr < 1 ? 'text-emerald-400' : 'text-zinc-300') : 'text-zinc-600'} />
              <Cell label="State rate" value={wc.state_rate ? `${wc.state_rate.loss_cost_change_pct > 0 ? '+' : ''}${wc.state_rate.loss_cost_change_pct}%` : '—'}
                tone={wc.state_rate ? rateTone(wc.state_rate.trend) : 'text-zinc-600'} sub={client.primary_state ?? undefined} />
            </div>
            {wc.has_data ? (
              <div className="grid grid-cols-3 gap-3 text-center text-[12px]">
                <div className="rounded-lg bg-zinc-900/60 py-2"><div className="font-mono text-zinc-200">{wc.claim_breakdown.cumulative_trauma}/{wc.claim_breakdown.acute}</div><div className="text-[10px] text-zinc-500 mt-0.5">CT / acute</div></div>
                <div className="rounded-lg bg-zinc-900/60 py-2"><div className={`font-mono ${wc.post_termination_cases > 0 ? 'text-red-400' : 'text-zinc-300'}`}>{wc.post_termination_cases}</div><div className="text-[10px] text-zinc-500 mt-0.5">Post-term</div></div>
                <div className="rounded-lg bg-zinc-900/60 py-2"><div className="font-mono text-zinc-200">{wc.rtw.open} open · {wc.rtw.avg_days_to_rtw ?? '—'}d</div><div className="text-[10px] text-zinc-500 mt-0.5">RTW</div></div>
              </div>
            ) : <p className="text-sm text-zinc-500">No loss run on file. Enter the carrier loss-run summary to compute WC metrics.</p>}
          </>
        )}

        {editWc && (
          <form onSubmit={submitWc}>
            <p className="text-[11px] text-zinc-600 mb-3">Key in the figures from the client's carrier loss run + current experience mod.</p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {WC_FIELDS.map((f) => (
                <div key={f.k}>
                  <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1">{f.label}</label>
                  <input
                    type={f.type === 'text' ? 'text' : 'number'} step={f.type === 'number-dec' ? '0.001' : '1'}
                    value={wcForm[f.k] ?? ''} onChange={(e) => setWcForm({ ...wcForm, [f.k]: e.target.value })} className={inputCls} />
                </div>
              ))}
            </div>
            <button type="submit" disabled={savingWc} className="mt-3 bg-zinc-100 text-zinc-900 text-sm font-medium rounded-lg px-4 py-1.5 hover:bg-white disabled:opacity-50 transition-colors">
              {savingWc ? 'Saving…' : 'Save loss run'}
            </button>
          </form>
        )}
      </Card>

      {/* EPL */}
      <Card className="p-5">
        <div className="flex items-center gap-3 mb-4">
          <Shield className="h-4 w-4 text-zinc-500" />
          <h3 className="text-sm font-medium text-zinc-200 tracking-wide">EPL Readiness</h3>
          <HelpHint text="Employment-practices-liability readiness, scored 0–100. Off-platform clients are fully broker-assessed: set each factor (policy, training, wage-hour, pay transparency, BIPA, etc.) from the underwriting questionnaire and the score updates live." />
          <span className={`text-2xl font-light font-mono ml-auto ${EPL_TONE[epl.band]}`}>{epl.score}</span>
          <span className={`text-[10px] uppercase tracking-widest font-bold ${EPL_TONE[epl.band]}`}>{EPL_BAND_LABEL[epl.band]}</span>
        </div>
        <p className="text-[11px] text-zinc-600 mb-4">Off-platform clients are fully broker-assessed — set each factor as you confirm it from the underwriting questionnaire.</p>
        <div className="space-y-1">
          {epl.factors.map((f: ExternalEplFactor) => (
            <div key={f.key} className="flex items-center gap-3 py-1.5 border-b border-zinc-800/30 last:border-0">
              <span className={`h-2 w-2 rounded-full flex-shrink-0 ${DOT[f.status]}`} />
              <span className="text-sm text-zinc-200 flex-1 min-w-0">{f.label}<span className="text-[10px] text-zinc-600 ml-2">{f.weight} pts</span></span>
              <div className="flex items-center gap-2">
                {savingEpl === f.key && <Loader2 className="h-3.5 w-3.5 text-zinc-500 animate-spin" />}
                <select value={f.attest_status} disabled={savingEpl === f.key}
                  onChange={(e) => setEpl(f.key, e.target.value as EplAttestationStatus)}
                  className="bg-zinc-900 border border-zinc-700 rounded-lg px-2 py-1 text-xs text-zinc-200 focus:outline-none focus:border-zinc-500">
                  {ATTEST_OPTS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
            </div>
          ))}
        </div>
      </Card>

      <SubmissionPanel
        onDownload={() => downloadExternalSubmission(clientId!)}
        onAnalyze={() => fetchExternalCoverageGap(clientId!)}
      />
    </div>
  )
}

function Cell({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: string; tone?: string }) {
  return (
    <div className="bg-zinc-900 px-4 py-3">
      <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">{label}</div>
      <div className={`text-xl font-light font-mono mt-1 ${tone ?? 'text-zinc-200'}`}>{value}</div>
      {sub && <div className="text-[10px] text-zinc-600 mt-0.5">{sub}</div>}
    </div>
  )
}
