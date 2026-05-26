import { useEffect, useMemo, useState } from 'react'
import { Loader2, Download } from 'lucide-react'
import { Button, Input, Toggle } from '../../components/ui'
import { api } from '../../api/client'

type Tier = 'mid' | 'max'

type DealQuote = {
  tier: Tier
  tier_label: string
  pepm: number
  onboarding: number
  subscription_yr: number
  subtotal: number
  broker_disc: number
  partner_disc: number
  discount_pct: number
  your_price_yr: number
  you_save_yr: number
}

type QuoteResponse = { mid: DealQuote; max: DealQuote }

type DealInputs = {
  company_name: string
  headcount: number
  tier: Tier
  broker: boolean
  broker_name: string | null
  partner: boolean
  hr_partner_addon: boolean
  proposal_date: string | null
}

const usd = (n: number) => `$${n.toLocaleString('en-US')}`

const TIER_PEPM_NOTE: Record<Tier, string> = {
  mid: '$10 PEPM · guided onboarding',
  max: '$13 PEPM · white-glove implementation',
}

function QuoteCard({ q, recommended }: { q: DealQuote; recommended: boolean }) {
  return (
    <div
      className={`rounded-xl border p-5 ${
        recommended
          ? 'border-violet-500/60 bg-violet-500/5'
          : 'border-zinc-800 bg-zinc-900/40'
      }`}
    >
      <div className="flex items-baseline justify-between">
        <h3 className="text-lg font-semibold text-zinc-100">{q.tier_label}</h3>
        {recommended && (
          <span className="rounded-full border border-violet-500/40 bg-violet-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-violet-300">
            Recommended
          </span>
        )}
      </div>
      <p className="mt-0.5 text-xs text-zinc-500">{TIER_PEPM_NOTE[q.tier]}</p>

      <div className="mt-4 space-y-1.5 text-sm">
        <Row label="Subscription / yr" value={usd(q.subscription_yr)} />
        <Row label="Onboarding" value={`+${usd(q.onboarding)}`} />
        {(q.broker_disc > 0 || q.partner_disc > 0) && (
          <>
            <Row label="Subtotal" value={usd(q.subtotal)} bold border />
            {q.broker_disc > 0 && (
              <Row label="−10% broker" value={`−${usd(q.broker_disc)}`} muted />
            )}
            {q.partner_disc > 0 && (
              <Row label="−5% partner" value={`−${usd(q.partner_disc)}`} muted />
            )}
          </>
        )}
        <div className="mt-2 flex items-center justify-between border-t border-zinc-700 pt-2.5">
          <span className="font-semibold text-zinc-200">Your price</span>
          <span className="text-xl font-bold text-zinc-50">
            {usd(q.your_price_yr)}
            <span className="ml-1 text-xs font-medium text-zinc-500">/yr</span>
          </span>
        </div>
        {q.you_save_yr > 0 && (
          <div className="mt-2 rounded-md bg-emerald-500/10 px-2.5 py-1.5 text-xs font-semibold text-emerald-300">
            You save {usd(q.you_save_yr)} / yr
          </div>
        )}
      </div>
    </div>
  )
}

function Row({
  label,
  value,
  bold,
  muted,
  border,
}: {
  label: string
  value: string
  bold?: boolean
  muted?: boolean
  border?: boolean
}) {
  return (
    <div
      className={`flex items-center justify-between ${border ? 'border-t border-zinc-800 pt-1.5' : ''} ${
        muted ? 'text-zinc-500' : 'text-zinc-300'
      } ${bold ? 'font-semibold text-zinc-200' : ''}`}
    >
      <span>{label}</span>
      <span>{value}</span>
    </div>
  )
}

