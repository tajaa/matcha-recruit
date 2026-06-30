import { useEffect, useMemo, useRef, useState } from 'react'
import { Loader2, Download, FileText, PencilLine, Plus, X } from 'lucide-react'
import { Button, Input } from '../../components/ui'
import { api } from '../../api/client'
import { getTemplate, saveTemplate } from '../../api/dealTemplates'
import SaveTemplateButton from './SaveTemplateButton'

type Block = { id: string; kind: string; text: string; items: string[]; new_page: boolean; column: string }
type DiscountTier = { min_seats: number; discount_pct: number; max_seats?: number | null }
type ClientRow = { name: string; seats: string }
type Cover = { wordmark: string; subtitle: string; product_line: string; product_title: string; tagline: string; footer_note: string; footer_contact: string; title_font: string; accent_color: string; bg_style: string }
type BookTemplate = { blocks: Block[]; discount_tiers: DiscountTier[]; list_pepm: number; cover?: Cover }

// Text fields blank → server default; design fields carry concrete defaults so the controls render.
const EMPTY_COVER: Cover = { wordmark: '', subtitle: '', product_line: '', product_title: '', tagline: '', footer_note: '', footer_contact: '', title_font: 'Fraunces', accent_color: '#7c6cff', bg_style: 'ink' }
// Placeholders mirror the server-side cover defaults — blank fields fall back to these.
const COVER_PH: Cover = {
  wordmark: 'matcha',
  subtitle: 'Risk, Compliance, Employee Relations Intelligence',
  product_line: 'Matcha Lite',
  product_title: 'Book Pricing',
  tagline: 'One platform for your whole book. One pooled rate.',
  footer_note: 'Confidential — proprietary partner pricing, for the named recipient only.',
  footer_contact: 'hey-matcha.com · aaron@hey-matcha.com',
  title_font: 'Fraunces', accent_color: '#7c6cff', bg_style: 'ink',
}
const FONT_OPTS: [string, string][] = [['Fraunces', 'Fraunces (serif)'], ['Playfair Display', 'Playfair Display'], ['Cormorant Garamond', 'Cormorant Garamond'], ['Space Grotesk', 'Space Grotesk'], ['Inter', 'Inter (sans)']]
const BG_OPTS: [string, string][] = [['ink', 'Ink (navy)'], ['noir', 'Noir'], ['plum', 'Plum'], ['forest', 'Forest'], ['slate', 'Slate']]

const COMPUTED_LABEL: Record<string, string> = {
  cover: 'Cover — edit text & design in the "Cover page" panel ←',
  t_discount: 'Volume discount schedule (auto)',
  t_roster: 'Client roster (auto)',
  book_econ: 'Book economics (auto)',
  sign: 'Signature blocks (auto)',
  disclaimer: 'Disclaimer (auto)',
}
const EDITABLE = new Set(['h2', 'h3', 'h4', 'p', 'note', 'callout', 'bullets'])
const int = (s: string, fb: number) => { const n = parseInt(s, 10); return Number.isFinite(n) ? n : fb }
const num = (s: string, fb: number) => { const n = parseFloat(s); return Number.isFinite(n) ? n : fb }

// Pooled discount: highest tier whose min_seats <= total committed seats (mirrors deal_book).
function discountFor(tiers: DiscountTier[], total: number): number {
  let d = 0
  for (const t of [...tiers].sort((a, b) => a.min_seats - b.min_seats)) {
    if (total >= t.min_seats) d = t.discount_pct
  }
  return d
}

