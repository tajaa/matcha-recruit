import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft, Check, ChevronDown, ChevronUp, GripVertical, ImagePlus, Loader2, Palette, Plus, Save, Sparkles, Trash2,
} from 'lucide-react'
import { cappeApi } from '../../../api/cappeClient'
import { CAPPE_THEMES, FONT_PAIRINGS, RADII, contrastText } from '../../../data/cappeThemes'
import type { CappeBlock, CappePage, CappeSite } from '../../../types/cappe'

// ── theme helpers (operate on the freeform theme_config object) ─────────────
const themeObj = (v: unknown): Record<string, unknown> =>
  v && typeof v === 'object' && !Array.isArray(v) ? { ...(v as Record<string, unknown>) } : {}
const themeColors = (t: Record<string, unknown>): Record<string, string> =>
  (t.colors && typeof t.colors === 'object' ? { ...(t.colors as Record<string, string>) } : {})
const themeFonts = (t: Record<string, unknown>): { heading?: string; body?: string } =>
  (t.fonts && typeof t.fonts === 'object' ? { ...(t.fonts as Record<string, string>) } : {})
// Match a font pairing id from a theme's current fonts (for the select value).
const fontPairId = (t: Record<string, unknown>): string => {
  const f = themeFonts(t)
  return FONT_PAIRINGS.find((p) => p.heading === (f.heading || 'Inter') && p.body === (f.body || 'Inter'))?.id || 'inter'
}

// ── value helpers (dynamic JSON, narrowed at the edges) ─────────────────────
const str = (v: unknown): string => (typeof v === 'string' ? v : '')
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : [])
const obj = (v: unknown): Record<string, unknown> =>
  v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {}
const isOn = (v: unknown): boolean => v === true

// ── field schema ────────────────────────────────────────────────────────────
type FieldKind = 'text' | 'textarea' | 'select' | 'bool' | 'image' | 'strlist' | 'list'
type Field = {
  key: string
  label: string
  kind: FieldKind
  placeholder?: string
  options?: { value: string; label: string }[]
  item?: Field[]            // for kind 'list'
  newItem?: () => Record<string, unknown>
  addLabel?: string
}

type BlockSchema = { label: string; fields: Field[]; make: () => CappeBlock }

const F = (key: string, label: string, kind: FieldKind = 'text', extra: Partial<Field> = {}): Field =>
  ({ key, label, kind, ...extra })

