import { useEffect, useMemo, useRef, useState } from 'react'
import { Loader2, Download, FileText, PencilLine } from 'lucide-react'
import { Button, Input } from '../../components/ui'
import { api } from '../../api/client'
import { getTemplate, saveTemplate } from '../../api/dealTemplates'
import SaveTemplateButton from './SaveTemplateButton'

type Block = { id: string; kind: string; text: string; items: string[]; new_page: boolean; column: string }
type MarginTier = { label: string; min_employees: number; max_employees: number; margin_pct: number }
type Cover = { wordmark: string; subtitle: string; product_line: string; product_title: string; tagline: string; footer_note: string; footer_contact: string }
type BrokerTemplate = { blocks: Block[]; margin_tiers: MarginTier[]; cover?: Cover }
type PlatformTier = 'lite' | 'mid' | 'max'

const EMPTY_COVER: Cover = { wordmark: '', subtitle: '', product_line: '', product_title: '', tagline: '', footer_note: '', footer_contact: '' }
// Placeholders mirror the server-side cover defaults — blank fields fall back to these.
const COVER_PH: Cover = {
  wordmark: 'matcha',
  subtitle: 'Risk, Compliance, Employee Relations Intelligence',
  product_line: 'Partner Program',
  product_title: 'Broker Edition',
  tagline: 'Sell risk management. Keep the margin.',
  footer_note: 'Confidential — proprietary partner pricing, for the named recipient only.',
  footer_contact: 'hey-matcha.com · aaron@hey-matcha.com',
}

const COMPUTED_LABEL: Record<string, string> = {
  cover: 'Cover (auto)',
  t_tiers: 'Margin tier table (auto)',
  t_wholesale: 'Wholesale rate card (auto)',
  book_econ: 'Book economics (auto)',
  t_sample: 'Sample client quote (auto)',
  sign: 'Signature blocks (auto)',
  disclaimer: 'Disclaimer (auto)',
}
const EDITABLE = new Set(['h2', 'h3', 'h4', 'p', 'note', 'callout', 'bullets'])
const int = (s: string, fb: number) => { const n = parseInt(s, 10); return Number.isFinite(n) ? n : fb }

