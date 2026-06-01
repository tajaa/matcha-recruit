import { useEffect, useMemo, useState } from 'react'
import { Loader2, Download, FileText } from 'lucide-react'
import { Button, Input, Toggle } from '../../components/ui'
import { api } from '../../api/client'
import { getTemplate, saveTemplate } from '../../api/dealTemplates'
import SaveTemplateButton from './SaveTemplateButton'
import FullDealTab from './FullDealTab'
import LiteEditionPanel from './LiteEditionPanel'
import BrokerTab from './BrokerTab'
import BookPricingTab from './BookPricingTab'

type Tier = 'lite' | 'mid' | 'max'
type OnePagerTemplate = { config: Record<Tier, { pepm: number; onboarding: number }> }

const TIERS: Tier[] = ['lite', 'mid', 'max']
const TIER_LABEL: Record<Tier, string> = { lite: 'Lite', mid: 'Mid', max: 'Max' }
const TIER_DEFAULTS: Record<Tier, { pepm: number; onboarding: number }> = {
  lite: { pepm: 5, onboarding: 0 },
  mid: { pepm: 10, onboarding: 4000 },
  max: { pepm: 13, onboarding: 10000 },
}

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

type QuoteResponse = Record<Tier, DealQuote>

type TierConfig = { pepm: string; onboarding: string }

const usd = (n: number) => `$${n.toLocaleString('en-US')}`

// Lite PEPM is volume-tiered (mirrors deal_pricing.lite_pepm): $5 base, −$1 over
// 100 employees, −$2 over 500. Mid/Max are flat.
function liteDefaultPepm(hc: number): number {
  if (hc > 500) return 3
  if (hc > 100) return 4
  return 5
}

