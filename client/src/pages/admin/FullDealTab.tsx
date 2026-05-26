import { useEffect, useMemo, useRef, useState } from 'react'
import { Loader2, Download, FileText, PencilLine } from 'lucide-react'
import { Button, Input, Toggle } from '../../components/ui'
import { api } from '../../api/client'

type BlockKind =
  | 'h2' | 'h3' | 'h4' | 'p' | 'note' | 'callout' | 'highlight' | 'bullets'
  | 'cover' | 't_pepm' | 't_costs' | 'hr_rate' | 't_savings' | 't_jurisdiction' | 't_roi' | 'sign' | 'disclaimer'

type Block = { id: string; kind: BlockKind; text: string; items: string[]; new_page: boolean }

const COMPUTED_LABEL: Partial<Record<BlockKind, string>> = {
  cover: 'Cover page (auto)',
  t_pepm: 'PEPM build-up table (auto from pricing)',
  t_costs: 'Annual cost table (auto from pricing)',
  hr_rate: 'HR Advisory rate card (standard)',
  t_savings: 'Savings table (auto from pricing)',
  t_jurisdiction: 'Jurisdiction fee schedule (auto)',
  t_roi: 'ROI table + highlight (auto)',
  sign: 'Signature blocks (auto)',
  disclaimer: 'Disclaimer (auto)',
}
const EDITABLE = new Set<BlockKind>(['h2', 'h3', 'h4', 'p', 'note', 'callout', 'highlight', 'bullets'])