const BLOCK_SCHEMAS: Record<string, BlockSchema> = {
  hero: {
    label: 'Hero',
    make: () => ({ type: 'hero', heading: 'Your headline', subheading: 'A sentence of supporting copy.', cta: 'Get started', style: 'centered' }),
    fields: [
      F('eyebrow', 'Eyebrow (small label)'),
      F('heading', 'Heading'),
      F('subheading', 'Subheading', 'textarea'),
      F('style', 'Layout', 'select', { options: [
        { value: 'centered', label: 'Centered' }, { value: 'split', label: 'Split (with image)' },
        { value: 'image', label: 'Full image background' }, { value: 'minimal', label: 'Minimal' },
      ] }),
      F('image', 'Image (for split / image layout)', 'image'),
      F('align', 'Text align (image layout)', 'select', { options: [
        { value: 'center', label: 'Center' }, { value: 'left', label: 'Left' },
      ] }),
      F('overlay', 'Photo overlay (image layout)', 'select', { options: [
        { value: 'light', label: 'Light' }, { value: 'medium', label: 'Medium' }, { value: 'dark', label: 'Dark' },
      ] }),
      F('height', 'Height (image layout)', 'select', { options: [
        { value: 'tall', label: 'Tall' }, { value: 'full', label: 'Full screen' },
      ] }),
      F('cta', 'Button label'),
      F('ctaHref', 'Button link', 'text', { placeholder: '/p/contact or https://…' }),
      F('cta2', 'Second button label'),
      F('cta2Href', 'Second button link'),
    ],
  },
  features: {
    label: 'Features',
    make: () => ({ type: 'features', heading: 'What I do', items: [
      { icon: '✦', title: 'Feature one', body: 'Short description.' },
      { icon: '◆', title: 'Feature two', body: 'Short description.' },
      { icon: '▲', title: 'Feature three', body: 'Short description.' },
    ] }),
    fields: [
      F('heading', 'Section heading'),
      F('subheading', 'Section subheading', 'textarea'),
      F('items', 'Items', 'list', {
        addLabel: 'Add feature', newItem: () => ({ title: '', body: '' }),
        item: [F('icon', 'Icon / emoji'), F('title', 'Title'), F('body', 'Body', 'textarea')],
      }),
    ],
  },
  gallery: {
    label: 'Gallery',
    make: () => ({ type: 'gallery', heading: 'Gallery', images: [] }),
    fields: [
      F('heading', 'Section heading'),
      F('images', 'Images', 'list', {
        addLabel: 'Add image', newItem: () => ({ url: '' }),
        item: [F('url', 'Image', 'image'), F('caption', 'Caption')],
      }),
    ],
  },
  pricing: {
    label: 'Pricing',
    make: () => ({ type: 'pricing', heading: 'Pricing', plans: [
      { name: 'Basic', price: '$0', period: '/mo', features: ['Feature'], cta: 'Choose' },
    ] }),
    fields: [
      F('heading', 'Section heading'),
      F('plans', 'Plans', 'list', {
        addLabel: 'Add plan', newItem: () => ({ name: '', price: '', features: [] }),
        item: [
          F('name', 'Name'), F('price', 'Price', 'text', { placeholder: '$24' }),
          F('period', 'Period', 'text', { placeholder: '/mo' }),
          F('features', 'Features', 'strlist'),
          F('cta', 'Button label'), F('ctaHref', 'Button link'),
          F('highlighted', 'Highlight as popular', 'bool'),
        ],
      }),
    ],
  },
  testimonial: {
    label: 'Testimonials',
    make: () => ({ type: 'testimonial', items: [{ quote: '', author: '' }] }),
    fields: [
      F('heading', 'Section heading'),
      F('items', 'Quotes', 'list', {
        addLabel: 'Add quote', newItem: () => ({ quote: '', author: '' }),
        item: [F('quote', 'Quote', 'textarea'), F('author', 'Author'), F('role', 'Role / company')],
      }),
    ],
  },
  cta: {
    label: 'Call to action',
    make: () => ({ type: 'cta', heading: 'Ready to start?', cta: 'Get started' }),
    fields: [
      F('heading', 'Heading'), F('subheading', 'Subheading', 'textarea'),
      F('cta', 'Button label'), F('ctaHref', 'Button link'),
    ],
  },
  menu: {
    label: 'Menu',
    make: () => ({ type: 'menu', heading: 'Menu', sections: [{ name: 'Section', items: [{ name: '', price: '' }] }] }),
    fields: [
      F('heading', 'Section heading'),
      F('sections', 'Sections', 'list', {
        addLabel: 'Add section', newItem: () => ({ name: '', items: [] }),
        item: [
          F('name', 'Section name'),
          F('items', 'Items', 'list', {
            addLabel: 'Add item', newItem: () => ({ name: '', price: '' }),
            item: [F('name', 'Name'), F('description', 'Description'), F('price', 'Price')],
          }),
        ],
      }),
    ],
  },
  posts: {
    label: 'Post list',
    make: () => ({ type: 'posts', items: [{ title: '', excerpt: '' }] }),
    fields: [
      F('heading', 'Section heading'),
      F('items', 'Posts', 'list', {
        addLabel: 'Add post', newItem: () => ({ title: '', excerpt: '' }),
        item: [F('date', 'Date'), F('title', 'Title'), F('excerpt', 'Excerpt', 'textarea'), F('slug', 'Links to page slug')],
      }),
    ],
  },
  stats: {
    label: 'Stats band',
    make: () => ({ type: 'stats', items: [
      { value: '500+', label: 'Happy clients' },
      { value: '10 yrs', label: 'Experience' },
      { value: '98%', label: 'Would recommend' },
    ] }),
    fields: [
      F('heading', 'Section heading'), F('subheading', 'Section subheading', 'textarea'),
      F('items', 'Stats', 'list', {
        addLabel: 'Add stat', newItem: () => ({ value: '', label: '' }),
        item: [F('value', 'Number', 'text', { placeholder: '500+' }), F('label', 'Label')],
      }),
    ],
  },
  logos: {
    label: 'Logo cloud',
    make: () => ({ type: 'logos', heading: 'Trusted by', items: [{ name: 'Acme' }, { name: 'Globex' }, { name: 'Initech' }] }),
    fields: [
      F('heading', 'Eyebrow label', 'text', { placeholder: 'Trusted by' }),
      F('items', 'Logos', 'list', {
        addLabel: 'Add logo', newItem: () => ({ name: '' }),
        item: [F('name', 'Name (used if no image)'), F('image', 'Logo image', 'image')],
      }),
    ],
  },
  faq: {
    label: 'FAQ',
    make: () => ({ type: 'faq', heading: 'Frequently asked', items: [
      { q: 'How does it work?', a: 'Explain it here in a sentence or two.' },
    ] }),
    fields: [
      F('heading', 'Section heading'), F('subheading', 'Section subheading', 'textarea'),
      F('items', 'Questions', 'list', {
        addLabel: 'Add question', newItem: () => ({ q: '', a: '' }),
        item: [F('q', 'Question'), F('a', 'Answer', 'textarea')],
      }),
    ],
  },
  bento: {
    label: 'Bento grid',
    make: () => ({ type: 'bento', heading: 'Highlights', items: [
      { title: 'Big idea', body: 'Your standout point.', span: 'wide' },
      { title: 'Detail one', body: 'Supporting detail.' },
      { title: 'Detail two', body: 'Supporting detail.' },
    ] }),
    fields: [
      F('heading', 'Section heading'), F('subheading', 'Section subheading', 'textarea'),
      F('items', 'Cells', 'list', {
        addLabel: 'Add cell', newItem: () => ({ title: '', body: '' }),
        item: [
          F('icon', 'Icon / emoji'), F('title', 'Title'), F('body', 'Body', 'textarea'),
          F('image', 'Background image', 'image'),
          F('span', 'Size', 'select', { options: [
            { value: 'normal', label: 'Normal' }, { value: 'wide', label: 'Wide (full row)' },
            { value: 'tall', label: 'Tall' },
          ] }),
        ],
      }),
    ],
  },
  split: {
    label: 'Split feature',
    make: () => ({ type: 'split', heading: 'A focused feature', body: 'Describe one thing in depth, with an image alongside.', bullets: ['Benefit one', 'Benefit two'] }),
    fields: [
      F('eyebrow', 'Eyebrow (small label)'),
      F('heading', 'Heading'), F('body', 'Body', 'textarea'),
      F('image', 'Image', 'image'),
      F('bullets', 'Bullet points', 'strlist'),
      F('cta', 'Button label'), F('ctaHref', 'Button link'),
      F('reverse', 'Image on right', 'bool'),
    ],
  },
  credentials: {
    label: 'Certifications',
    make: () => ({ type: 'credentials', heading: 'Certifications & qualifications', items: [
      { title: 'Certified Personal Trainer', issuer: 'NASM', year: '2021' },
      { title: 'CPR & First Aid', issuer: 'Red Cross', year: '2024' },
    ] }),
    fields: [
      F('heading', 'Section heading'), F('subheading', 'Section subheading', 'textarea'),
      F('items', 'Credentials', 'list', {
        addLabel: 'Add credential', newItem: () => ({ title: '', issuer: '', year: '' }),
        item: [
          F('title', 'Title / certification'), F('issuer', 'Issuing body'),
          F('year', 'Year'), F('detail', 'Detail (optional)', 'textarea'),
        ],
      }),
    ],
  },
  text: {
    label: 'Text',
    make: () => ({ type: 'text', body: 'Write something here.' }),
    fields: [F('heading', 'Heading'), F('body', 'Body', 'textarea')],
  },
  contact: {
    label: 'Contact form',
    make: () => ({ type: 'contact', heading: 'Get in touch', fields: ['name', 'email', 'message'] }),
    fields: [
      F('heading', 'Heading'), F('subheading', 'Subheading', 'textarea'),
      F('fields', 'Form fields', 'strlist'),
      F('formSlug', 'Submit to form (slug)', 'text', { placeholder: 'contact — create it in the Forms tab' }),
    ],
  },
  store: {
    label: 'Store (products)',
    make: () => ({ type: 'store', heading: 'Shop' }),
    fields: [
      F('heading', 'Section heading'), F('subheading', 'Section subheading', 'textarea'),
    ],
  },
  booking: {
    label: 'Booking widget',
    make: () => ({ type: 'booking', heading: 'Book a session' }),
    fields: [
      F('heading', 'Section heading'), F('subheading', 'Section subheading', 'textarea'),
    ],
  },
  newsletter: {
    label: 'Newsletter signup',
    make: () => ({ type: 'newsletter', heading: 'Subscribe' }),
    fields: [
      F('heading', 'Section heading'), F('subheading', 'Section subheading', 'textarea'),
    ],
  },
}