export default function BookPricingTab() {
  const today = useMemo(() => new Date().toISOString().slice(0, 10), [])
  const [brokerName, setBrokerName] = useState('')
  const [listPepm, setListPepm] = useState('5')
  const [proposalDate, setProposalDate] = useState(today)
  const [tiers, setTiers] = useState<DiscountTier[]>([])
  const [cover, setCover] = useState<Cover>(EMPTY_COVER)
  const [clients, setClients] = useState<ClientRow[]>([
    { name: 'Acme Clinic', seats: '80' },
    { name: 'Baytown Mfg', seats: '210' },
    { name: 'North HVAC', seats: '350' },
  ])

  const [blocks, setBlocks] = useState<Block[] | null>(null)
  const [view, setView] = useState<'edit' | 'preview'>('edit')
  const [previewHtml, setPreviewHtml] = useState('')
  const [previewing, setPreviewing] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      api.get<{ blocks: Block[]; discount_tiers: DiscountTier[] }>('/admin/deal-flow/book-defaults'),
      getTemplate<BookTemplate>('book'),
    ])
      .then(([def, saved]) => {
        const t = saved.payload
        setBlocks(t?.blocks ?? def.blocks)
        setTiers(t?.discount_tiers ?? def.discount_tiers)
        if (t?.list_pepm != null) setListPepm(String(t.list_pepm))
        if (t?.cover) setCover({ ...EMPTY_COVER, ...t.cover })
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load template'))
  }, [])

  const list = num(listPepm, 5)
  const totalSeats = useMemo(() => clients.reduce((s, c) => s + int(c.seats, 0), 0), [clients])
  const disc = discountFor(tiers, totalSeats)
  const netPepm = Math.round(list * (1 - disc / 100) * 100) / 100

  const inputs = useMemo(
    () => ({
      broker_name: brokerName.trim() || 'Broker Partner',
      list_pepm: list,
      discount_tiers: tiers,
      clients: clients
        .map((c) => ({ name: c.name.trim(), seats: int(c.seats, 0) }))
        .filter((c) => c.name || c.seats > 0),
      proposal_date: proposalDate || null,
      cover,
      blocks: blocks
        ? blocks.map((b) => (b.kind === 'bullets' ? { ...b, items: b.items.filter((i) => i.trim()) } : b))
        : null,
    }),
    [brokerName, list, tiers, clients, proposalDate, cover, blocks],
  )

  const inputsRef = useRef(inputs)
  inputsRef.current = inputs
  useEffect(() => {
    if (view !== 'preview') return
    setPreviewing(true)
    const t = setTimeout(() => {
      api.post<{ html: string }>('/admin/deal-flow/book-proposal/preview', inputsRef.current)
        .then((r) => { setPreviewHtml(r.html); setError(null) })
        .catch((e) => setError(e instanceof Error ? e.message : 'Preview failed'))
        .finally(() => setPreviewing(false))
    }, 300)
    return () => clearTimeout(t)
  }, [view, inputs])

  function updateBlock(id: string, patch: Partial<Block>) {
    setBlocks((prev) => prev && prev.map((b) => (b.id === id ? { ...b, ...patch } : b)))
  }
  function updateCover(patch: Partial<Cover>) {
    setCover((prev) => ({ ...prev, ...patch }))
  }
  function updateTier(i: number, patch: Partial<DiscountTier>) {
    setTiers((prev) => prev.map((t, idx) => (idx === i ? { ...t, ...patch } : t)))
  }
  function addTier() {
    setTiers((prev) => [...prev, { min_seats: 0, discount_pct: 0 }])
  }
  function removeTier(i: number) {
    setTiers((prev) => prev.filter((_, idx) => idx !== i))
  }
  function updateClient(i: number, patch: Partial<ClientRow>) {
    setClients((prev) => prev.map((c, idx) => (idx === i ? { ...c, ...patch } : c)))
  }
  function addClient() {
    setClients((prev) => [...prev, { name: '', seats: '' }])
  }
  function removeClient(i: number) {
    setClients((prev) => prev.filter((_, idx) => idx !== i))
  }

  async function saveTpl() {
    // Persist the reusable template (prose + volume tiers + list rate); the broker
    // name and client roster are per-deal inputs and stay out of the saved template.
    await saveTemplate<BookTemplate>('book', { blocks: blocks ?? [], discount_tiers: tiers, list_pepm: list, cover })
  }

  async function download() {
    setDownloading(true)
    setError(null)
    try {
      const safe = (brokerName.trim() || 'Broker').replace(/[^A-Za-z0-9]+/g, '_').replace(/^_|_$/g, '')
      await api.downloadPost('/admin/deal-flow/book-proposal', inputs, `${safe}_Matcha_Lite_Book_Pricing.pdf`)
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
          <Button onClick={download} disabled={downloading}>
            {downloading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Download className="mr-2 h-4 w-4" />}
            Download Book Pricing PDF
          </Button>
        </div>
      </div>

      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

      <div className="mt-5 grid grid-cols-1 gap-6 lg:grid-cols-[340px_1fr]">
        <div className="space-y-5">
          <Section title="Broker">
            <Input label="Broker name" value={brokerName} onChange={(e) => setBrokerName(e.target.value)} placeholder="Alliant" />
            <Input label="Lite list PEPM ($)" type="number" min={0} step="0.5" value={listPepm} onChange={(e) => setListPepm(e.target.value)} />
            <Input label="Proposal date" type="date" value={proposalDate} onChange={(e) => setProposalDate(e.target.value)} />
            <div className="rounded-lg border border-violet-500/30 bg-violet-500/5 px-3 py-2 text-xs text-zinc-300">
              <b className="text-zinc-100">{totalSeats.toLocaleString()}</b> committed seats &rarr;{' '}
              <b className="text-violet-200">{disc}% off</b> &rarr; <b className="text-zinc-100">${netPepm.toFixed(2)}</b> PEPM
            </div>
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
            <div className="border-t border-zinc-800 pt-3">
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-500">Design</p>
              <div className="grid grid-cols-2 gap-2">
                <SelectRow label="Title font" value={cover.title_font} onChange={(v) => updateCover({ title_font: v })} options={FONT_OPTS} />
                <SelectRow label="Background" value={cover.bg_style} onChange={(v) => updateCover({ bg_style: v })} options={BG_OPTS} />
              </div>
              <div className="mt-2 flex items-center gap-2">
                <label className="text-sm font-medium text-zinc-300">Accent color</label>
                <input type="color" value={cover.accent_color} onChange={(e) => updateCover({ accent_color: e.target.value })}
                  className="h-8 w-12 cursor-pointer rounded border border-zinc-700 bg-zinc-900" />
                <span className="text-xs text-zinc-500">{cover.accent_color}</span>
              </div>
            </div>
          </Section>

          <Section title="Volume discount tiers">
            <p className="text-xs text-zinc-500">Seat threshold and % are editable; pooled committed seats pick the rate. Leave the last tier's max blank for open-ended, or set a cap — seats beyond it are quoted on request.</p>
            <div className="grid grid-cols-[1fr_1fr_1fr_auto] items-center gap-x-2 gap-y-2 text-xs">
              <span className="font-medium text-zinc-500">Min seats</span>
              <span className="font-medium text-zinc-500">Max seats</span>
              <span className="font-medium text-zinc-500">Discount %</span>
              <span />
              {tiers.map((t, i) => (
                <FragmentTier key={i} tier={t} onChange={(patch) => updateTier(i, patch)} onRemove={() => removeTier(i)} />
              ))}
            </div>
            <button type="button" onClick={addTier}
              className="inline-flex items-center gap-1 text-xs font-medium text-violet-300 hover:text-violet-200">
              <Plus className="h-3.5 w-3.5" /> Add tier
            </button>
          </Section>

          <Section title="Client roster">
            <p className="text-xs text-zinc-500">The clients you are enrolling. Seats pool to set the book-wide rate.</p>
            <div className="space-y-2">
              {clients.map((c, i) => (
                <div key={i} className="flex items-center gap-2">
                  <input
                    value={c.name} placeholder="Client name"
                    onChange={(e) => updateClient(i, { name: e.target.value })}
                    className="min-w-0 flex-1 rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-100 focus:border-violet-500 focus:outline-none"
                  />
                  <input
                    type="number" min={0} value={c.seats} placeholder="Seats"
                    onChange={(e) => updateClient(i, { seats: e.target.value })}
                    className="w-20 rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-100 focus:border-violet-500 focus:outline-none"
                  />
                  <button type="button" onClick={() => removeClient(i)} className="text-zinc-500 hover:text-red-400" aria-label="Remove client">
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
            <button type="button" onClick={addClient}
              className="inline-flex items-center gap-1 text-xs font-medium text-violet-300 hover:text-violet-200">
              <Plus className="h-3.5 w-3.5" /> Add client
            </button>
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
              <iframe title="book preview" srcDoc={previewHtml} className="h-[80vh] w-full bg-white" />
            </div>
          ) : !blocks ? (
            <p className="flex items-center gap-2 text-sm text-zinc-500"><Loader2 className="h-4 w-4 animate-spin" /> Loading template…</p>
          ) : (
            <div className="space-y-3 rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
              <p className="text-xs text-zinc-500">Edit the one-pager copy. Tables fill from the inputs at left. Preview to see the styled packet.</p>
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

function CoverField({ label, k, cover, ph, onChange }: { label: string; k: keyof Cover; cover: Cover; ph: Cover; onChange: (patch: Partial<Cover>) => void }) {
  return <Input label={label} value={cover[k]} placeholder={ph[k]} onChange={(e) => onChange({ [k]: e.target.value })} />
}

function FragmentTier({ tier, onChange, onRemove }: { tier: DiscountTier; onChange: (patch: Partial<DiscountTier>) => void; onRemove: () => void }) {
  return (
    <>
      <input
        type="number" min={0} value={tier.min_seats}
        onChange={(e) => onChange({ min_seats: int(e.target.value, tier.min_seats) })}
        className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm text-zinc-100 focus:border-violet-500 focus:outline-none"
      />
      <input
        type="number" min={0} value={tier.max_seats ?? ''} placeholder="∞"
        onChange={(e) => onChange({ max_seats: e.target.value.trim() === '' ? null : int(e.target.value, tier.max_seats ?? 0) })}
        className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm text-zinc-100 focus:border-violet-500 focus:outline-none"
      />
      <input
        type="number" min={0} max={90} value={tier.discount_pct}
        onChange={(e) => onChange({ discount_pct: int(e.target.value, tier.discount_pct) })}
        className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm text-zinc-100 focus:border-violet-500 focus:outline-none"
      />
      <button type="button" onClick={onRemove} className="text-zinc-500 hover:text-red-400" aria-label="Remove tier">
        <X className="h-4 w-4" />
      </button>
    </>
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
      <input value={block.text} onChange={(e) => onChange({ text: e.target.value })}
        className={`w-full rounded-md border border-transparent bg-transparent px-2 py-1 text-zinc-100 hover:border-zinc-700 focus:border-violet-500 focus:outline-none ${size}`} />
    )
  }
  if (block.kind === 'bullets') {
    return <AutoTextarea value={block.items.join('\n')} onChange={(v) => onChange({ items: v.split('\n') })} className="text-sm text-zinc-300" placeholder="One per line" />
  }
  const cls = block.kind === 'note' ? 'text-xs italic text-zinc-400'
    : block.kind === 'callout' ? 'text-sm text-zinc-200 border-l-2 border-violet-500/50 pl-3'
    : 'text-sm text-zinc-300'
  return <AutoTextarea value={block.text} onChange={(v) => onChange({ text: v })} className={cls} />
}

function AutoTextarea({ value, onChange, className = '', placeholder }: { value: string; onChange: (v: string) => void; className?: string; placeholder?: string }) {
  const ref = useRef<HTMLTextAreaElement>(null)
  useEffect(() => { const el = ref.current; if (el) { el.style.height = 'auto'; el.style.height = `${el.scrollHeight}px` } }, [value])
  return (
    <textarea ref={ref} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} rows={1}
      className={`w-full resize-none rounded-md border border-transparent bg-transparent px-2 py-1 leading-relaxed hover:border-zinc-700 focus:border-violet-500 focus:outline-none ${className}`} />
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
