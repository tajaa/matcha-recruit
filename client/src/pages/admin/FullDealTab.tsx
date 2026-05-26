import { useEffect, useMemo, useState } from 'react'
import { Loader2, Download } from 'lucide-react'
import { Button, Input, Toggle } from '../../components/ui'
import { api } from '../../api/client'

// Defaults mirror server/app/core/services/deal_full.py (kept in sync by hand).
const DEFAULT_EXEC_SUMMARY = `Matcha is a compliance, employee relations, and workforce risk platform built for organizations that carry heavy regulatory and funding obligations on lean administrative budgets. Your compliance and HR team stops manually checking regulatory pages and opens one dashboard. Every requirement that applies to your workforce is monitored continuously. When something changes, they get an alert with severity, which team is affected, and what action to take.

From employment law and local ordinances to data privacy, ER investigations, pre-termination risk scoring, and intelligent policy documents, Matcha consolidates fragmented HR operations into a single platform. The system is configured during implementation with the categories that apply to your operation, alongside your core labor obligations: minimum wage, local wage ordinances, meal and rest breaks, paid sick leave, and workers' compensation.

When your team has a compliance question, they type it into the system, and it walks through the jurisdiction hierarchy, identifies which level of law governs, cites the statutes, and shows the penalty range and enforcing agency. Sourced from government databases with citation links and verification timestamps, not generated from thin air.

What your team owns after go-live: the system. We build it during implementation, then hand it off. The CSM stays assigned, but the platform runs independently. You're not paying for a service — you're buying infrastructure.`

const DEFAULT_ROI_INTRO = `Organizations in regulated, multi-site environments carry a disproportionately high compliance burden relative to their administrative budgets — and a disproportionately high consequence when something goes wrong. A single wage-and-hour class action can run well into six figures in back pay and penalties before defense costs. A retaliation or wrongful-termination claim can generate $150,000+ in defense costs. The hard savings below reflect what the platform replaces. The risk-reduction value reflects what it prevents.`

const num = (s: string, fallback: number) => {
  const n = parseFloat(s)
  return Number.isFinite(n) ? n : fallback
}
const int = (s: string, fallback: number) => {
  const n = parseInt(s, 10)
  return Number.isFinite(n) ? n : fallback
}