const int = (s: string, fb: number) => { const n = parseInt(s, 10); return Number.isFinite(n) ? n : fb }
const num = (s: string, fb: number) => { const n = parseFloat(s); return Number.isFinite(n) ? n : fb }

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
  const [brokerPct, setBrokerPct] = useState('10')
  const [partner, setPartner] = useState(true)
  const [partnerPct, setPartnerPct] = useState('5')
  const [volume, setVolume] = useState(true)
  const [volumeManual, setVolumeManual] = useState(false)
  const [hardSavings, setHardSavings] = useState('223000')
  const [riskReduction, setRiskReduction] = useState('60000')

  const [blocks, setBlocks] = useState<Block[] | null>(null)
  const [view, setView] = useState<'edit' | 'preview'>('edit')
  const [previewHtml, setPreviewHtml] = useState('')
  const [previewing, setPreviewing] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const headcountNum = int(headcount, 0)
  const validHeadcount = headcountNum > 0

  // Load the default document once.
  useEffect(() => {
    api.get<{ blocks: Block[] }>('/admin/deal-flow/full-defaults')
      .then((r) => setBlocks(r.blocks))
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load template'))
  }, [])

  // Volume auto-tracks 500+ until manually toggled.
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
      broker_pct: int(brokerPct, 10),
      partner,
      partner_pct: int(partnerPct, 5),
      roi_hard_savings: int(hardSavings, 0),
      roi_risk_reduction: int(riskReduction, 0),
      blocks: blocks
        ? blocks.map((b) => (b.kind === 'bullets' ? { ...b, items: b.items.filter((i) => i.trim()) } : b))
        : null,
    }),
    [companyName, headcountNum, validHeadcount, location, proposalDate, rackPepm, platformFee,
     implementation, jurisExtra, volume, broker, brokerName, brokerPct, partner, partnerPct, hardSavings, riskReduction, blocks],
  )

  // Refresh the preview when in preview mode (debounced).
  const inputsRef = useRef(inputs)
  inputsRef.current = inputs
  useEffect(() => {
    if (view !== 'preview' || !validHeadcount) return
    setPreviewing(true)
    const t = setTimeout(() => {
      api.post<{ html: string }>('/admin/deal-flow/full-proposal/preview', inputsRef.current)
        .then((r) => { setPreviewHtml(r.html); setError(null) })
        .catch((e) => setError(e instanceof Error ? e.message : 'Preview failed'))
        .finally(() => setPreviewing(false))
    }, 350)
    return () => clearTimeout(t)
  }, [view, inputs, validHeadcount])

  function updateBlock(id: string, patch: Partial<Block>) {
    setBlocks((prev) => prev && prev.map((b) => (b.id === id ? { ...b, ...patch } : b)))
  }

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
      <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex rounded-lg border border-zinc-700 p-0.5">
          <ToggleBtn active={view === 'edit'} onClick={() => setView('edit')} icon={<PencilLine className="h-4 w-4" />}>Edit</ToggleBtn>
          <ToggleBtn active={view === 'preview'} onClick={() => setView('preview')} icon={<FileText className="h-4 w-4" />}>Preview</ToggleBtn>
        </div>
        <Button onClick={downloadFull} disabled={!validHeadcount || downloading}>
          {downloading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Download className="mr-2 h-4 w-4" />}
          Download Full Proposal PDF
        </Button>
      </div>

      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

      <div className="mt-5 grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
        {/* Inputs */}
        <div className="space-y-5">
          <Section title="Deal">
            <Input label="Company name" value={companyName} onChange={(e) => setCompanyName(e.target.value)} placeholder="LA Non-Profit" />
            <Input label="Headcount" type="number" min={1} value={headcount} onChange={(e) => setHeadcount(e.target.value)} />
            <Input label="Location" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="California (Los Angeles)" />
            <Input label="Proposal date" type="date" value={proposalDate} onChange={(e) => setProposalDate(e.target.value)} />
          </Section>
          <Section title="Pricing">
            <Input label="Rack PEPM ($)" type="number" step="0.01" min={0} value={rackPepm} onChange={(e) => setRackPepm(e.target.value)} />
            <Input label="Platform fee — standard ($/yr)" type="number" min={0} value={platformFee} onChange={(e) => setPlatformFee(e.target.value)} />
            <Input label="Implementation — standard ($)" type="number" min={0} value={implementation} onChange={(e) => setImplementation(e.target.value)} />
            <Input label="Additional jurisdictions" type="number" min={0} value={jurisExtra} onChange={(e) => setJurisExtra(e.target.value)} />
            <ToggleRow label="Volume (−10% PEPM)" checked={volume} onChange={(v) => { setVolumeManual(true); setVolume(v) }} />
            <ToggleRow label="Broker discount" checked={broker} onChange={setBroker} />
            {broker && (
              <div className="grid grid-cols-2 gap-3">
                <Input label="Broker name" value={brokerName} onChange={(e) => setBrokerName(e.target.value)} />
                <Input label="Broker %" type="number" min={0} max={100} value={brokerPct} onChange={(e) => setBrokerPct(e.target.value)} />
              </div>
            )}
            <ToggleRow label="Partner program" checked={partner} onChange={setPartner} />
            {partner && <Input label="Partner %" type="number" min={0} max={100} value={partnerPct} onChange={(e) => setPartnerPct(e.target.value)} />}
          </Section>
          <Section title="ROI assumptions">
            <Input label="Annual hard savings ($)" type="number" min={0} value={hardSavings} onChange={(e) => setHardSavings(e.target.value)} />
            <Input label="Risk-reduction value ($)" type="number" min={0} value={riskReduction} onChange={(e) => setRiskReduction(e.target.value)} />
          </Section>
        </div>

        {/* Document / Preview */}
        <div>
          {view === 'preview' ? (
            <div className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-200">
              {previewing && (
                <div className="flex items-center gap-2 bg-zinc-900 px-3 py-1.5 text-xs text-zinc-400">
                  <Loader2 className="h-3 w-3 animate-spin" /> Rendering…
                </div>
              )}
              <iframe title="proposal preview" srcDoc={previewHtml} className="h-[80vh] w-full bg-white" />
            </div>
          ) : !blocks ? (
            <p className="flex items-center gap-2 text-sm text-zinc-500"><Loader2 className="h-4 w-4 animate-spin" /> Loading template…</p>
          ) : (
            <div className="space-y-3 rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
              <p className="text-xs text-zinc-500">Edit any heading or paragraph. Pricing tables fill in from the inputs at left. Switch to Preview to see the styled document.</p>
              {blocks.map((b) => (
                <BlockEditor key={b.id} block={b} onChange={(patch) => updateBlock(b.id, patch)} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function BlockEditor({ block, onChange }: { block: Block; onChange: (patch: Partial<Block>) => void }) {
  if (!EDITABLE.has(block.kind)) {
    return (
      <div className="rounded-md border border-dashed border-zinc-700 bg-zinc-800/40 px-3 py-2 text-xs italic text-zinc-500">
        ▦ {COMPUTED_LABEL[block.kind] ?? block.kind}
      </div>
    )
  }
  if (block.kind === 'h2' || block.kind === 'h3' || block.kind === 'h4') {
    const size = block.kind === 'h2' ? 'text-lg font-bold' : block.kind === 'h3' ? 'text-base font-semibold' : 'text-sm font-semibold'
    return (
      <input
        value={block.text}
        onChange={(e) => onChange({ text: e.target.value })}
        className={`w-full rounded-md border border-transparent bg-transparent px-2 py-1 text-zinc-100 hover:border-zinc-700 focus:border-violet-500 focus:outline-none ${size}`}
      />
    )
  }
  if (block.kind === 'bullets') {
    return (
      <AutoTextarea
        value={block.items.join('\n')}
        onChange={(v) => onChange({ items: v.split('\n') })}
        className="text-sm text-zinc-300"
        placeholder="One bullet per line"
      />
    )
  }
  const cls =
    block.kind === 'note' ? 'text-xs italic text-zinc-400'
    : block.kind === 'callout' ? 'text-sm text-zinc-200 border-l-2 border-violet-500/50 pl-3'
    : block.kind === 'highlight' ? 'text-sm font-medium text-zinc-100'
    : 'text-sm text-zinc-300'
  return <AutoTextarea value={block.text} onChange={(v) => onChange({ text: v })} className={cls} />
}

function AutoTextarea({
  value, onChange, className = '', placeholder,
}: { value: string; onChange: (v: string) => void; className?: string; placeholder?: string }) {
  const ref = useRef<HTMLTextAreaElement>(null)
  useEffect(() => {
    const el = ref.current
    if (el) { el.style.height = 'auto'; el.style.height = `${el.scrollHeight}px` }
  }, [value])
  return (
    <textarea
      ref={ref}
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      rows={1}
      className={`w-full resize-none rounded-md border border-transparent bg-transparent px-2 py-1 leading-relaxed hover:border-zinc-700 focus:border-violet-500 focus:outline-none ${className}`}
    />
  )
}

function ToggleBtn({ active, onClick, icon, children }: { active: boolean; onClick: () => void; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
        active ? 'bg-violet-500/15 text-violet-200' : 'text-zinc-400 hover:text-zinc-200'
      }`}
    >
      {icon}
      {children}
    </button>
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

function ToggleRow({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-zinc-300">{label}</span>
      <Toggle checked={checked} onChange={onChange} />
    </div>
  )
}
