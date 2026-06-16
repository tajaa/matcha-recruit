import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft, Check, ChevronDown, ChevronUp, Copy, Film, GripVertical, ImagePlus, Loader2, Megaphone, MousePointerClick, Palette, Pencil, Plus, Save, Search, Sparkles, Trash2, Wand2, X,
} from 'lucide-react'
import { cappeApi } from '../../../api/cappeClient'
import { useCappeMe } from '../../../hooks/useCappeMe'
import { BODY_FONTS, CAPPE_THEMES, FONT_CATEGORY, FONT_PAIRINGS, HEADING_FONTS, RADII, contrastText } from '../../../data/cappeThemes'
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
type FieldKind = 'text' | 'textarea' | 'select' | 'bool' | 'image' | 'video' | 'strlist' | 'list'
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
      F('image', 'Hero photo — adds a full-bleed background', 'image'),
      F('video', 'Hero video — premium, autoplay full-bleed background', 'video'),
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
  reviews: {
    label: 'Reviews',
    make: () => ({ type: 'reviews', heading: 'What clients say', allowSubmissions: true }),
    fields: [
      F('heading', 'Section heading'), F('subheading', 'Section subheading', 'textarea'),
      F('allowSubmissions', 'Let visitors leave a review', 'bool'),
    ],
  },
  map: {
    label: 'Map / Find us',
    make: () => ({ type: 'map', heading: 'Find us' }),
    fields: [
      F('heading', 'Section heading'),
      F('address', 'Address', 'text', { placeholder: 'Defaults to your business address in Settings' }),
      F('lat', 'Latitude (optional — adds a map)', 'text', { placeholder: 'e.g. 37.7749' }),
      F('lng', 'Longitude (optional)', 'text', { placeholder: 'e.g. -122.4194' }),
    ],
  },
  hours: {
    label: 'Opening hours',
    make: () => ({ type: 'hours', heading: 'Hours' }),
    fields: [F('heading', 'Section heading'), F('subheading', 'Subheading', 'textarea')],
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

const BLOCK_ORDER = ['hero', 'features', 'split', 'bento', 'stats', 'credentials', 'logos', 'gallery', 'pricing', 'testimonial', 'reviews', 'faq', 'cta', 'store', 'booking', 'menu', 'hours', 'map', 'posts', 'text', 'contact', 'newsletter']

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

function VideoInput({ value, onChange }: { value: unknown; onChange: (v: string) => void }) {
  const siteId = useContext(SiteCtx)
  const { account } = useCappeMe()
  const premium = account?.plan === 'pro' || account?.plan === 'business'
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const url = str(value)

  async function upload(file: File) {
    setBusy(true)
    setErr(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await cappeApi.upload<{ url: string }>(`/sites/${siteId}/upload-video`, fd)
      onChange(res.url)
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setBusy(false)
    }
  }

  if (!premium) {
    return (
      <div className="rounded-lg border border-dashed border-amber-700/40 bg-amber-500/[0.06] px-3 py-2.5 text-xs text-amber-300/90">
        <span className="font-medium">Premium feature.</span> Upgrade to Pro to add an autoplay background video to your hero.
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center gap-2">
        <input value={url} onChange={(e) => onChange(e.target.value)} placeholder="Video URL (MP4 / WebM)" className={inputCls} />
        {url && <video src={url} muted playsInline className="h-9 w-14 shrink-0 rounded object-cover" />}
        {url && (
          <button type="button" onClick={() => onChange('')} className="shrink-0 text-zinc-500 hover:text-red-400" title="Clear">
            <Trash2 className="h-4 w-4" />
          </button>
        )}
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          disabled={busy}
          className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-zinc-700 px-2.5 py-2 text-xs font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-60"
        >
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Film className="h-3.5 w-3.5" />}
        </button>
      </div>
      {err && <p className="mt-1 text-xs text-red-400">{err}</p>}
      <p className="mt-1 text-[11px] text-zinc-500">Short, muted loop works best (MP4/WebM, max 50 MB). Set a Hero photo above to use as the poster.</p>
      <input
        ref={fileRef}
        type="file"
        accept="video/mp4,video/webm,video/quicktime"
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
  if (field.kind === 'video') {
    return <div>{label}<VideoInput value={value} onChange={onChange} /></div>
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

// ── premium designer (per-block `_design` + global studio) ───────────────────
function usePremium(): boolean {
  const { account } = useCappeMe()
  return account?.plan === 'pro' || account?.plan === 'business'
}

// Canvas (click-on-page) mode is the top-tier flagship — Business only.
function useBusinessTier(): boolean {
  const { account } = useCappeMe()
  return account?.plan === 'business'
}

function PremiumLock({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-amber-700/40 bg-amber-500/[0.06] px-3 py-2.5 text-xs text-amber-300/90">
      <span className="font-medium">Premium feature.</span> {children}
    </div>
  )
}

const dLabel = 'mb-1 block text-[11px] font-medium text-zinc-500'
const dHead = 'text-[11px] font-semibold uppercase tracking-wide text-zinc-500'

function DSelect({ label, value, options, onChange }: {
  label: string; value: string; options: [string, string][]; onChange: (v: string) => void
}) {
  return (
    <label className="block">
      <span className={dLabel}>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} className={`${inputCls} py-1.5`}>
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </label>
  )
}

function DNum({ label, value, onChange, min, max, step }: {
  label: string; value: number; onChange: (v: number) => void; min: number; max: number; step?: number
}) {
  return (
    <label className="block">
      <span className={dLabel}>{label}</span>
      <input type="number" value={value} min={min} max={max} step={step ?? 1}
        onChange={(e) => onChange(Number(e.target.value))} className={`${inputCls} py-1.5`} />
    </label>
  )
}

function DCheck({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 text-xs text-zinc-300">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)}
        className="h-3.5 w-3.5 rounded border-zinc-600 bg-zinc-900 text-emerald-500" />
      {label}
    </label>
  )
}

function DColor({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-xs text-zinc-400">{label}</span>
      <div className="flex items-center gap-1">
        <input type="color" value={value || '#000000'} onChange={(e) => onChange(e.target.value)}
          className="h-7 w-10 cursor-pointer rounded border border-zinc-700 bg-transparent" />
        {value && <button type="button" onClick={() => onChange('')} className="text-zinc-500 hover:text-red-400" title="Clear"><Trash2 className="h-3.5 w-3.5" /></button>}
      </div>
    </div>
  )
}

function GradientPicker({ value, onChange }: { value: Record<string, unknown>; onChange: (g: Record<string, unknown>) => void }) {
  const stops = arr(value.stops).map(str)
  const s0 = stops[0] || '#10b981', s1 = stops[1] || '#a3e635'
  const setStop = (i: number, v: string) => { const next = [s0, s1]; next[i] = v; onChange({ ...value, stops: next }) }
  return (
    <div className="space-y-1.5">
      <div className="grid grid-cols-2 gap-2">
        <label className="block"><span className={dLabel}>From</span>
          <input type="color" value={s0} onChange={(e) => setStop(0, e.target.value)} className="h-8 w-full cursor-pointer rounded border border-zinc-700 bg-transparent" /></label>
        <label className="block"><span className={dLabel}>To</span>
          <input type="color" value={s1} onChange={(e) => setStop(1, e.target.value)} className="h-8 w-full cursor-pointer rounded border border-zinc-700 bg-transparent" /></label>
      </div>
      <DNum label="Angle (°)" value={Number(value.angle) || 135} min={0} max={360} step={5} onChange={(v) => onChange({ ...value, angle: v })} />
    </div>
  )
}

// ── promos panel (site-wide announcement bar + pop-up) ───────────────────────
function PInput({ label, value, onChange, ph, area }: {
  label: string; value: unknown; onChange: (v: string) => void; ph?: string; area?: boolean
}) {
  return (
    <label className="block"><span className={dLabel}>{label}</span>
      {area
        ? <textarea value={str(value)} onChange={(e) => onChange(e.target.value)} rows={2} placeholder={ph} className={`${inputCls} py-1.5`} />
        : <input value={str(value)} onChange={(e) => onChange(e.target.value)} placeholder={ph} className={`${inputCls} py-1.5`} />}
    </label>
  )
}

/** Site-wide promotions editor: an announcement bar + a pop-up modal stored on
 *  the site's meta_config.promos. Pro/Business only. Previews live; saved on the
 *  page editor's Save. */
function PromosPanel({ meta, premium, onChange, dirty }: {
  meta: Record<string, unknown>
  premium: boolean
  onChange: (m: Record<string, unknown>) => void
  dirty: boolean
}) {
  const [open, setOpen] = useState(false)
  const promos = obj(meta.promos)
  const bar = obj(promos.bar)
  const popup = obj(promos.popup)
  const patch = (group: 'bar' | 'popup', key: string, value: unknown) =>
    onChange({ ...meta, promos: { ...promos, [group]: { ...obj(promos[group]), [key]: value } } })
  const popMode = str(popup.mode) || 'newsletter'
  const popTrigger = str(popup.trigger) || 'load'

  return (
    <div className="relative">
      <button onClick={() => setOpen((o) => !o)}
        className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium ${open ? 'border-emerald-500 text-emerald-400' : 'border-zinc-700 text-zinc-300 hover:bg-zinc-800'}`}>
        <Megaphone className="h-4 w-4" /> Promos{dirty && <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-20" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-30 mt-1 max-h-[80vh] w-80 overflow-y-auto rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-2xl shadow-black/50">
            {!premium ? (
              <PremiumLock>Upgrade to Pro to add sale banners &amp; pop-ups that grow your list.</PremiumLock>
            ) : (
              <>
                {/* Announcement bar */}
                <section className="space-y-2.5">
                  <div className="flex items-center justify-between">
                    <p className={dHead}>Announcement bar</p>
                    <DCheck label="On" checked={isOn(bar.enabled)} onChange={(v) => patch('bar', 'enabled', v)} />
                  </div>
                  {isOn(bar.enabled) && (
                    <>
                      <PInput label="Message" value={bar.text} onChange={(v) => patch('bar', 'text', v)} ph="Summer sale — 20% off everything" />
                      <div className="grid grid-cols-2 gap-2">
                        <PInput label="Button label" value={bar.ctaLabel} onChange={(v) => patch('bar', 'ctaLabel', v)} ph="Shop now" />
                        <PInput label="Button link" value={bar.ctaHref} onChange={(v) => patch('bar', 'ctaHref', v)} ph="/p/shop" />
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <DSelect label="Position" value={str(bar.position) || 'top'} onChange={(v) => patch('bar', 'position', v)} options={[['top', 'Top'], ['bottom', 'Bottom (sticky)']]} />
                        <div className="flex items-end pb-1"><DCheck label="Dismissible" checked={isOn(bar.dismissible)} onChange={(v) => patch('bar', 'dismissible', v)} /></div>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <DColor label="Background" value={str(bar.bg)} onChange={(v) => patch('bar', 'bg', v)} />
                        <DColor label="Text" value={str(bar.color)} onChange={(v) => patch('bar', 'color', v)} />
                      </div>
                    </>
                  )}
                </section>

                {/* Pop-up modal */}
                <section className="mt-3 space-y-2.5 border-t border-zinc-800 pt-3">
                  <div className="flex items-center justify-between">
                    <p className={dHead}>Pop-up</p>
                    <DCheck label="On" checked={isOn(popup.enabled)} onChange={(v) => patch('popup', 'enabled', v)} />
                  </div>
                  {isOn(popup.enabled) && (
                    <>
                      <div className="grid grid-cols-2 gap-2">
                        <DSelect label="Show on" value={popTrigger} onChange={(v) => patch('popup', 'trigger', v)} options={[['load', 'Page load'], ['delay', 'After delay'], ['exit', 'Exit intent']]} />
                        {popTrigger === 'delay'
                          ? <DNum label="Delay (sec)" value={Number(popup.delaySec) || 5} min={0} max={120} onChange={(v) => patch('popup', 'delaySec', v)} />
                          : <DSelect label="Frequency" value={str(popup.frequency) || 'session'} onChange={(v) => patch('popup', 'frequency', v)} options={[['session', 'Once / visit'], ['once', 'Once ever'], ['always', 'Every load']]} />}
                      </div>
                      {popTrigger === 'delay' && (
                        <DSelect label="Frequency" value={str(popup.frequency) || 'session'} onChange={(v) => patch('popup', 'frequency', v)} options={[['session', 'Once / visit'], ['once', 'Once ever'], ['always', 'Every load']]} />
                      )}
                      <DSelect label="Goal" value={popMode} onChange={(v) => patch('popup', 'mode', v)} options={[['newsletter', 'Collect emails'], ['code', 'Show discount code'], ['cta', 'Call to action']]} />
                      <PInput label="Heading" value={popup.heading} onChange={(v) => patch('popup', 'heading', v)} ph="Get 10% off your first order" />
                      <PInput label="Body" value={popup.body} onChange={(v) => patch('popup', 'body', v)} ph="Join our list for early drops & deals." area />
                      <div><span className={dLabel}>Image (optional)</span><ImageInput value={popup.image} onChange={(v) => patch('popup', 'image', v)} /></div>
                      {popMode === 'newsletter' && <PInput label="Button label" value={popup.ctaLabel} onChange={(v) => patch('popup', 'ctaLabel', v)} ph="Subscribe" />}
                      {popMode === 'code' && (
                        <div className="grid grid-cols-2 gap-2">
                          <PInput label="Discount code" value={popup.code} onChange={(v) => patch('popup', 'code', v)} ph="WELCOME10" />
                          <PInput label="Button label" value={popup.ctaLabel} onChange={(v) => patch('popup', 'ctaLabel', v)} ph="Shop now" />
                        </div>
                      )}
                      {popMode === 'cta' && (
                        <div className="grid grid-cols-2 gap-2">
                          <PInput label="Button label" value={popup.ctaLabel} onChange={(v) => patch('popup', 'ctaLabel', v)} ph="Learn more" />
                          <PInput label="Button link" value={popup.ctaHref} onChange={(v) => patch('popup', 'ctaHref', v)} ph="/p/about" />
                        </div>
                      )}
                      {popMode === 'code' && (
                        <PInput label="Button link" value={popup.ctaHref} onChange={(v) => patch('popup', 'ctaHref', v)} ph="/p/shop" />
                      )}
                      <DColor label="Card background" value={str(popup.bg)} onChange={(v) => patch('popup', 'bg', v)} />
                    </>
                  )}
                </section>
                <p className="mt-3 text-[11px] text-zinc-500">Previews live (switch to Form preview to see the pop-up). <span className="text-zinc-300">Save</span> to publish.</p>
              </>
            )}
          </div>
        </>
      )}
    </div>
  )
}

// Lazy-load every catalog family (one Google Fonts request) so the picker can
// render each option in its own typeface. Injected once, on first open.
const FONT_CATS: ('Sans' | 'Serif' | 'Display' | 'Mono' | 'Handwriting')[] = ['Sans', 'Serif', 'Display', 'Mono', 'Handwriting']
function ensureFontPreviewCss() {
  const id = 'cz-fontpreview'
  if (document.getElementById(id)) return
  const parts = HEADING_FONTS.map((f) => `family=${encodeURIComponent(f)}:wght@500;700`).join('&')
  const link = document.createElement('link')
  link.id = id
  link.rel = 'stylesheet'
  link.href = `https://fonts.googleapis.com/css2?${parts}&display=swap`
  document.head.appendChild(link)
}

/** Searchable font picker — renders each option in its own typeface, grouped by
 *  category. `bodyOnly` narrows to body-readable families. */
function CappeFontPicker({ label, value, onChange, bodyOnly }: {
  label: string; value: string; onChange: (v: string) => void; bodyOnly?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const list = bodyOnly ? BODY_FONTS : HEADING_FONTS
  useEffect(() => { if (open) ensureFontPreviewCss() }, [open])
  const filtered = list.filter((n) => n.toLowerCase().includes(q.trim().toLowerCase()))
  return (
    <div className="relative">
      <span className={dLabel}>{label}</span>
      <button type="button" onClick={() => setOpen((o) => !o)}
        className={`${inputCls} flex items-center justify-between py-1.5`} style={{ fontFamily: `'${value}', sans-serif` }}>
        <span className="truncate">{value || 'Choose font'}</span>
        <ChevronDown className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-20" onClick={() => { setOpen(false); setQ('') }} />
          <div className="absolute z-30 mt-1 max-h-72 w-full overflow-y-auto rounded-lg border border-zinc-700 bg-zinc-900 p-1.5 shadow-xl shadow-black/40">
            <div className="relative mb-1">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500" />
              <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search fonts…" className={`${inputCls} py-1.5 pl-7`} />
            </div>
            {FONT_CATS.map((cat) => {
              const items = filtered.filter((n) => FONT_CATEGORY[n] === cat)
              if (!items.length) return null
              return (
                <div key={cat}>
                  <p className="px-2 pb-0.5 pt-1.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-500">{cat}</p>
                  {items.map((n) => (
                    <button key={n} type="button" onClick={() => { onChange(n); setOpen(false); setQ('') }}
                      className={`flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-sm hover:bg-emerald-500/10 ${n === value ? 'text-emerald-400' : 'text-zinc-200'}`}
                      style={{ fontFamily: `'${n}', sans-serif` }}>
                      <span className="truncate">{n}</span>
                      {n === value && <Check className="h-3.5 w-3.5 shrink-0" />}
                    </button>
                  ))}
                </div>
              )
            })}
            {!filtered.length && <p className="px-2 py-3 text-center text-xs text-zinc-500">No fonts match.</p>}
          </div>
        </>
      )}
    </div>
  )
}

/** Per-block design inspector — motion, background, layout & section colors.
 *  Writes a nested `_design` object on the block. Pro/Business only. */
function DesignInspector({ design, onChange }: { design: unknown; onChange: (d: Record<string, unknown>) => void }) {
  const premium = usePremium()
  const [open, setOpen] = useState(false)
  const d = obj(design)
  const motion = obj(d.motion), bg = obj(d.bg), layout = obj(d.layout), colors = obj(d.colors)
  const fx = str(motion.effect) || 'none'
  const hover = str(motion.hover) || 'none'
  const loop = str(motion.loop) || 'none'
  const headingFx = str(motion.heading) || 'none'
  const bgType = str(bg.type) || 'none'
  const patch = (group: string, key: string, value: unknown) =>
    onChange({ ...d, [group]: { ...obj(d[group]), [key]: value } })
  const padOpts: [string, string][] = [['default', 'Default'], ['none', 'None'], ['sm', 'Small'], ['lg', 'Large'], ['xl', 'XL']]

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/40">
      <button type="button" onClick={() => setOpen((o) => !o)} className="flex w-full items-center justify-between px-3 py-2 text-xs font-semibold text-zinc-300 hover:text-zinc-100">
        <span className="flex items-center gap-1.5"><Wand2 className="h-3.5 w-3.5 text-amber-400" /> Design</span>
        {open ? <ChevronUp className="h-3.5 w-3.5 text-zinc-500" /> : <ChevronDown className="h-3.5 w-3.5 text-zinc-500" />}
      </button>
      {open && (
        <div className="space-y-4 border-t border-zinc-800 p-3">
          {!premium ? (
            <PremiumLock>Upgrade to Pro to unlock motion, backgrounds, and advanced styling.</PremiumLock>
          ) : (
            <>
              <section className="space-y-2">
                <p className={dHead}>Motion</p>
                <DSelect label="Reveal on scroll" value={fx} onChange={(v) => patch('motion', 'effect', v)} options={[['none', 'None'], ['fade', 'Fade'], ['slide-up', 'Slide up'], ['slide-down', 'Slide down'], ['slide-left', 'Slide left'], ['slide-right', 'Slide right'], ['zoom', 'Zoom'], ['blur-in', 'Blur in'], ['flip', 'Flip'], ['rotate', 'Rotate in'], ['mask-up', 'Mask up'], ['bounce', 'Bounce']]} />
                {fx !== 'none' && (
                  <div className="grid grid-cols-2 gap-2">
                    <DNum label="Delay (ms)" value={Number(motion.delay) || 0} min={0} max={2000} step={50} onChange={(v) => patch('motion', 'delay', v)} />
                    <DNum label="Duration (ms)" value={Number(motion.duration) || 700} min={100} max={2000} step={50} onChange={(v) => patch('motion', 'duration', v)} />
                  </div>
                )}
                <div className="grid grid-cols-2 gap-2">
                  <DSelect label="Hover effect" value={hover} onChange={(v) => patch('motion', 'hover', v)} options={[['none', 'None'], ['lift', 'Lift'], ['tilt', 'Tilt 3D'], ['glow', 'Glow']]} />
                  <DSelect label="Continuous loop" value={loop} onChange={(v) => patch('motion', 'loop', v)} options={[['none', 'None'], ['float', 'Float'], ['pulse', 'Pulse']]} />
                </div>
                <DSelect label="Heading animation" value={headingFx} onChange={(v) => patch('motion', 'heading', v)} options={[['none', 'None'], ['rise', 'Rise in'], ['shimmer', 'Shimmer']]} />
                <div className="flex flex-wrap gap-x-4 gap-y-1.5">
                  <DCheck label="Stagger children" checked={isOn(motion.stagger)} onChange={(v) => patch('motion', 'stagger', v)} />
                  <DCheck label="Parallax" checked={isOn(motion.parallax)} onChange={(v) => patch('motion', 'parallax', v)} />
                  <DCheck label="Ken Burns" checked={isOn(motion.kenburns)} onChange={(v) => patch('motion', 'kenburns', v)} />
                </div>
                {isOn(motion.parallax) && <DNum label="Parallax strength" value={Number(motion.parallaxStrength) || 20} min={0} max={80} step={5} onChange={(v) => patch('motion', 'parallaxStrength', v)} />}
              </section>

              <section className="space-y-2">
                <p className={dHead}>Background</p>
                <DSelect label="Type" value={bgType} onChange={(v) => patch('bg', 'type', v)} options={[['none', 'None'], ['color', 'Solid color'], ['gradient', 'Gradient'], ['image', 'Image'], ['video', 'Video']]} />
                {bgType === 'color' && <DColor label="Color" value={str(bg.color)} onChange={(v) => patch('bg', 'color', v)} />}
                {bgType === 'gradient' && <GradientPicker value={obj(bg.gradient)} onChange={(g) => patch('bg', 'gradient', g)} />}
                {bgType === 'image' && <div><span className={dLabel}>Image</span><ImageInput value={bg.image} onChange={(v) => patch('bg', 'image', v)} /></div>}
                {bgType === 'video' && <div><span className={dLabel}>Video</span><VideoInput value={bg.video} onChange={(v) => patch('bg', 'video', v)} /></div>}
                {(bgType === 'image' || bgType === 'video') && (
                  <div className="grid grid-cols-2 gap-2">
                    <DSelect label="Overlay" value={str(bg.overlay) || 'none'} onChange={(v) => patch('bg', 'overlay', v)} options={[['none', 'None'], ['light', 'Light'], ['medium', 'Medium'], ['dark', 'Dark']]} />
                    <DNum label="Blur (px)" value={Number(bg.blur) || 0} min={0} max={40} onChange={(v) => patch('bg', 'blur', v)} />
                  </div>
                )}
              </section>

              <section className="space-y-2">
                <p className={dHead}>Layout</p>
                <div className="grid grid-cols-2 gap-2">
                  <DSelect label="Padding top" value={str(layout.padTop) || 'default'} onChange={(v) => patch('layout', 'padTop', v)} options={padOpts} />
                  <DSelect label="Padding bottom" value={str(layout.padBottom) || 'default'} onChange={(v) => patch('layout', 'padBottom', v)} options={padOpts} />
                  <DSelect label="Content width" value={str(layout.maxWidth) || 'default'} onChange={(v) => patch('layout', 'maxWidth', v)} options={[['default', 'Default'], ['narrow', 'Narrow'], ['wide', 'Wide'], ['full', 'Full bleed']]} />
                  <DSelect label="Min height" value={str(layout.minHeight) || 'default'} onChange={(v) => patch('layout', 'minHeight', v)} options={[['default', 'Default'], ['tall', 'Tall'], ['screen', 'Full screen']]} />
                </div>
                <DSelect label="Align" value={str(layout.align) || 'default'} onChange={(v) => patch('layout', 'align', v)} options={[['default', 'Default'], ['left', 'Left'], ['center', 'Center']]} />
              </section>

              <section className="space-y-1.5">
                <p className={dHead}>Colors (this section)</p>
                <DColor label="Text" value={str(colors.text)} onChange={(v) => patch('colors', 'text', v)} />
                <DColor label="Headings" value={str(colors.heading)} onChange={(v) => patch('colors', 'heading', v)} />
                <DColor label="Accent" value={str(colors.accent)} onChange={(v) => patch('colors', 'accent', v)} />
              </section>
            </>
          )}
        </div>
      )}
    </div>
  )
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
          <DesignInspector design={block._design} onChange={(dz) => onChange({ ...block, _design: dz })} />
        </div>
      )}
      {open && !schema && <div className="p-4 text-sm text-zinc-500">Unknown block type “{block.type}”.</div>}
    </div>
  )
}