const BLOCK_ORDER = ['hero', 'features', 'split', 'bento', 'stats', 'credentials', 'logos', 'gallery', 'pricing', 'testimonial', 'faq', 'cta', 'store', 'booking', 'menu', 'posts', 'text', 'contact', 'newsletter']

// ── upload context (only ImageInput needs the siteId) ───────────────────────
const SiteCtx = createContext<string>('')

const inputCls =
  'w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500'

// ── field inputs ─────────────────────────────────────────────────────────────
function ImageInput({ value, onChange }: { value: unknown; onChange: (v: string) => void }) {
  const siteId = useContext(SiteCtx)
  const [busy, setBusy] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const url = str(value)

  async function upload(file: File) {
    setBusy(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await cappeApi.upload<{ url: string }>(`/sites/${siteId}/upload`, fd)
      onChange(res.url)
    } catch {
      /* surfaced by empty url */
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex items-center gap-2">
      <input value={url} onChange={(e) => onChange(e.target.value)} placeholder="Image URL" className={inputCls} />
      {url && <img src={url} alt="" className="h-9 w-9 shrink-0 rounded object-cover" />}
      <button
        type="button"
        onClick={() => fileRef.current?.click()}
        disabled={busy}
        className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-zinc-700 px-2.5 py-2 text-xs font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-60"
      >
        {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ImagePlus className="h-3.5 w-3.5" />}
      </button>
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = '' }}
      />
    </div>
  )
}