export default function FullDealTab() {
  const today = useMemo(() => new Date().toISOString().slice(0, 10), [])
  const [companyName, setCompanyName] = useState('')
  const [headcount, setHeadcount] = useState('500')
  const [location, setLocation] = useState('')
  const [proposalDate, setProposalDate] = useState(today)

  const [rackPepm, setRackPepm] = useState('15.00')
  const [platformFee, setPlatformFee] = useState('5000')
  const [implementation, setImplementation] = useState('8000')
  const [jurisExtra, setJurisExtra] = useState('0')

  const [broker, setBroker] = useState(true)
  const [brokerName, setBrokerName] = useState('Alliant')
  const [partner, setPartner] = useState(true)
  const [volume, setVolume] = useState(true)
  const [volumeManual, setVolumeManual] = useState(false)

  const [hardSavings, setHardSavings] = useState('223000')
  const [riskReduction, setRiskReduction] = useState('60000')

  const [execSummary, setExecSummary] = useState(DEFAULT_EXEC_SUMMARY)
  const [roiIntro, setRoiIntro] = useState(DEFAULT_ROI_INTRO)

  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const headcountNum = int(headcount, 0)
  const validHeadcount = headcountNum > 0

  // Volume discount auto-tracks 500+ until manually toggled.
  useEffect(() => {
    if (volumeManual || !validHeadcount) return
    setVolume(headcountNum >= 500)
  }, [headcountNum, validHeadcount, volumeManual])

  const inputs = useMemo(
    () => ({
      company_name: companyName.trim() || 'Prospect',
      headcount: validHeadcount ? headcountNum : 1,
      location: location.trim(),
      proposal_date: proposalDate || null,
      rack_pepm: num(rackPepm, 15),
      platform_fee: int(platformFee, 5000),
      implementation: int(implementation, 8000),
      jurisdictions_included: 1,
      jurisdictions_extra: int(jurisExtra, 0),
      volume_discount: volume,
      broker,
      broker_name: broker ? brokerName.trim() || 'Broker' : null,
      partner,
      roi_hard_savings: int(hardSavings, 0),
      roi_risk_reduction: int(riskReduction, 0),
      exec_summary: execSummary,
      roi_intro: roiIntro,
    }),
    [companyName, headcountNum, validHeadcount, location, proposalDate, rackPepm, platformFee,
     implementation, jurisExtra, volume, broker, brokerName, partner, hardSavings, riskReduction,
     execSummary, roiIntro],
  )

  async function downloadFull() {
    if (!validHeadcount) return
    setDownloading(true)
    setError(null)
    try {
      const safe = (companyName.trim() || 'Matcha').replace(/[^A-Za-z0-9]+/g, '_').replace(/^_|_$/g, '')
      await api.downloadPost('/admin/deal-flow/full-proposal', inputs, `${safe}_Matcha_Full_Proposal.pdf`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Full proposal download failed')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div>
      <div className="mt-6 flex items-center justify-between">
        <p className="text-sm text-zinc-500">
          Full multi-page service proposal (rack-rate model). Numbers come from inputs; prose is editable below.
        </p>
        <Button onClick={downloadFull} disabled={!validHeadcount || downloading}>
          {downloading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Download className="mr-2 h-4 w-4" />}
          Download Full Proposal PDF
        </Button>
      </div>

      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Deal facts */}
        <Section title="Deal">
          <Input label="Company name" value={companyName} onChange={(e) => setCompanyName(e.target.value)} placeholder="LA Non-Profit" />
          <Input label="Headcount" type="number" min={1} value={headcount} onChange={(e) => setHeadcount(e.target.value)} />
          <Input label="Location" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="California (Los Angeles)" />
          <Input label="Proposal date" type="date" value={proposalDate} onChange={(e) => setProposalDate(e.target.value)} />
        </Section>

        {/* Pricing */}
        <Section title="Pricing">
          <Input label="Rack PEPM ($)" type="number" step="0.01" min={0} value={rackPepm} onChange={(e) => setRackPepm(e.target.value)} />
          <Input label="Platform fee — standard ($/yr)" type="number" min={0} value={platformFee} onChange={(e) => setPlatformFee(e.target.value)} />
          <Input label="Implementation — standard ($)" type="number" min={0} value={implementation} onChange={(e) => setImplementation(e.target.value)} />
          <Input label="Additional jurisdictions (count)" type="number" min={0} value={jurisExtra} onChange={(e) => setJurisExtra(e.target.value)} />
          <ToggleRow label="Volume discount (−10% PEPM)" checked={volume} onChange={(v) => { setVolumeManual(true); setVolume(v) }} />
          <ToggleRow label="Broker discount (−10%)" checked={broker} onChange={setBroker} />
          {broker && <Input label="Broker name" value={brokerName} onChange={(e) => setBrokerName(e.target.value)} />}
          <ToggleRow label="Partner program (−5%)" checked={partner} onChange={setPartner} />
        </Section>

        {/* ROI */}
        <Section title="ROI assumptions">
          <Input label="Annual hard savings ($)" type="number" min={0} value={hardSavings} onChange={(e) => setHardSavings(e.target.value)} />
          <Input label="Annual risk-reduction value ($)" type="number" min={0} value={riskReduction} onChange={(e) => setRiskReduction(e.target.value)} />
          <p className="text-xs text-zinc-500">
            Investment rows compute from pricing; net savings = total value − investment.
          </p>
        </Section>

        {/* Prose */}
        <Section title="Prose (editable)">
          <Textarea label="Executive Summary" value={execSummary} onChange={setExecSummary} rows={10} />
          <Textarea label="ROI intro" value={roiIntro} onChange={setRoiIntro} rows={5} />
          <p className="text-xs text-zinc-500">Separate paragraphs with a blank line. First Exec Summary paragraph becomes the highlighted callout.</p>
        </Section>
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-4 rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
      <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">{title}</p>
      {children}
    </div>
  )
}

function Textarea({
  label,
  value,
  onChange,
  rows,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  rows: number
}) {
  return (
    <div>
      <label className="mb-1.5 block text-sm font-medium text-zinc-300">{label}</label>
      <textarea
        value={value}
        rows={rows}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm leading-relaxed text-zinc-100 focus:border-violet-500 focus:outline-none"
      />
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