function QuoteCard({ q, recommended }: { q: DealQuote; recommended: boolean }) {
  const note = q.onboarding === 0 ? 'no onboarding fee' : 'incl. onboarding'
  return (
    <div
      className={`rounded-xl border p-5 ${
        recommended ? 'border-violet-500/60 bg-violet-500/5' : 'border-zinc-800 bg-zinc-900/40'
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
      <p className="mt-0.5 text-xs text-zinc-500">
        ${q.pepm} PEPM · {note}
      </p>

      <div className="mt-4 space-y-1.5 text-sm">
        <Row label="Subscription / yr" value={usd(q.subscription_yr)} />
        <Row label="Onboarding" value={q.onboarding === 0 ? 'None' : `+${usd(q.onboarding)}`} />
        {(q.broker_disc > 0 || q.partner_disc > 0) && (
          <>
            <Row label="Subtotal" value={usd(q.subtotal)} bold border />
            {q.broker_disc > 0 && <Row label="Broker discount" value={`−${usd(q.broker_disc)}`} muted />}
            {q.partner_disc > 0 && <Row label="Partner discount" value={`−${usd(q.partner_disc)}`} muted />}
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
  const [brokerPct, setBrokerPct] = useState('10')
  const [partner, setPartner] = useState(true)
  const [partnerPct, setPartnerPct] = useState('5')
  const [hrPartner, setHrPartner] = useState(false)
  const [proposalDate, setProposalDate] = useState(today)
  const [template, setTemplate] = useState<'standard' | 'lite_edition'>('standard')
  // Lite PEPM auto-tracks headcount until the admin overrides it manually.
  const [liteManual, setLiteManual] = useState(false)

  // Editable per-tier price config (pre-filled with the standard structure).
  const [config, setConfig] = useState<Record<Tier, TierConfig>>(() => ({
    lite: { pepm: String(TIER_DEFAULTS.lite.pepm), onboarding: String(TIER_DEFAULTS.lite.onboarding) },
    mid: { pepm: String(TIER_DEFAULTS.mid.pepm), onboarding: String(TIER_DEFAULTS.mid.onboarding) },
    max: { pepm: String(TIER_DEFAULTS.max.pepm), onboarding: String(TIER_DEFAULTS.max.onboarding) },
  }))

  const [quotes, setQuotes] = useState<QuoteResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [downloading, setDownloading] = useState(false)
  const [view, setView] = useState<'onepager' | 'full' | 'broker' | 'book'>('onepager')
  const [showPreview, setShowPreview] = useState(false)
  const [previewHtml, setPreviewHtml] = useState('')
  const [previewing, setPreviewing] = useState(false)

  const headcountNum = parseInt(headcount, 10)
  const validHeadcount = Number.isFinite(headcountNum) && headcountNum > 0

  const setTierField = (t: Tier, field: keyof TierConfig, value: string) => {
    if (t === 'lite' && field === 'pepm') setLiteManual(true)
    setConfig((prev) => ({ ...prev, [t]: { ...prev[t], [field]: value } }))
  }

  // Auto-fill Lite PEPM from the volume rule until the admin overrides it.
  useEffect(() => {
    if (liteManual || !validHeadcount) return
    const auto = String(liteDefaultPepm(headcountNum))
    setConfig((prev) => (prev.lite.pepm === auto ? prev : { ...prev, lite: { ...prev.lite, pepm: auto } }))
  }, [headcountNum, validHeadcount, liteManual])

  // Load any saved one-pager pricing template (admin-global). Marks Lite as manual
  // so the volume auto-fill above doesn't clobber a saved Lite PEPM.
  useEffect(() => {
    getTemplate<OnePagerTemplate>('one_pager')
      .then((saved) => {
        const c = saved.payload?.config
        if (!c) return
        setConfig({
          lite: { pepm: String(c.lite.pepm), onboarding: String(c.lite.onboarding) },
          mid: { pepm: String(c.mid.pepm), onboarding: String(c.mid.onboarding) },
          max: { pepm: String(c.max.pepm), onboarding: String(c.max.onboarding) },
        })
        setLiteManual(true)
      })
      .catch(() => { /* no saved template → keep defaults */ })
  }, [])

  const inputs = useMemo(() => {
    const overrides: Record<string, { pepm: number; onboarding: number }> = {}
    for (const t of TIERS) {
      const pepm = parseInt(config[t].pepm, 10)
      const onboarding = parseInt(config[t].onboarding, 10)
      overrides[t] = {
        pepm: Number.isFinite(pepm) && pepm >= 0 ? pepm : TIER_DEFAULTS[t].pepm,
        onboarding: Number.isFinite(onboarding) && onboarding >= 0 ? onboarding : TIER_DEFAULTS[t].onboarding,
      }
    }
    return {
      company_name: companyName.trim() || 'Prospect',
      headcount: validHeadcount ? headcountNum : 0,
      tier,
      broker,
      broker_name: broker ? brokerName.trim() || 'Broker' : null,
      broker_pct: parseInt(brokerPct, 10) || 0,
      partner,
      partner_pct: parseInt(partnerPct, 10) || 0,
      hr_partner_addon: hrPartner,
      proposal_date: proposalDate || null,
      overrides,
      template,
    }
  }, [companyName, headcountNum, validHeadcount, tier, broker, brokerName, brokerPct, partner, partnerPct, hrPartner, proposalDate, config, template])

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

  // Styled preview (same HTML as the PDF), fetched on demand.
  useEffect(() => {
    if (!showPreview || !validHeadcount) return
    setPreviewing(true)
    const t = setTimeout(() => {
      api.post<{ html: string }>('/admin/deal-flow/proposal/preview', inputs)
        .then((r) => { setPreviewHtml(r.html); setError(null) })
        .catch((e) => setError(e instanceof Error ? e.message : 'Preview failed'))
        .finally(() => setPreviewing(false))
    }, 300)
    return () => clearTimeout(t)
  }, [showPreview, inputs, validHeadcount])

  async function saveTpl() {
    const c = {} as Record<Tier, { pepm: number; onboarding: number }>
    for (const t of TIERS) {
      const pepm = parseInt(config[t].pepm, 10)
      const onboarding = parseInt(config[t].onboarding, 10)
      c[t] = {
        pepm: Number.isFinite(pepm) && pepm >= 0 ? pepm : TIER_DEFAULTS[t].pepm,
        onboarding: Number.isFinite(onboarding) && onboarding >= 0 ? onboarding : TIER_DEFAULTS[t].onboarding,
      }
    }
    await saveTemplate<OnePagerTemplate>('one_pager', { config: c })
  }

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
      <h1 className="text-2xl font-semibold text-zinc-100">Deal Flow</h1>
      <p className="mt-2 text-sm text-zinc-500">Generate Matcha proposals. Per-deal inputs are transient; Save persists the editable template for each tab.</p>

      <div className="mt-5 flex gap-2 border-b border-zinc-800">
        {([
          ['onepager', 'One-Pager'],
          ['full', 'Full Deal'],
          ['broker', 'Broker'],
          ['book', 'Book Pricing'],
        ] as const).map(([val, label]) => (
          <button
            key={val}
            type="button"
            onClick={() => setView(val)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
              view === val
                ? 'border-violet-500 text-violet-200'
                : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {view === 'full' ? (
        <FullDealTab />
      ) : view === 'broker' ? (
        <BrokerTab />
      ) : view === 'book' ? (
        <BookPricingTab />
      ) : (
        <div>
          <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-zinc-500">
              Configure off the Lite / Mid / Max structure and generate a proposal PDF.
            </p>
            <div className="flex items-center gap-2">
              <SaveTemplateButton onSave={saveTpl} label="Save pricing" />
              {template === 'standard' && (
                <>
                  <Button variant="secondary" onClick={() => setShowPreview((v) => !v)} disabled={!validHeadcount}>
                    <FileText className="mr-2 h-4 w-4" />
                    {showPreview ? 'Hide preview' : 'Preview'}
                  </Button>
                  <Button onClick={downloadProposal} disabled={!validHeadcount || downloading}>
                    {downloading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Download className="mr-2 h-4 w-4" />}
                    Download Proposal PDF
                  </Button>
                </>
              )}
            </div>
          </div>

          {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

          <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[380px_1fr]">
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
            <label className="mb-1.5 block text-sm font-medium text-zinc-300">Proposal template</label>
            <div className="flex gap-2">
              {([
                ['standard', 'Standard (3-tier)'],
                ['lite_edition', 'Lite Edition'],
              ] as const).map(([val, label]) => (
                <button
                  key={val}
                  type="button"
                  onClick={() => setTemplate(val)}
                  className={`flex-1 rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
                    template === val
                      ? 'border-violet-500/60 bg-violet-500/10 text-violet-200'
                      : 'border-zinc-700 text-zinc-400 hover:border-zinc-600'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            {template === 'lite_edition' && (
              <p className="mt-1.5 text-xs text-zinc-500">
                Single-page green Lite one-pager. Uses the Lite tier pricing.
              </p>
            )}
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-zinc-300">Recommended tier</label>
            <div className="flex gap-2">
              {TIERS.map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTier(t)}
                  className={`flex-1 rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
                    tier === t
                      ? 'border-violet-500/60 bg-violet-500/10 text-violet-200'
                      : 'border-zinc-700 text-zinc-400 hover:border-zinc-600'
                  }`}
                >
                  {TIER_LABEL[t]}
                </button>
              ))}
            </div>
          </div>

          {/* Per-tier price overrides */}
          <div className="space-y-3 rounded-lg border border-zinc-800 p-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Pricing per tier</p>
            <div className="grid grid-cols-[auto_1fr_1fr] items-center gap-x-3 gap-y-2 text-xs">
              <span />
              <span className="font-medium text-zinc-500">PEPM ($)</span>
              <span className="font-medium text-zinc-500">Onboarding ($)</span>
              {TIERS.map((t) => (
                <FragmentRow
                  key={t}
                  label={TIER_LABEL[t]}
                  cfg={config[t]}
                  onChange={(field, v) => setTierField(t, field, v)}
                />
              ))}
            </div>
          </div>

          <ToggleRow label="Broker discount" checked={broker} onChange={setBroker} />
          {broker && (
            <div className="grid grid-cols-2 gap-3">
              <Input label="Broker name" value={brokerName} onChange={(e) => setBrokerName(e.target.value)} placeholder="Alliant" />
              <Input label="Broker %" type="number" min={0} max={100} value={brokerPct} onChange={(e) => setBrokerPct(e.target.value)} />
            </div>
          )}
          <ToggleRow label="Partner program" checked={partner} onChange={setPartner} />
          {partner && (
            <Input label="Partner %" type="number" min={0} max={100} value={partnerPct} onChange={(e) => setPartnerPct(e.target.value)} />
          )}
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
          {template === 'lite_edition' ? (
            <LiteEditionPanel baseInputs={inputs} validHeadcount={validHeadcount} filenameBase={companyName} />
          ) : showPreview ? (
            <div className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-200">
              {previewing && (
                <div className="flex items-center gap-2 bg-zinc-900 px-3 py-1.5 text-xs text-zinc-400">
                  <Loader2 className="h-3 w-3 animate-spin" /> Rendering…
                </div>
              )}
              <iframe title="proposal preview" srcDoc={previewHtml} className="h-[80vh] w-full bg-white" />
            </div>
          ) : !validHeadcount ? (
            <p className="text-sm text-zinc-500">Enter a headcount to see pricing.</p>
          ) : !quotes ? (
            <p className="flex items-center gap-2 text-sm text-zinc-500">
              <Loader2 className="h-4 w-4 animate-spin" /> Calculating…
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-3">
              {TIERS.map((t) => (
                <QuoteCard key={t} q={quotes[t]} recommended={tier === t} />
              ))}
            </div>
          )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function FragmentRow({
  label,
  cfg,
  onChange,
}: {
  label: string
  cfg: TierConfig
  onChange: (field: keyof TierConfig, value: string) => void
}) {
  return (
    <>
      <span className="text-sm font-medium text-zinc-300">{label}</span>
      <input
        type="number"
        min={0}
        value={cfg.pepm}
        onChange={(e) => onChange('pepm', e.target.value)}
        className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm text-zinc-100 focus:border-violet-500 focus:outline-none"
      />
      <input
        type="number"
        min={0}
        value={cfg.onboarding}
        onChange={(e) => onChange('onboarding', e.target.value)}
        className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm text-zinc-100 focus:border-violet-500 focus:outline-none"
      />
    </>
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