function StringList({ value, onChange }: { value: unknown; onChange: (v: string[]) => void }) {
  const items = arr(value).map(str)
  const set = (i: number, v: string) => onChange(items.map((x, j) => (j === i ? v : x)))
  return (
    <div className="space-y-1.5">
      {items.map((v, i) => (
        <div key={i} className="flex gap-1.5">
          <input value={v} onChange={(e) => set(i, e.target.value)} className={inputCls} />
          <button type="button" onClick={() => onChange(items.filter((_, j) => j !== i))} className="px-2 text-zinc-500 hover:text-red-400">
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      ))}
      <button type="button" onClick={() => onChange([...items, ''])} className="text-xs font-medium text-emerald-400 hover:text-emerald-300">
        + Add
      </button>
    </div>
  )
}

function ListEditor({ field, value, onChange }: { field: Field; value: unknown; onChange: (v: unknown[]) => void }) {
  const rows = arr(value)
  const setRow = (i: number, row: Record<string, unknown>) => onChange(rows.map((r, j) => (j === i ? row : r)))
  const move = (i: number, dir: -1 | 1) => {
    const j = i + dir
    if (j < 0 || j >= rows.length) return
    const next = [...rows]
    ;[next[i], next[j]] = [next[j], next[i]]
    onChange(next)
  }
  return (
    <div className="space-y-3">
      {rows.map((r, i) => {
        const row = obj(r)
        return (
          <div key={i} className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
                {field.label.replace(/s$/, '')} {i + 1}
              </span>
              <div className="flex items-center gap-1 text-zinc-500">
                <button type="button" onClick={() => move(i, -1)} className="hover:text-zinc-200"><ChevronUp className="h-3.5 w-3.5" /></button>
                <button type="button" onClick={() => move(i, 1)} className="hover:text-zinc-200"><ChevronDown className="h-3.5 w-3.5" /></button>
                <button type="button" onClick={() => onChange(rows.filter((_, j) => j !== i))} className="hover:text-red-400"><Trash2 className="h-3.5 w-3.5" /></button>
              </div>
            </div>
            <div className="space-y-2.5">
              {(field.item || []).map((sf) => (
                <FieldInput key={sf.key} field={sf} value={row[sf.key]} onChange={(v) => setRow(i, { ...row, [sf.key]: v })} />
              ))}
            </div>
          </div>
        )
      })}
      <button
        type="button"
        onClick={() => onChange([...rows, field.newItem ? field.newItem() : {}])}
        className="inline-flex items-center gap-1 rounded-lg border border-dashed border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:border-emerald-500 hover:text-emerald-400"
      >
        <Plus className="h-3.5 w-3.5" /> {field.addLabel || 'Add'}
      </button>
    </div>
  )
}