// ── canvas mode: block-type palette + contextual panel ───────────────────────
function AddPalette({ onPick }: { onPick: (type: string) => void }) {
  return (
    <div className="absolute z-20 mt-1 grid w-full grid-cols-2 gap-1 rounded-xl border border-zinc-700 bg-zinc-900 p-2 shadow-xl shadow-black/40">
      {BLOCK_ORDER.map((t) => (
        <button key={t} onClick={() => onPick(t)} className="rounded-lg px-3 py-2 text-left text-sm text-zinc-300 hover:bg-emerald-500/10 hover:text-emerald-400">
          {BLOCK_SCHEMAS[t].label}
        </button>
      ))}
    </div>
  )
}

/** Contextual editor for the block selected on the canvas. Same controls as the
 *  form editor (schema fields + DesignInspector), driven by selection. */
function CanvasPanel({ blocks, sel, onChange, onMove, onRemove, onDuplicate, onAddAt, onAdd, onClose }: {
  blocks: CappeBlock[]
  sel: number | null
  onChange: (i: number, b: CappeBlock) => void
  onMove: (i: number, dir: -1 | 1) => void
  onRemove: (i: number) => void
  onDuplicate: (i: number) => void
  onAddAt: (type: string, i: number) => void
  onAdd: (type: string) => void
  onClose?: () => void
}) {
  const [addOpen, setAddOpen] = useState(false)
  // Close the palette whenever the selection changes.
  useEffect(() => { setAddOpen(false) }, [sel])

  if (sel == null || !blocks[sel]) {
    return (
      <div className="p-4">
        <p className="rounded-lg border border-dashed border-zinc-700 p-4 text-center text-xs text-zinc-500">
          Click any section on the canvas to edit it. Double-click text to type in place.
        </p>
        <div className="relative mt-3">
          <button onClick={() => setAddOpen((o) => !o)} className="flex w-full items-center justify-center gap-2 rounded-xl border-2 border-dashed border-zinc-700 py-3 text-sm font-semibold text-zinc-400 hover:border-emerald-500 hover:text-emerald-400">
            <Plus className="h-4 w-4" /> Add block
          </button>
          {addOpen && <AddPalette onPick={(t) => { onAdd(t); setAddOpen(false) }} />}
        </div>
      </div>
    )
  }

  const block = blocks[sel]
  const schema = BLOCK_SCHEMAS[block.type]
  return (
    <div className="space-y-3 p-4">
      <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
        <span className="text-sm font-semibold text-zinc-100">{schema?.label || block.type}</span>
        <div className="flex items-center gap-1.5 text-zinc-500">
          <button title="Move up" onClick={() => onMove(sel, -1)} disabled={sel === 0} className="hover:text-zinc-200 disabled:opacity-30"><ChevronUp className="h-4 w-4" /></button>
          <button title="Move down" onClick={() => onMove(sel, 1)} disabled={sel === blocks.length - 1} className="hover:text-zinc-200 disabled:opacity-30"><ChevronDown className="h-4 w-4" /></button>
          <button title="Duplicate" onClick={() => onDuplicate(sel)} className="hover:text-zinc-200"><Copy className="h-4 w-4" /></button>
          <button title="Delete" onClick={() => onRemove(sel)} className="hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
          {onClose && <button title="Close" onClick={onClose} className="ml-1 border-l border-zinc-700 pl-1.5 hover:text-zinc-200"><X className="h-4 w-4" /></button>}
        </div>
      </div>
      {schema ? (
        <>
          {schema.fields.map((f) => (
            <FieldInput key={f.key} field={f} value={block[f.key]} onChange={(v) => onChange(sel, { ...block, [f.key]: v })} />
          ))}
          <DesignInspector design={block._design} onChange={(dz) => onChange(sel, { ...block, _design: dz })} />
        </>
      ) : <p className="text-xs text-zinc-500">Unknown block “{block.type}”.</p>}
      <div className="relative pt-1">
        <button onClick={() => setAddOpen((o) => !o)} className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-zinc-700 py-2 text-xs font-medium text-zinc-400 hover:border-emerald-500 hover:text-emerald-400">
          <Plus className="h-3.5 w-3.5" /> Add block below
        </button>
        {addOpen && <AddPalette onPick={(t) => { onAddAt(t, sel); setAddOpen(false) }} />}
      </div>
    </div>
  )
}

