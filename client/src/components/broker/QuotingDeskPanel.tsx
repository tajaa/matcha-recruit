import { useEffect, useState } from 'react'
import { Sparkles, Loader2, CheckCircle2, Send } from 'lucide-react'
import { Card, useToast } from '../ui'
import type { QuotableLine, QuotePayload } from '../../api/risk/insurance'
import type { BrokerQuote, BrokerPrefill, BrokerQuoteInput } from '../../api/broker/brokerInsurance'

const LINES: { key: QuotableLine; label: string }[] = [
  { key: 'bop', label: "Business Owner's Policy" },
  { key: 'gl', label: 'General Liability' },
  { key: 'wc', label: "Workers' Comp" },
  { key: 'professional', label: 'Professional Liability' },
]

const STATUS_TONE: Record<string, string> = {
  draft: 'text-zinc-500', quoted: 'text-sky-400', presented: 'text-amber-400',
  bound: 'text-emerald-400', expired: 'text-zinc-500', error: 'text-rose-400',
}

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : 'Something went wrong'
}
function dollars(cents: number | null | undefined): string {
  return cents == null ? '—' : `$${(cents / 100).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
}

/**
 * Broker quoting desk — request a Coterie quote for a client from data on file,
 * then either bind directly (when the client-link permits) or present it for the
 * client to accept. Reused for on-platform and off-platform clients by swapping
 * the injected API fns; `presentQuote` omitted (off-platform has no accept surface).
 */
export function QuotingDeskPanel({
  loadPrefill, loadQuotes, createQuote, presentQuote, bindQuote,
}: {
  loadPrefill: (line: QuotableLine) => Promise<BrokerPrefill>
  loadQuotes: () => Promise<{ quotes: BrokerQuote[] }>
  createQuote: (input: BrokerQuoteInput) => Promise<BrokerQuote>
  presentQuote?: (quoteId: string, body: { commission_bps?: number | null; broker_note?: string | null }) => Promise<BrokerQuote>
  bindQuote?: (quoteId: string) => Promise<BrokerQuote>
}) {
  const { toast } = useToast()
  const [line, setLine] = useState<QuotableLine>('bop')
  const [payload, setPayload] = useState<QuotePayload | null>(null)
  const [mock, setMock] = useState(false)
  const [canBind, setCanBind] = useState(false)
  const [commissionBps, setCommissionBps] = useState<number | null>(null)
  const [quotes, setQuotes] = useState<BrokerQuote[]>([])
  const [loading, setLoading] = useState(true)
  const [quoting, setQuoting] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([loadPrefill('bop'), loadQuotes()])
      .then(([pf, q]) => { setPayload(pf.payload); setMock(pf.mock_mode); setCanBind(pf.can_bind); setQuotes(q.quotes) })
      .catch((e) => toast(errMsg(e), 'error'))
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function reloadPrefill(next: QuotableLine) {
    setLine(next)
    try { const pf = await loadPrefill(next); setPayload(pf.payload); setMock(pf.mock_mode); setCanBind(pf.can_bind) }
    catch (e) { toast(errMsg(e), 'error') }
  }

  async function onGetQuote() {
    if (!payload) return
    setQuoting(true)
    try {
      const q = await createQuote({
        line,
        legal_name: payload.business.legal_name, naics: payload.business.naics,
        state: payload.business.state, zip_code: payload.business.zip,
        headcount: payload.exposure.headcount, annual_payroll: payload.exposure.annual_payroll,
        annual_revenue: payload.exposure.annual_revenue,
        commission_bps: commissionBps,
      })
      setQuotes((prev) => [q, ...prev])
      if (q.status === 'error') toast(q.error_message || 'Carrier could not quote', 'error')
    } catch (e) { toast(errMsg(e), 'error') } finally { setQuoting(false) }
  }

  async function onPresent(id: string) {
    if (!presentQuote) return
    setBusyId(id)
    try {
      const updated = await presentQuote(id, { commission_bps: commissionBps })
      setQuotes((prev) => prev.map((q) => (q.id === id ? updated : q)))
      toast('Quote presented to the client for acceptance', 'success')
    } catch (e) { toast(errMsg(e), 'error') } finally { setBusyId(null) }
  }

  async function onBind(id: string) {
    if (!bindQuote) return
    setBusyId(id)
    try {
      const bound = await bindQuote(id)
      setQuotes((prev) => prev.map((q) => (q.id === id ? bound : q)))
      toast('Policy bound', 'success')
    } catch (e) { toast(errMsg(e), 'error') } finally { setBusyId(null) }
  }

  function setBiz<K extends keyof QuotePayload['business']>(k: K, v: QuotePayload['business'][K]) {
    setPayload((p) => (p ? { ...p, business: { ...p.business, [k]: v } } : p))
  }
  function setExp<K extends keyof QuotePayload['exposure']>(k: K, v: QuotePayload['exposure'][K]) {
    setPayload((p) => (p ? { ...p, exposure: { ...p.exposure, [k]: v } } : p))
  }

  if (loading) return <div className="flex items-center justify-center h-40"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>

  return (
    <div className="space-y-5">
      <Card className="p-4 space-y-4">
        <div>
          <h3 className="text-sm font-medium text-zinc-200">Get a carrier quote</h3>
          <p className="text-[11px] text-zinc-500 mt-0.5">
            Built from this client's data on file. Review, then bind{presentQuote ? ' or present for the client to accept' : ''}.
          </p>
          {mock && <p className="text-[11px] text-amber-400/80 mt-1">Sandbox mode — representative pricing, not live carrier numbers.</p>}
        </div>

        <div>
          <div className="text-xs text-zinc-500 mb-1.5">Coverage line</div>
          <div className="flex flex-wrap gap-2">
            {LINES.map((l) => (
              <button key={l.key} onClick={() => reloadPrefill(l.key)}
                className={`text-sm rounded-lg px-3 py-1.5 border ${line === l.key ? 'bg-zinc-100 text-zinc-900 border-zinc-100' : 'border-zinc-800 text-zinc-300 hover:border-zinc-600'}`}>
                {l.label}
              </button>
            ))}
          </div>
        </div>

        {payload && (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <Field label="Legal name" value={payload.business.legal_name ?? ''} onChange={(v) => setBiz('legal_name', v || null)} />
            <Field label="NAICS" value={payload.business.naics ?? ''} onChange={(v) => setBiz('naics', v || null)} />
            <Field label="State" value={payload.business.state ?? ''} onChange={(v) => setBiz('state', v || null)} />
            <Field label="ZIP" value={payload.business.zip ?? ''} onChange={(v) => setBiz('zip', v || null)} />
            <NumField label="Headcount" value={payload.exposure.headcount} onChange={(v) => setExp('headcount', v)} />
            <NumField label="Annual payroll" value={payload.exposure.annual_payroll} onChange={(v) => setExp('annual_payroll', v)} />
            {(line === 'gl' || line === 'bop' || line === 'professional') && (
              <NumField label="Annual revenue" value={payload.exposure.annual_revenue} onChange={(v) => setExp('annual_revenue', v)} />
            )}
            <NumField label="Commission (bps)" value={commissionBps} onChange={setCommissionBps} />
          </div>
        )}

        <div className="flex justify-end">
          <button onClick={onGetQuote} disabled={quoting || !payload}
            className="inline-flex items-center gap-1.5 text-sm text-zinc-900 bg-zinc-100 hover:bg-white rounded-lg px-3 py-2 font-medium disabled:opacity-50">
            {quoting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} Get quote
          </button>
        </div>
      </Card>

      <Card className="p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-xs text-zinc-500 border-b border-zinc-800">
            <th className="py-2.5 px-4">Line</th><th>Premium</th><th>Status</th><th>Expires</th><th></th>
          </tr></thead>
          <tbody>
            {quotes.length === 0 && <tr><td colSpan={5} className="px-4 py-6 text-zinc-600">No quotes yet — request one above.</td></tr>}
            {quotes.map((q) => (
              <tr key={q.id} className="border-b border-zinc-900">
                <td className="px-4 py-2.5 text-zinc-200">{LINES.find((l) => l.key === q.line)?.label ?? q.line}</td>
                <td className="text-zinc-200">{dollars(q.premium_cents)}<span className="text-xs text-zinc-500">/yr</span></td>
                <td className={STATUS_TONE[q.status] ?? 'text-zinc-400'}>{q.status}</td>
                <td className="text-zinc-400">{q.expires_at || '—'}</td>
                <td className="pr-4 text-right whitespace-nowrap">
                  {(q.status === 'quoted' || q.status === 'presented') && (
                    <span className="inline-flex items-center gap-3">
                      {presentQuote && q.status === 'quoted' && (
                        <button onClick={() => onPresent(q.id)} disabled={busyId === q.id}
                          className="inline-flex items-center gap-1 text-xs text-sky-300 hover:text-sky-200 disabled:opacity-50">
                          {busyId === q.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />} Present
                        </button>
                      )}
                      {bindQuote && canBind && (
                        <button onClick={() => onBind(q.id)} disabled={busyId === q.id}
                          className="inline-flex items-center gap-1 text-xs text-emerald-300 hover:text-emerald-200 disabled:opacity-50">
                          {busyId === q.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />} Bind
                        </button>
                      )}
                    </span>
                  )}
                  {q.status === 'bound' && <span className="text-xs text-emerald-400">bound</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      {presentQuote && !canBind && (
        <p className="text-[11px] text-zinc-600">
          Direct bind is off for this client — present a quote and the client accepts &amp; binds it on their own Insurance page.
        </p>
      )}
    </div>
  )
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="block">
      <span className="text-xs text-zinc-500">{label}</span>
      <input value={value} onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full bg-zinc-900 border border-zinc-800 rounded-lg px-2.5 py-1.5 text-sm text-zinc-100 focus:border-zinc-600 outline-none" />
    </label>
  )
}

function NumField({ label, value, onChange }: { label: string; value: number | null; onChange: (v: number | null) => void }) {
  return (
    <label className="block">
      <span className="text-xs text-zinc-500">{label}</span>
      <input type="number" value={value ?? ''} onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
        className="mt-1 w-full bg-zinc-900 border border-zinc-800 rounded-lg px-2.5 py-1.5 text-sm text-zinc-100 focus:border-zinc-600 outline-none" />
    </label>
  )
}