function FieldInput({ field, value, onChange }: { field: Field; value: unknown; onChange: (v: unknown) => void }) {
  const label = (
    <label className="mb-1 block text-xs font-medium text-zinc-400">{field.label}</label>
  )
  if (field.kind === 'list') {
    return <div>{label}<ListEditor field={field} value={value} onChange={onChange} /></div>
  }
  if (field.kind === 'strlist') {
    return <div>{label}<StringList value={value} onChange={onChange} /></div>
  }
  if (field.kind === 'image') {
    return <div>{label}<ImageInput value={value} onChange={onChange} /></div>
  }
  if (field.kind === 'bool') {
    return (
      <label className="flex items-center gap-2 text-sm text-zinc-300">
        <input type="checkbox" checked={isOn(value)} onChange={(e) => onChange(e.target.checked)} className="h-4 w-4 rounded border-zinc-600 bg-zinc-900 text-emerald-500" />
        {field.label}
      </label>
    )
  }
  if (field.kind === 'select') {
    return (
      <div>{label}
        <select value={str(value)} onChange={(e) => onChange(e.target.value)} className={inputCls}>
          {(field.options || []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </div>
    )
  }
  if (field.kind === 'textarea') {
    return <div>{label}<textarea value={str(value)} onChange={(e) => onChange(e.target.value)} rows={3} placeholder={field.placeholder} className={inputCls} /></div>
  }
  return <div>{label}<input value={str(value)} onChange={(e) => onChange(e.target.value)} placeholder={field.placeholder} className={inputCls} /></div>
}

// ── block card ───────────────────────────────────────────────────────────────
function BlockCard({
  block, index, total, onChange, onRemove, onMove,
}: {
  block: CappeBlock; index: number; total: number
  onChange: (b: CappeBlock) => void
  onRemove: () => void
  onMove: (dir: -1 | 1) => void
}) {
  const [open, setOpen] = useState(true)
  const schema = BLOCK_SCHEMAS[block.type]
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900">
      <div className="flex items-center justify-between gap-2 border-b border-zinc-800 px-4 py-2.5">
        <button type="button" onClick={() => setOpen((o) => !o)} className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
          <GripVertical className="h-4 w-4 text-zinc-600" />
          {schema?.label || block.type}
        </button>
        <div className="flex items-center gap-1 text-zinc-500">
          <button type="button" onClick={() => onMove(-1)} disabled={index === 0} className="hover:text-zinc-200 disabled:opacity-30"><ChevronUp className="h-4 w-4" /></button>
          <button type="button" onClick={() => onMove(1)} disabled={index === total - 1} className="hover:text-zinc-200 disabled:opacity-30"><ChevronDown className="h-4 w-4" /></button>
          <button type="button" onClick={onRemove} className="hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
          <button type="button" onClick={() => setOpen((o) => !o)} className="hover:text-zinc-200">{open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}</button>
        </div>
      </div>
      {open && schema && (
        <div className="space-y-3 p-4">
          {schema.fields.map((f) => (
            <FieldInput key={f.key} field={f} value={block[f.key]} onChange={(v) => onChange({ ...block, [f.key]: v })} />
          ))}
        </div>
      )}
      {open && !schema && <div className="p-4 text-sm text-zinc-500">Unknown block type “{block.type}”.</div>}
    </div>
  )
}

// ── page editor ──────────────────────────────────────────────────────────────
export default function PageEditor() {
  const { siteId, pageId } = useParams<{ siteId: string; pageId: string }>()
  const navigate = useNavigate()

  const [page, setPage] = useState<CappePage | null>(null)
  const [title, setTitle] = useState('')
  const [status, setStatus] = useState<'draft' | 'published'>('draft')
  const [blocks, setBlocks] = useState<CappeBlock[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)

  const [preview, setPreview] = useState('')
  const previewSeq = useRef(0)

  // Live theme switching — edited locally, previewed instantly, saved on demand.
  const [theme, setTheme] = useState<Record<string, unknown>>({})
  const [themeDirty, setThemeDirty] = useState(false)
  const [themeOpen, setThemeOpen] = useState(false)

  useEffect(() => {
    if (!siteId || !pageId) return
    Promise.all([
      cappeApi.get<CappePage[]>(`/sites/${siteId}/pages`),
      cappeApi.get<CappeSite>(`/sites/${siteId}`).catch(() => null),
    ])
      .then(([pages, site]) => {
        const p = pages.find((x) => x.id === pageId)
        if (!p) { setError('Page not found'); return }
        setPage(p)
        setTitle(p.title)
        setStatus(p.status === 'published' ? 'published' : 'draft')
        const bs = (p.content?.blocks as CappeBlock[]) || []
        setBlocks(Array.isArray(bs) ? bs : [])
        setTheme(themeObj(site?.theme_config))
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load page'))
      .finally(() => setLoading(false))
  }, [siteId, pageId])

  // Debounced live preview of the current (unsaved) blocks + theme.
  useEffect(() => {
    if (!siteId || !page) return
    const seq = ++previewSeq.current
    const t = setTimeout(() => {
      cappeApi
        .postHtml(`/sites/${siteId}/preview`, { title, slug: page.slug, content: { blocks }, theme_config: theme })
        .then((html) => { if (seq === previewSeq.current) setPreview(html) })
        .catch(() => { /* keep last good preview */ })
    }, 400)
    return () => clearTimeout(t)
  }, [siteId, page, title, blocks, theme])

  // ── theme mutators ─────────────────────────────────────────────────────────
  const applyPreset = (id: string) => {
    const preset = CAPPE_THEMES.find((p) => p.id === id)
    if (!preset) return
    setTheme({ ...preset.config, preset: preset.id })
    setThemeDirty(true)
  }
  const setBrand = (hex: string) => {
    setTheme((t) => ({ ...t, colors: { ...themeColors(t), brand: hex, accent: hex, brandText: contrastText(hex) } }))
    setThemeDirty(true)
  }
  const setPairing = (id: string) => {
    const p = FONT_PAIRINGS.find((x) => x.id === id)
    if (!p) return
    setTheme((t) => ({ ...t, fonts: { heading: p.heading, body: p.body } }))
    setThemeDirty(true)
  }
  const setRadius = (v: string) => { setTheme((t) => ({ ...t, radius: v })); setThemeDirty(true) }
  const setMode = (m: 'light' | 'dark') => { setTheme((t) => ({ ...t, mode: m })); setThemeDirty(true) }

  const updateBlock = (i: number, b: CappeBlock) => setBlocks((bs) => bs.map((x, j) => (j === i ? b : x)))
  const removeBlock = (i: number) => setBlocks((bs) => bs.filter((_, j) => j !== i))
  const moveBlock = (i: number, dir: -1 | 1) =>
    setBlocks((bs) => {
      const j = i + dir
      if (j < 0 || j >= bs.length) return bs
      const next = [...bs]
      ;[next[i], next[j]] = [next[j], next[i]]
      return next
    })
  const addBlock = (type: string) => {
    setBlocks((bs) => [...bs, BLOCK_SCHEMAS[type].make()])
    setAdding(false)
  }

  async function save() {
    if (!siteId || !pageId) return
    setSaving(true)
    setError(null)
    setNotice(null)
    try {
      const updated = await cappeApi.put<CappePage>(`/sites/${siteId}/pages/${pageId}`, {
        title,
        status,
        content: { blocks },
      })
      setPage(updated)
      // Persist the theme to the site too, if it was changed here.
      if (themeDirty) {
        await cappeApi.put<CappeSite>(`/sites/${siteId}`, { theme_config: theme })
        setThemeDirty(false)
      }
      setNotice('Saved.')
      setTimeout(() => setNotice(null), 2000)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="flex min-h-screen items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>
  }
  if (!page) {
    return (
      <div className="mx-auto max-w-3xl px-8 py-10">
        <p className="text-sm text-red-400">{error || 'Page not found.'}</p>
        <Link to={`/cappe/sites/${siteId}`} className="mt-4 inline-flex items-center gap-1 text-sm text-emerald-400 hover:text-emerald-300">
          <ArrowLeft className="h-4 w-4" /> Back to site
        </Link>
      </div>
    )
  }

  return (
    <SiteCtx.Provider value={siteId || ''}>
      <div className="flex h-screen flex-col bg-zinc-950 text-zinc-100">
        {/* top bar */}
        <div className="flex items-center justify-between gap-4 border-b border-zinc-800 bg-zinc-900 px-6 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <button onClick={() => navigate(`/cappe/sites/${siteId}`)} className="text-zinc-500 hover:text-zinc-200"><ArrowLeft className="h-5 w-5" /></button>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="min-w-0 rounded-md border border-transparent bg-transparent px-2 py-1 text-lg font-semibold text-zinc-50 hover:border-zinc-700 focus:border-emerald-500 focus:outline-none"
            />
            <span className="shrink-0 text-xs text-zinc-500">/{page.slug}</span>
          </div>
          <div className="flex items-center gap-2">
            {notice && <span className="text-sm text-emerald-400">{notice}</span>}
            {error && <span className="text-sm text-red-400">{error}</span>}

            {/* Live theme switcher + tweaks */}
            <div className="relative">
              <button
                onClick={() => setThemeOpen((o) => !o)}
                className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium ${themeOpen ? 'border-emerald-500 text-emerald-400' : 'border-zinc-700 text-zinc-300 hover:bg-zinc-800'}`}
              >
                <Palette className="h-4 w-4" /> Theme{themeDirty && <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />}
              </button>
              {themeOpen && (
                <>
                  <div className="fixed inset-0 z-20" onClick={() => setThemeOpen(false)} />
                  <div className="absolute right-0 z-30 mt-1 max-h-[80vh] w-80 overflow-y-auto rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-2xl shadow-black/50">
                    <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Theme</p>
                    <div className="grid grid-cols-3 gap-1.5">
                      {CAPPE_THEMES.map((preset) => {
                        const active = theme.preset === preset.id
                        return (
                          <button
                            key={preset.id}
                            onClick={() => applyPreset(preset.id)}
                            className={`relative overflow-hidden rounded-lg border text-left ${active ? 'border-emerald-500 ring-1 ring-emerald-500' : 'border-zinc-700 hover:border-zinc-500'}`}
                            title={preset.name}
                          >
                            <div className="flex h-9 items-center gap-1 px-1.5" style={{ background: preset.swatch.bg }}>
                              <span className="h-4 w-4 rounded" style={{ background: preset.swatch.brand }} />
                              <span className="h-1.5 flex-1 rounded" style={{ background: preset.swatch.text, opacity: 0.7 }} />
                            </div>
                            <div className="flex items-center justify-between gap-0.5 bg-zinc-950 px-1.5 py-1">
                              <span className="truncate text-[10px] text-zinc-300">{preset.name.split(' ')[0]}</span>
                              {preset.premium ? <Sparkles className="h-2.5 w-2.5 text-amber-400" /> : active ? <Check className="h-2.5 w-2.5 text-emerald-400" /> : null}
                            </div>
                          </button>
                        )
                      })}
                    </div>

                    <div className="mt-3 space-y-2.5 border-t border-zinc-800 pt-3">
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Tweak</p>

                      <div className="flex items-center justify-between">
                        <span className="text-xs text-zinc-400">Brand color</span>
                        <input
                          type="color"
                          value={themeColors(theme).brand || ((theme.mode as string) === 'dark' ? '#a3e635' : '#10b981')}
                          onChange={(e) => setBrand(e.target.value)}
                          className="h-7 w-12 cursor-pointer rounded border border-zinc-700 bg-transparent"
                        />
                      </div>

                      <div className="flex items-center justify-between gap-2">
                        <span className="shrink-0 text-xs text-zinc-400">Fonts</span>
                        <select value={fontPairId(theme)} onChange={(e) => setPairing(e.target.value)} className={`${inputCls} py-1.5`}>
                          {FONT_PAIRINGS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                        </select>
                      </div>

                      <div className="flex items-center justify-between gap-2">
                        <span className="shrink-0 text-xs text-zinc-400">Corners</span>
                        <select value={(theme.radius as string) || 'lg'} onChange={(e) => setRadius(e.target.value)} className={`${inputCls} py-1.5`}>
                          {RADII.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                        </select>
                      </div>

                      <div className="flex items-center justify-between">
                        <span className="text-xs text-zinc-400">Mode</span>
                        <div className="flex rounded-lg border border-zinc-700 p-0.5">
                          {(['light', 'dark'] as const).map((m) => (
                            <button key={m} onClick={() => setMode(m)} className={`rounded-md px-2.5 py-0.5 text-xs font-medium capitalize ${((theme.mode as string) || 'light') === m ? 'bg-emerald-500 text-zinc-950' : 'text-zinc-400 hover:text-zinc-200'}`}>{m}</button>
                          ))}
                        </div>
                      </div>
                    </div>
                    <p className="mt-3 text-[11px] text-zinc-500">Preview updates live. <span className="text-zinc-300">Save</span> to publish the look.</p>
                  </div>
                </>
              )}
            </div>

            <select value={status} onChange={(e) => setStatus(e.target.value as 'draft' | 'published')} className="rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-100">
              <option value="draft">Draft</option>
              <option value="published">Published</option>
            </select>
            <button onClick={save} disabled={saving} className="flex items-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60">
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Save
            </button>
          </div>
        </div>

        {/* split: editor | live preview */}
        <div className="flex min-h-0 flex-1">
          <div className="w-full overflow-y-auto border-r border-zinc-800 bg-zinc-950 p-5 lg:w-[46%]">
            <div className="space-y-3">
              {blocks.map((b, i) => (
                <BlockCard
                  key={i}
                  block={b}
                  index={i}
                  total={blocks.length}
                  onChange={(nb) => updateBlock(i, nb)}
                  onRemove={() => removeBlock(i)}
                  onMove={(dir) => moveBlock(i, dir)}
                />
              ))}
              {blocks.length === 0 && (
                <p className="rounded-xl border border-dashed border-zinc-700 p-6 text-center text-sm text-zinc-500">
                  No blocks yet. Add one below to start building this page.
                </p>
              )}

              {/* add block */}
              <div className="relative">
                <button
                  onClick={() => setAdding((a) => !a)}
                  className="flex w-full items-center justify-center gap-2 rounded-xl border-2 border-dashed border-zinc-700 py-3 text-sm font-semibold text-zinc-400 hover:border-emerald-500 hover:text-emerald-400"
                >
                  <Plus className="h-4 w-4" /> Add block
                </button>
                {adding && (
                  <div className="absolute z-10 mt-1 grid w-full grid-cols-2 gap-1 rounded-xl border border-zinc-700 bg-zinc-900 p-2 shadow-xl shadow-black/40">
                    {BLOCK_ORDER.map((t) => (
                      <button key={t} onClick={() => addBlock(t)} className="rounded-lg px-3 py-2 text-left text-sm text-zinc-300 hover:bg-emerald-500/10 hover:text-emerald-400">
                        {BLOCK_SCHEMAS[t].label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* preview */}
          <div className="hidden flex-1 bg-zinc-900 lg:block">
            {preview ? (
              <iframe title="Live preview" srcDoc={preview} sandbox="allow-scripts" className="h-full w-full border-0" />
            ) : (
              <div className="flex h-full items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-zinc-600" /></div>
            )}
          </div>
        </div>
      </div>
    </SiteCtx.Provider>
  )
}