// ── page editor ──────────────────────────────────────────────────────────────
export default function PageEditor() {
  const { siteId, pageId } = useParams<{ siteId: string; pageId: string }>()
  const navigate = useNavigate()
  const designerUnlocked = usePremium()

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

  // ── Canvas mode (Business only): click-on-page editing via the preview iframe.
  const canvasUnlocked = useBusinessTier()
  const [editMode, setEditMode] = useState<'form' | 'canvas'>('form')
  useEffect(() => { if (canvasUnlocked) setEditMode('canvas') }, [canvasUnlocked])
  const [selBlock, setSelBlock] = useState<number | null>(null)
  const [popPos, setPopPos] = useState<{ top: number; left: number }>({ top: 96, left: 96 })
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const suspendPreview = useRef(false)
  const [refreshTick, setRefreshTick] = useState(0)
  // Refs mirror state for the (mount-once) postMessage handler — avoid stale closures.
  const selBlockRef = useRef<number | null>(null)
  const blocksRef = useRef<CappeBlock[]>([])
  selBlockRef.current = selBlock
  blocksRef.current = blocks
  const postToCanvas = (msg: unknown) => iframeRef.current?.contentWindow?.postMessage(msg, '*')

  // Live theme switching — edited locally, previewed instantly, saved on demand.
  const [theme, setTheme] = useState<Record<string, unknown>>({})
  const [themeDirty, setThemeDirty] = useState(false)
  const [themeOpen, setThemeOpen] = useState(false)

  // Site-wide promos (announcement bar + pop-up) live on the site's meta_config,
  // edited here with live preview, persisted to the site on Save.
  const [meta, setMeta] = useState<Record<string, unknown>>({})
  const [promosDirty, setPromosDirty] = useState(false)
  const [promosOpen, setPromosOpen] = useState(false)

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
        setMeta(themeObj(site?.meta_config))
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load page'))
      .finally(() => setLoading(false))
  }, [siteId, pageId])

  // Debounced live preview of the current (unsaved) blocks + theme. In Canvas
  // mode it renders with the selection/edit runtime (`editable`). While an inline
  // edit or drag is in progress (`suspendPreview`), skip the refetch so the
  // iframe — and the user's caret — survive; it resumes on `cz-editing-end`.
  useEffect(() => {
    if (!siteId || !page) return
    const seq = ++previewSeq.current
    const t = setTimeout(() => {
      if (suspendPreview.current) return
      cappeApi
        .postHtml(`/sites/${siteId}/preview`, {
          title, slug: page.slug, content: { blocks }, theme_config: theme, meta_config: meta, editable: editMode === 'canvas',
        })
        .then((html) => { if (seq === previewSeq.current) setPreview(html) })
        .catch(() => { /* keep last good preview */ })
    }, 400)
    return () => clearTimeout(t)
  }, [siteId, page, title, blocks, theme, meta, editMode, refreshTick])

  // Canvas bridge: the framed runtime posts selection/edit/reorder events; we
  // validate by source identity (the iframe is opaque-origin, so `e.origin` is
  // "null" — never check it). Mounted once; reads live state via refs.
  useEffect(() => {
    function onMsg(e: MessageEvent) {
      if (e.source !== iframeRef.current?.contentWindow) return
      const d = e.data || {}
      switch (d.type) {
        case 'cz-ready':
          if (selBlockRef.current != null) postToCanvas({ type: 'cz-highlight', block: selBlockRef.current })
          break
        case 'cz-select': {
          setSelBlock(d.block)
          // Anchor the floating editor near the clicked element (iframe rect +
          // element rect → parent viewport), clamped on-screen.
          const fr = iframeRef.current?.getBoundingClientRect()
          if (fr && d.rect) {
            const left = Math.min(Math.max(fr.left + d.rect.left + 8, 8), window.innerWidth - 372)
            const top = Math.min(Math.max(fr.top + d.rect.top + 8, 64), window.innerHeight - 160)
            setPopPos({ top, left })
          }
          postToCanvas({ type: 'cz-highlight', block: d.block })
          break
        }
        case 'cz-edit': {
          const b = blocksRef.current[d.block]
          if (b) setBlocks((bs) => bs.map((x, j) => (j === d.block ? { ...x, [d.field]: d.value } : x)))
          break
        }
        case 'cz-reorder':
          setBlocks((bs) => {
            const next = [...bs]
            const [moved] = next.splice(d.from, 1)
            next.splice(d.to, 0, moved)
            return next
          })
          setSelBlock(d.to)
          break
        case 'cz-editing-start':
          suspendPreview.current = true
          break
        case 'cz-editing-end':
          suspendPreview.current = false
          setRefreshTick((n) => n + 1)
          break
      }
    }
    window.addEventListener('message', onMsg)
    return () => window.removeEventListener('message', onMsg)
  }, [])

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
  const setPremium = (on: boolean) => { setTheme((t) => ({ ...t, premium: on })); setThemeDirty(true) }
  // ── premium designer: independent fonts, typography, brand gradient ────────
  const setHeadingFont = (name: string) => { setTheme((t) => ({ ...t, fonts: { ...themeFonts(t), heading: name } })); setThemeDirty(true) }
  const setBodyFont = (name: string) => { setTheme((t) => ({ ...t, fonts: { ...themeFonts(t), body: name } })); setThemeDirty(true) }
  const setTypeKey = (key: string, value: unknown) => {
    setTheme((t) => { const type = { ...themeObj(t.type) }; if (value === '' || value == null) delete type[key]; else type[key] = value; return { ...t, type } })
    setThemeDirty(true)
  }
  const setBrandGradient = (g: Record<string, unknown> | null) => {
    setTheme((t) => {
      const colors = { ...(t.colors && typeof t.colors === 'object' && !Array.isArray(t.colors) ? (t.colors as Record<string, unknown>) : {}) }
      if (g) colors.brandGradient = g; else delete colors.brandGradient
      return { ...t, colors }
    })
    setThemeDirty(true)
  }

  const updateBlock = (i: number, b: CappeBlock) => setBlocks((bs) => bs.map((x, j) => (j === i ? b : x)))
  const removeBlock = (i: number) => { setBlocks((bs) => bs.filter((_, j) => j !== i)); setSelBlock(null) }
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
  // Insert a new block right after index `i` (canvas "add below").
  const addBlockAt = (type: string, i: number) => {
    setBlocks((bs) => { const next = [...bs]; next.splice(i + 1, 0, BLOCK_SCHEMAS[type].make()); return next })
    setSelBlock(i + 1)
  }
  // Deep-copy a block (incl. _design + list items) and insert after it.
  const duplicateBlock = (i: number) => {
    setBlocks((bs) => {
      const clone = JSON.parse(JSON.stringify(bs[i])) as CappeBlock
      const next = [...bs]; next.splice(i + 1, 0, clone); return next
    })
    setSelBlock(i + 1)
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
      // Persist the theme + promos (meta_config) to the site too, if changed here.
      if (themeDirty || promosDirty) {
        const patch: Record<string, unknown> = {}
        if (themeDirty) patch.theme_config = theme
        if (promosDirty) patch.meta_config = meta
        await cappeApi.put<CappeSite>(`/sites/${siteId}`, patch)
        setThemeDirty(false)
        setPromosDirty(false)
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

            {/* Site-wide promos (announcement bar + pop-up) */}
            <PromosPanel meta={meta} premium={designerUnlocked} dirty={promosDirty} onChange={(m) => { setMeta(m); setPromosDirty(true) }} />

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

                      <div className="flex items-center justify-between">
                        <span className="flex items-center gap-1 text-xs text-zinc-400"><Sparkles className="h-3 w-3 text-amber-400" /> Premium effects</span>
                        <div className="flex rounded-lg border border-zinc-700 p-0.5">
                          {([['On', true], ['Off', false]] as const).map(([label, on]) => (
                            <button key={label} onClick={() => setPremium(on)} className={`rounded-md px-2.5 py-0.5 text-xs font-medium ${!!theme.premium === on ? 'bg-emerald-500 text-zinc-950' : 'text-zinc-400 hover:text-zinc-200'}`}>{label}</button>
                          ))}
                        </div>
                      </div>
                    </div>

                    {/* premium designer studio — custom fonts, type, brand gradient */}
                    <div className="mt-3 space-y-2.5 border-t border-zinc-800 pt-3">
                      <p className={`${dHead} flex items-center gap-1`}><Wand2 className="h-3 w-3 text-amber-400" /> Designer</p>
                      {!designerUnlocked ? (
                        <PremiumLock>Upgrade to Pro for custom fonts, gradients &amp; motion.</PremiumLock>
                      ) : (
                        <>
                          <div className="grid grid-cols-2 gap-2">
                            <CappeFontPicker label="Heading font" value={themeFonts(theme).heading || 'Inter'} onChange={setHeadingFont} />
                            <CappeFontPicker label="Body font" value={themeFonts(theme).body || 'Inter'} onChange={setBodyFont} bodyOnly />
                          </div>
                          <div className="grid grid-cols-2 gap-2">
                            <label className="block"><span className={dLabel}>Heading weight</span>
                              <select value={String(themeObj(theme.type).headingWeight ?? '')} onChange={(e) => setTypeKey('headingWeight', e.target.value ? Number(e.target.value) : '')} className={`${inputCls} py-1.5`}>
                                <option value="">Default</option>
                                {([['400', 'Regular'], ['500', 'Medium'], ['600', 'Semibold'], ['700', 'Bold'], ['800', 'Extrabold'], ['900', 'Black']] as [string, string][]).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                              </select></label>
                            <label className="block"><span className={dLabel}>Letter spacing</span>
                              <select value={String(themeObj(theme.type).headingSpacing ?? '')} onChange={(e) => setTypeKey('headingSpacing', e.target.value)} className={`${inputCls} py-1.5`}>
                                <option value="">Default</option>
                                {([['-0.03em', 'Tight'], ['-0.015em', 'Snug'], ['0em', 'Normal'], ['0.04em', 'Wide']] as [string, string][]).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                              </select></label>
                          </div>
                          <label className="block"><span className={dLabel}>Animated headline</span>
                            <select value={String(themeObj(theme.type).heroAnim ?? 'none')} onChange={(e) => setTypeKey('heroAnim', e.target.value)} className={`${inputCls} py-1.5`}>
                              {([['none', 'None'], ['rise', 'Rise in'], ['shimmer', 'Shimmer']] as [string, string][]).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                            </select></label>
                          <DCheck
                            label="Brand gradient buttons"
                            checked={!!obj(obj(theme.colors).brandGradient).stops}
                            onChange={(on) => setBrandGradient(on ? { angle: 135, stops: [themeColors(theme).brand || '#10b981', '#a3e635'] } : null)}
                          />
                          {!!obj(obj(theme.colors).brandGradient).stops && (
                            <GradientPicker value={obj(obj(theme.colors).brandGradient)} onChange={(g) => setBrandGradient(g)} />
                          )}
                        </>
                      )}
                    </div>
                    <p className="mt-3 text-[11px] text-zinc-500">Preview updates live. <span className="text-zinc-300">Save</span> to publish the look.</p>
                  </div>
                </>
              )}
            </div>

            {canvasUnlocked && (
              <div className="flex rounded-lg border border-zinc-700 p-0.5">
                {([['canvas', 'Canvas', MousePointerClick], ['form', 'Form', Pencil]] as const).map(([m, label, Icon]) => (
                  <button key={m} onClick={() => setEditMode(m)} className={`flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium ${editMode === m ? 'bg-emerald-500 text-zinc-950' : 'text-zinc-400 hover:text-zinc-200'}`}>
                    <Icon className="h-3.5 w-3.5" /> {label}
                  </button>
                ))}
              </div>
            )}

            <select value={status} onChange={(e) => setStatus(e.target.value as 'draft' | 'published')} className="rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-100">
              <option value="draft">Draft</option>
              <option value="published">Published</option>
            </select>
            <button onClick={save} disabled={saving} className="flex items-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60">
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Save
            </button>
          </div>
        </div>

        {editMode === 'canvas' ? (
          /* canvas: click a section on the page → a floating editor pops up at it (Business) */
          <div className="relative flex min-h-0 flex-1">
            <div className="hidden flex-1 bg-zinc-900 lg:block">
              {preview ? (
                <iframe ref={iframeRef} title="Canvas" srcDoc={preview} sandbox="allow-scripts" className="h-full w-full border-0" />
              ) : (
                <div className="flex h-full items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-zinc-600" /></div>
              )}
            </div>

            {/* floating editor — anchored to the clicked element when selected,
                else a corner card with the Add affordance + hint */}
            <div
              className="fixed z-40 hidden max-h-[74vh] w-[360px] overflow-y-auto rounded-xl border border-zinc-700 bg-zinc-900 shadow-2xl shadow-black/60 lg:block"
              style={selBlock != null ? { top: popPos.top, left: popPos.left } : { bottom: 16, left: 16 }}
            >
              <CanvasPanel
                blocks={blocks}
                sel={selBlock}
                onChange={updateBlock}
                onMove={moveBlock}
                onRemove={removeBlock}
                onDuplicate={duplicateBlock}
                onAddAt={addBlockAt}
                onAdd={addBlock}
                onClose={() => { setSelBlock(null); postToCanvas({ type: 'cz-clear' }) }}
              />
            </div>

            <div className="flex w-full items-center justify-center p-8 text-center text-sm text-zinc-500 lg:hidden">
              Canvas editing needs a wider screen — switch to Form mode or use a desktop.
            </div>
          </div>
        ) : (
          /* split: form editor | live preview */
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
        )}
      </div>
    </SiteCtx.Provider>
  )
}