export default function BrokerTab() {
  const today = useMemo(() => new Date().toISOString().slice(0, 10), [])
  const [brokerName, setBrokerName] = useState('')
  const [bookEmployees, setBookEmployees] = useState('2000')
  const [proposalDate, setProposalDate] = useState(today)
  const [repTier, setRepTier] = useState<PlatformTier>('mid')
  const [tierOverride, setTierOverride] = useState('auto')
  const [marginTiers, setMarginTiers] = useState<MarginTier[]>([])
  const [cover, setCover] = useState<Cover>(EMPTY_COVER)
  const [scName, setScName] = useState('Sample Client')
  const [scHeadcount, setScHeadcount] = useState('300')
  const [scTier, setScTier] = useState<PlatformTier>('mid')

  const [blocks, setBlocks] = useState<Block[] | null>(null)
  const [view, setView] = useState<'edit' | 'preview'>('edit')
  const [previewHtml, setPreviewHtml] = useState('')
  const [previewing, setPreviewing] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const bookNum = int(bookEmployees, 0)
  const valid = bookNum >= 0 && brokerName.trim().length >= 0

  useEffect(() => {
    Promise.all([
      api.get<{ blocks: Block[]; margin_tiers: MarginTier[] }>('/admin/deal-flow/broker-defaults'),
      getTemplate<BrokerTemplate>('broker'),
    ])
      .then(([def, saved]) => {
        const t = saved.payload
        setBlocks(t?.blocks ?? def.blocks)
        setMarginTiers(t?.margin_tiers ?? def.margin_tiers)
        if (t?.cover) setCover({ ...EMPTY_COVER, ...t.cover })
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load template'))
  }, [])

  const inputs = useMemo(
    () => ({
      broker_name: brokerName.trim() || 'Broker Partner',
      book_employees: bookNum,
      proposal_date: proposalDate || null,
      representative_tier: repTier,
      margin_tier_override: tierOverride === 'auto' ? null : tierOverride,
      margin_tiers: marginTiers.length ? marginTiers : null,
      sample_client_name: scName.trim() || 'Sample Client',
      sample_client_headcount: int(scHeadcount, 300),
      sample_client_tier: scTier,
      cover,
      blocks: blocks
        ? blocks.map((b) => (b.kind === 'bullets' ? { ...b, items: b.items.filter((i) => i.trim()) } : b))
        : null,
    }),
    [brokerName, bookNum, proposalDate, repTier, tierOverride, marginTiers, scName, scHeadcount, scTier, cover, blocks],
  )

  const inputsRef = useRef(inputs)
  inputsRef.current = inputs
  useEffect(() => {
    if (view !== 'preview') return
    setPreviewing(true)
    const t = setTimeout(() => {
      api.post<{ html: string }>('/admin/deal-flow/broker-proposal/preview', inputsRef.current)
        .then((r) => { setPreviewHtml(r.html); setError(null) })
        .catch((e) => setError(e instanceof Error ? e.message : 'Preview failed'))
        .finally(() => setPreviewing(false))
    }, 300)
    return () => clearTimeout(t)
  }, [view, inputs])

  function updateBlock(id: string, patch: Partial<Block>) {
    setBlocks((prev) => prev && prev.map((b) => (b.id === id ? { ...b, ...patch } : b)))
  }
  function removeBlock(id: string) {
    setBlocks((prev) => prev && prev.filter((b) => b.id !== id))
  }
  function updateTier(i: number, patch: Partial<MarginTier>) {
    setMarginTiers((prev) => prev.map((t, idx) => (idx === i ? { ...t, ...patch } : t)))
  }
  function updateCover(patch: Partial<Cover>) {
    setCover((prev) => ({ ...prev, ...patch }))
  }
  function addTier() {
    setMarginTiers((prev) => {
      const last = prev[prev.length - 1]
      const min = last ? (last.max_employees >= 10_000_000 ? last.min_employees : last.max_employees + 1) : 0
      return [...prev, { label: 'New Tier', min_employees: min, max_employees: 10_000_000, margin_pct: 10 }]
    })
  }
  function removeTier(i: number) {
    setMarginTiers((prev) => prev.filter((_, idx) => idx !== i))
  }

  async function saveTpl() {
    // Reusable template = program copy + margin-tier schedule; broker/sample-client are per-deal.
    await saveTemplate<BrokerTemplate>('broker', { blocks: blocks ?? [], margin_tiers: marginTiers, cover })
  }

  async function download() {
    setDownloading(true)
    setError(null)
    try {
      const safe = (brokerName.trim() || 'Broker').replace(/[^A-Za-z0-9]+/g, '_').replace(/^_|_$/g, '')
      await api.downloadPost('/admin/deal-flow/broker-proposal', inputs, `${safe}_Matcha_Partner_Program.pdf`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Download failed')
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
        <div className="flex items-center gap-2">
          <SaveTemplateButton onSave={saveTpl} />
          <Button onClick={download} disabled={downloading || !valid}>
            {downloading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Download className="mr-2 h-4 w-4" />}
            Download Partner Program PDF
          </Button>
        </div>
      </div>

      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

      <div className="mt-5 grid grid-cols-1 gap-6 lg:grid-cols-[340px_1fr]">
        <div className="space-y-5">
          <Section title="Broker">
            <Input label="Broker name" value={brokerName} onChange={(e) => setBrokerName(e.target.value)} placeholder="Alliant" />
            <div>
              <Input label="Committed seats" type="number" min={0} value={bookEmployees} onChange={(e) => setBookEmployees(e.target.value)} />
              <p className="mt-1 text-xs text-zinc-500">Combined headcount of the clients you enroll — can be part of the book, not all of it.</p>
            </div>
            <Input label="Proposal date" type="date" value={proposalDate} onChange={(e) => setProposalDate(e.target.value)} />
            <SelectRow label="Tier" value={tierOverride} onChange={setTierOverride}
              options={[['auto', 'Auto (by book size)'], ...marginTiers.map((t) => [t.label, t.label] as [string, string])]} />
            <SelectRow label="Book economics tier" value={repTier} onChange={(v) => setRepTier(v as PlatformTier)}
              options={[['lite', 'Lite'], ['mid', 'Mid'], ['max', 'Max']]} />
          </Section>

          <Section title="Cover page">
            <p className="text-xs text-zinc-500">Cover text. Leave a field blank to use the default (shown as the placeholder).</p>
            <CoverField label="Wordmark" k="wordmark" cover={cover} ph={COVER_PH} onChange={updateCover} />
            <CoverField label="Subtitle" k="subtitle" cover={cover} ph={COVER_PH} onChange={updateCover} />
            <div className="grid grid-cols-2 gap-2">
              <CoverField label="Product line" k="product_line" cover={cover} ph={COVER_PH} onChange={updateCover} />
              <CoverField label="Product title" k="product_title" cover={cover} ph={COVER_PH} onChange={updateCover} />
            </div>
            <CoverField label="Tagline" k="tagline" cover={cover} ph={COVER_PH} onChange={updateCover} />
            <CoverField label="Footer note" k="footer_note" cover={cover} ph={COVER_PH} onChange={updateCover} />
            <CoverField label="Footer contact" k="footer_contact" cover={cover} ph={COVER_PH} onChange={updateCover} />
          </Section>

          <Section title="Margin tiers">
            <div className="grid grid-cols-[1fr_auto_auto] items-center gap-x-3 gap-y-2 text-xs">
              <span className="font-medium text-zinc-500">Tier · book range</span>
              <span className="font-medium text-zinc-500">Margin %</span>
              <span />
              {marginTiers.map((t, i) => (
                <FragmentTier key={i} tier={t} onChange={(patch) => updateTier(i, patch)} onRemove={() => removeTier(i)} />
              ))}
            </div>
            <button type="button" onClick={addTier}
              className="text-xs font-medium text-violet-400 hover:text-violet-300">+ Add tier</button>
          </Section>

          <Section title="Sample client">
            <Input label="Client name" value={scName} onChange={(e) => setScName(e.target.value)} />
            <Input label="Headcount" type="number" min={1} value={scHeadcount} onChange={(e) => setScHeadcount(e.target.value)} />
            <SelectRow label="Platform tier" value={scTier} onChange={(v) => setScTier(v as PlatformTier)}
              options={[['lite', 'Lite'], ['mid', 'Mid'], ['max', 'Max']]} />
          </Section>
        </div>

        <div>
          {view === 'preview' ? (
            <div className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-200">
              {previewing && (
                <div className="flex items-center gap-2 bg-zinc-900 px-3 py-1.5 text-xs text-zinc-400">
                  <Loader2 className="h-3 w-3 animate-spin" /> Rendering…
                </div>
              )}
              <iframe title="broker preview" srcDoc={previewHtml} className="h-[80vh] w-full bg-white" />
            </div>
          ) : !blocks ? (
            <p className="flex items-center gap-2 text-sm text-zinc-500"><Loader2 className="h-4 w-4 animate-spin" /> Loading template…</p>
          ) : (
            <div className="space-y-3 rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
              <p className="text-xs text-zinc-500">Edit the program copy. Tables fill from the inputs at left. Preview to see the styled packet.</p>
              {blocks.map((b) => (
                <BlockEditor key={b.id} block={b} onChange={(patch) => updateBlock(b.id, patch)} onRemove={() => removeBlock(b.id)} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function CoverField({ label, k, cover, ph, onChange }: { label: string; k: keyof Cover; cover: Cover; ph: Cover; onChange: (patch: Partial<Cover>) => void }) {
  return <Input label={label} value={cover[k]} placeholder={ph[k]} onChange={(e) => onChange({ [k]: e.target.value })} />
}

function FragmentTier({ tier, onChange, onRemove }: { tier: MarginTier; onChange: (patch: Partial<MarginTier>) => void; onRemove: () => void }) {
  const isUnbounded = tier.max_employees >= 10_000_000
  return (
    <>
      <div className="flex items-center gap-1.5 text-sm text-zinc-300">
        <input
          value={tier.label} onChange={(e) => onChange({ label: e.target.value })}
          className="w-20 shrink-0 rounded-md border border-transparent bg-transparent px-1 py-0.5 font-bold text-zinc-100 hover:border-zinc-700 focus:border-violet-500 focus:outline-none"
        />
        <input
          type="number" min={0} value={tier.min_employees}
          onChange={(e) => onChange({ min_employees: int(e.target.value, tier.min_employees) })}
          className="w-16 rounded-md border border-zinc-700 bg-zinc-900 px-1.5 py-0.5 text-xs text-zinc-100 focus:border-violet-500 focus:outline-none"
        />
        <span className="text-zinc-500">–</span>
        <input
          type="number" min={0} value={isUnbounded ? '' : tier.max_employees} placeholder="∞"
          onChange={(e) => onChange({ max_employees: e.target.value.trim() === '' ? 10_000_000 : int(e.target.value, tier.max_employees) })}
          className="w-16 rounded-md border border-zinc-700 bg-zinc-900 px-1.5 py-0.5 text-xs text-zinc-100 focus:border-violet-500 focus:outline-none"
        />
      </div>
      <input
        type="number" min={0} max={90} value={tier.margin_pct}
        onChange={(e) => onChange({ margin_pct: int(e.target.value, tier.margin_pct) })}
        className="w-20 rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm text-zinc-100 focus:border-violet-500 focus:outline-none"
      />
      <button type="button" onClick={onRemove} title="Remove tier"
        className="shrink-0 rounded px-1.5 text-xs text-zinc-600 hover:bg-red-500/15 hover:text-red-400">✕</button>
    </>
  )
}

function BlockEditor({ block, onChange, onRemove }: { block: Block; onChange: (patch: Partial<Block>) => void; onRemove: () => void }) {
  const removeBtn = (
    <button type="button" onClick={onRemove} title="Remove block"
      className="shrink-0 rounded px-1.5 text-xs text-zinc-600 hover:bg-red-500/15 hover:text-red-400">✕</button>
  )

  if (!EDITABLE.has(block.kind)) {
    return (
      <div className="flex items-center justify-between gap-2 rounded-md border border-dashed border-zinc-700 bg-zinc-800/40 px-3 py-2 text-xs italic text-zinc-500">
        <span>▦ {COMPUTED_LABEL[block.kind] ?? block.kind}</span>
        {removeBtn}
      </div>
    )
  }
  if (block.kind === 'h2' || block.kind === 'h3' || block.kind === 'h4') {
    const size = block.kind === 'h2' ? 'text-lg font-bold' : block.kind === 'h3' ? 'text-base font-semibold' : 'text-sm font-semibold'
    return (
      <div className="flex items-center gap-1">
        <input value={block.text} onChange={(e) => onChange({ text: e.target.value })}
          className={`w-full rounded-md border border-transparent bg-transparent px-2 py-1 text-zinc-100 hover:border-zinc-700 focus:border-violet-500 focus:outline-none ${size}`} />
        {removeBtn}
      </div>
    )
  }
  if (block.kind === 'bullets') {
    return (
      <div className="flex items-start gap-1">
        <AutoTextarea value={block.items.join('\n')} onChange={(v) => onChange({ items: v.split('\n') })} className="text-sm text-zinc-300" placeholder="One per line" />
        {removeBtn}
      </div>
    )
  }
  const cls = block.kind === 'note' ? 'text-xs italic text-zinc-400'
    : block.kind === 'callout' ? 'text-sm text-zinc-200 border-l-2 border-violet-500/50 pl-3'
    : 'text-sm text-zinc-300'
  return (
    <div className="flex items-start gap-1">
      <AutoTextarea value={block.text} onChange={(v) => onChange({ text: v })} className={cls} />
      {removeBtn}
    </div>
  )
}

function AutoTextarea({ value, onChange, className = '', placeholder }: { value: string; onChange: (v: string) => void; className?: string; placeholder?: string }) {
  const ref = useRef<HTMLTextAreaElement>(null)
  useEffect(() => { const el = ref.current; if (el) { el.style.height = 'auto'; el.style.height = `${el.scrollHeight}px` } }, [value])
  return (
    <textarea ref={ref} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} rows={1}
      className={`w-full resize-none rounded-md border border-transparent bg-transparent px-2 py-1 leading-relaxed hover:border-zinc-700 focus:border-violet-500 focus:outline-none ${className}`} />
  )
}

function SelectRow({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: [string, string][] }) {
  return (
    <div>
      <label className="mb-1.5 block text-sm font-medium text-zinc-300">{label}</label>
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-2 py-2 text-sm text-zinc-100 focus:border-violet-500 focus:outline-none">
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </div>
  )
}

function ToggleBtn({ active, onClick, icon, children }: { active: boolean; onClick: () => void; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${active ? 'bg-violet-500/15 text-violet-200' : 'text-zinc-400 hover:text-zinc-200'}`}>
      {icon}{children}
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