export default function DealFlow() {
  const today = useMemo(() => new Date().toISOString().slice(0, 10), [])
  const [companyName, setCompanyName] = useState('')
  const [headcount, setHeadcount] = useState('500')
  const [tier, setTier] = useState<Tier>('max')
  const [broker, setBroker] = useState(true)
  const [brokerName, setBrokerName] = useState('Alliant')
  const [partner, setPartner] = useState(true)
  const [hrPartner, setHrPartner] = useState(false)
  const [proposalDate, setProposalDate] = useState(today)

  const [quotes, setQuotes] = useState<QuoteResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [downloading, setDownloading] = useState(false)

  const headcountNum = parseInt(headcount, 10)
  const validHeadcount = Number.isFinite(headcountNum) && headcountNum > 0

  const inputs: DealInputs = useMemo(
    () => ({
      company_name: companyName.trim() || 'Prospect',
      headcount: validHeadcount ? headcountNum : 0,
      tier,
      broker,
      broker_name: broker ? brokerName.trim() || 'Broker' : null,
      partner,
      hr_partner_addon: hrPartner,
      proposal_date: proposalDate || null,
    }),
    [companyName, headcountNum, validHeadcount, tier, broker, brokerName, partner, hrPartner, proposalDate],
  )

  // Live quote — server is the single source of pricing truth (debounced).
  useEffect(() => {
    if (!validHeadcount) {
      setQuotes(null)
      return
    }
    const t = setTimeout(() => {
      api
        .post<QuoteResponse>('/admin/deal-flow/quote', inputs)
        .then((r) => {
          setQuotes(r)
          setError(null)
        })
        .catch((e) => setError(e instanceof Error ? e.message : 'Quote failed'))
    }, 300)
    return () => clearTimeout(t)
  }, [inputs, validHeadcount])

  async function downloadProposal() {
    if (!validHeadcount) return
    setDownloading(true)
    setError(null)
    try {
      const safe = (companyName.trim() || 'Matcha').replace(/[^A-Za-z0-9]+/g, '_').replace(/^_|_$/g, '')
      await api.downloadPost('/admin/deal-flow/proposal', inputs, `${safe}_Matcha_Proposal.pdf`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Proposal download failed')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">Deal Flow</h1>
          <p className="mt-2 text-sm text-zinc-500">
            Configure a deal off the standard Mid / Max structure and generate a proposal PDF. Nothing is saved.
          </p>
        </div>
        <Button onClick={downloadProposal} disabled={!validHeadcount || downloading}>
          {downloading ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Download className="mr-2 h-4 w-4" />
          )}
          Download Proposal PDF
        </Button>
      </div>

      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[360px_1fr]">
        {/* Form */}
        <div className="space-y-5 rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
          <Input
            label="Company name"
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
            placeholder="LA Non-Profit"
          />
          <Input
            label="Headcount"
            type="number"
            min={1}
            value={headcount}
            onChange={(e) => setHeadcount(e.target.value)}
          />

          <div>
            <label className="mb-1.5 block text-sm font-medium text-zinc-300">Recommended tier</label>
            <div className="flex gap-2">
              {(['mid', 'max'] as Tier[]).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTier(t)}
                  className={`flex-1 rounded-lg border px-3 py-2 text-sm font-medium capitalize transition-colors ${
                    tier === t
                      ? 'border-violet-500/60 bg-violet-500/10 text-violet-200'
                      : 'border-zinc-700 text-zinc-400 hover:border-zinc-600'
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          <ToggleRow label="Broker discount (−10%)" checked={broker} onChange={setBroker} />
          {broker && (
            <Input
              label="Broker name"
              value={brokerName}
              onChange={(e) => setBrokerName(e.target.value)}
              placeholder="Alliant"
            />
          )}
          <ToggleRow label="Partner program (−5%)" checked={partner} onChange={setPartner} />
          <ToggleRow label="HR Partner add-on ($2,000/mo)" checked={hrPartner} onChange={setHrPartner} />

          <Input
            label="Proposal date"
            type="date"
            value={proposalDate}
            onChange={(e) => setProposalDate(e.target.value)}
          />
        </div>

        {/* Live summary */}
        <div>
          {!validHeadcount ? (
            <p className="text-sm text-zinc-500">Enter a headcount to see pricing.</p>
          ) : !quotes ? (
            <p className="flex items-center gap-2 text-sm text-zinc-500">
              <Loader2 className="h-4 w-4 animate-spin" /> Calculating…
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
              <QuoteCard q={quotes.mid} recommended={tier === 'mid'} />
              <QuoteCard q={quotes.max} recommended={tier === 'max'} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function ToggleRow({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-zinc-300">{label}</span>
      <Toggle checked={checked} onChange={onChange} />
    </div>
  )
}
