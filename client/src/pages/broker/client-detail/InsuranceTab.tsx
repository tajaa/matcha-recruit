import { useEffect, useState } from 'react'
import { Loader2, TrendingUp, FileWarning, Send, Lock } from 'lucide-react'
import { Card, useToast } from '../../../components/ui'
import { QuotingDeskPanel } from '../../../components/broker/QuotingDeskPanel'
import {
  brokerPrefill, brokerListQuotes, brokerCreateQuote, brokerPresentQuote, brokerBindQuote,
  fetchRiskToRate, syncRiskToRate, fetchLossRuns, fileFnol,
  type RiskToRate, type LossRun,
} from '../../../api/broker/brokerInsurance'

function errMsg(e: unknown): string { return e instanceof Error ? e.message : 'Something went wrong' }
function dollars(cents: number | null | undefined): string {
  return cents == null ? '—' : `$${(cents / 100).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
}
const bps = (v: number) => `${(v / 100).toFixed(2)}%`

export function InsuranceTab({ companyId }: { companyId: string }) {
  return (
    <div className="space-y-8">
      <QuotingDeskPanel
        loadPrefill={(line) => brokerPrefill(companyId, line)}
        loadQuotes={() => brokerListQuotes(companyId)}
        createQuote={(input) => brokerCreateQuote(companyId, input)}
        presentQuote={(id, body) => brokerPresentQuote(companyId, id, body)}
        bindQuote={(id) => brokerBindQuote(companyId, id)}
      />
      <RiskToRatePanel companyId={companyId} />
      <ClaimsBridgePanel companyId={companyId} />
    </div>
  )
}

// --- Risk-to-Rate --------------------------------------------------------------

function RiskToRatePanel({ companyId }: { companyId: string }) {
  const { toast } = useToast()
  const [data, setData] = useState<RiskToRate | null>(null)
  const [loading, setLoading] = useState(true)
  const [locked, setLocked] = useState(false)
  const [syncing, setSyncing] = useState(false)

  useEffect(() => {
    fetchRiskToRate(companyId)
      .then(setData)
      .catch(() => setLocked(true))
      .finally(() => setLoading(false))
  }, [companyId])

  async function onSync() {
    setSyncing(true)
    try {
      const r = await syncRiskToRate(companyId)
      toast(r.mock_mode ? 'Evidence synced (sandbox)' : 'Evidence pushed to carrier', 'success')
    } catch (e) { toast(errMsg(e), 'error') } finally { setSyncing(false) }
  }

  if (loading) return <SectionSkeleton />
  if (locked) return <LockedSection title="Risk-to-Rate" note="Premium-credit feed needs a live carrier appointment." />

  return (
    <div>
      <SectionHeader icon={TrendingUp} title="Risk-to-Rate"
        subtitle="Verified controls that earn carrier credits. Close the gaps to unlock more." />
      {data && (
        <Card className="p-4 space-y-4">
          <div className="flex flex-wrap gap-4">
            <Stat label="Realized credit" value={bps(data.realized_credit_bps)} tone="text-emerald-400" />
            <Stat label="Available credit" value={bps(data.available_credit_bps)} tone="text-sky-400" />
            {data.readiness_score != null && <Stat label="Readiness" value={`${data.readiness_score}%`} tone="text-zinc-200" />}
          </div>
          <div className="space-y-2">
            {data.levers.map((l) => (
              <div key={l.key} className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2">
                <div>
                  <div className="text-sm text-zinc-200">{l.label}</div>
                  <div className="text-[11px] text-zinc-500">
                    {l.status === 'realized' ? 'In place' : l.basis === 'gap' ? 'Gap — action available' : 'Not tracked yet'}
                  </div>
                </div>
                <div className="text-right">
                  <div className={`text-sm font-mono ${l.status === 'realized' ? 'text-emerald-400' : 'text-sky-400'}`}>{bps(l.est_credit_bps)}</div>
                  <div className="text-[10px] uppercase tracking-wider text-zinc-600">{l.status}</div>
                </div>
              </div>
            ))}
          </div>
          <div className="flex justify-end">
            <button onClick={onSync} disabled={syncing}
              className="inline-flex items-center gap-1.5 text-sm text-zinc-200 px-3 py-1.5 rounded-lg border border-zinc-700 hover:border-zinc-500 disabled:opacity-50">
              {syncing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />} Sync evidence to carrier
            </button>
          </div>
          <p className="text-[10px] text-zinc-600">Directional estimates until carrier credits are live.</p>
        </Card>
      )}
    </div>
  )
}

// --- Claims Bridge -------------------------------------------------------------

function ClaimsBridgePanel({ companyId }: { companyId: string }) {
  const { toast } = useToast()
  const [lossRuns, setLossRuns] = useState<LossRun[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [locked, setLocked] = useState(false)
  const [incidentId, setIncidentId] = useState('')
  const [filing, setFiling] = useState(false)

  useEffect(() => {
    fetchLossRuns(companyId)
      .then((r) => setLossRuns(r.loss_runs))
      .catch(() => setLocked(true))
      .finally(() => setLoading(false))
  }, [companyId])

  async function onFnol() {
    if (!incidentId.trim()) return
    setFiling(true)
    try {
      const claim = await fileFnol(companyId, { incident_id: incidentId.trim() })
      toast(`FNOL filed — ${claim.claim_ref}`, 'success')
      setIncidentId('')
    } catch (e) { toast(errMsg(e), 'error') } finally { setFiling(false) }
  }

  if (loading) return <SectionSkeleton />
  if (locked) return <LockedSection title="Claims Bridge" note="Loss-run pull + FNOL need a live carrier appointment." />

  return (
    <div>
      <SectionHeader icon={FileWarning} title="Claims Bridge"
        subtitle="Loss runs pulled from the carrier, and file a First Notice of Loss from a logged incident." />
      <Card className="p-4 space-y-4">
        <div>
          <div className="text-xs text-zinc-500 mb-1.5">Loss runs</div>
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-zinc-500 border-b border-zinc-800">
              <th className="py-2">Policy year</th><th>Claims</th><th>Incurred</th><th>Paid</th><th>Open</th>
            </tr></thead>
            <tbody>
              {(lossRuns ?? []).map((r) => (
                <tr key={r.policy_year} className="border-b border-zinc-900">
                  <td className="py-2 text-zinc-200">{r.policy_year}</td>
                  <td className="text-zinc-300">{r.claims}</td>
                  <td className="text-zinc-300">{dollars(r.incurred_cents)}</td>
                  <td className="text-zinc-300">{dollars(r.paid_cents)}</td>
                  <td className="text-zinc-300">{r.open}</td>
                </tr>
              ))}
              {(lossRuns ?? []).length === 0 && <tr><td colSpan={5} className="py-4 text-zinc-600">No loss runs.</td></tr>}
            </tbody>
          </table>
        </div>
        <div>
          <div className="text-xs text-zinc-500 mb-1.5">File FNOL from an incident</div>
          <div className="flex gap-2">
            <input value={incidentId} onChange={(e) => setIncidentId(e.target.value)}
              placeholder="IR incident ID"
              className="flex-1 bg-zinc-900 border border-zinc-800 rounded-lg px-2.5 py-1.5 text-sm text-zinc-100 focus:border-zinc-600 outline-none" />
            <button onClick={onFnol} disabled={filing || !incidentId.trim()}
              className="inline-flex items-center gap-1.5 text-sm text-zinc-900 bg-zinc-100 hover:bg-white rounded-lg px-3 py-1.5 font-medium disabled:opacity-50">
              {filing ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileWarning className="h-4 w-4" />} File FNOL
            </button>
          </div>
        </div>
      </Card>
    </div>
  )
}

// --- small shared bits ---------------------------------------------------------

function SectionHeader({ icon: Icon, title, subtitle }: { icon: typeof TrendingUp; title: string; subtitle: string }) {
  return (
    <div className="mb-3">
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 text-zinc-400" />
        <h3 className="text-sm font-medium text-zinc-200">{title}</h3>
      </div>
      <p className="text-[11px] text-zinc-500 mt-0.5">{subtitle}</p>
    </div>
  )
}
function Stat({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-900 px-3 py-1.5 min-w-[96px]">
      <div className="text-[9px] uppercase tracking-wider text-zinc-500">{label}</div>
      <div className={`text-base font-mono mt-0.5 ${tone}`}>{value}</div>
    </div>
  )
}
function SectionSkeleton() {
  return <div className="flex items-center gap-2 text-sm text-zinc-500 py-4"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</div>
}
function LockedSection({ title, note }: { title: string; note: string }) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 text-zinc-400"><Lock className="h-4 w-4" /><span className="text-sm font-medium">{title}</span></div>
      <p className="text-[11px] text-zinc-500 mt-1">{note}</p>
    </Card>
  )
}
