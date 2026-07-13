// Newsletter block schema — the client-side contract for the visual builder.
//
// Block `type` + field keys MUST stay in sync with the server renderer in
// `server/app/core/services/email_blocks.py` (the design_json is rendered
// there into email-safe HTML). Adding a block = a schema entry here + a
// renderer there.

export type FieldKind = 'text' | 'textarea' | 'select' | 'bool' | 'image' | 'list'

export type Field = {
  key: string
  label: string
  kind: FieldKind
  placeholder?: string
  help?: string
  options?: { value: string; label: string }[]
  item?: Field[] // for kind 'list'
  newItem?: () => Record<string, unknown>
  addLabel?: string
}

export type NLBlock = { id: string; type: string } & Record<string, unknown>

export type ThemePreset = 'light' | 'dark'

export type NewsletterDesign = {
  version: number
  theme: { preset: ThemePreset; brandColor?: string; bg?: string; brandName?: string; logoUrl?: string }
  blocks: NLBlock[]
}

export type BlockSchema = {
  type: string
  label: string
  icon: string // emoji glyph for the insert menu / block card
  group: 'Layout' | 'Content' | 'Media' | 'Social proof'
  make: () => Omit<NLBlock, 'id'>
  fields: Field[]
}

const F = (key: string, label: string, kind: FieldKind = 'text', extra: Partial<Field> = {}): Field =>
  ({ key, label, kind, ...extra })

export const BLOCK_SCHEMAS: Record<string, BlockSchema> = {
  hero: {
    type: 'hero', label: 'Hero', icon: '🖼️', group: 'Layout',
    make: () => ({ type: 'hero', layout: 'overlay', overlay: 'dark', align: 'center', eyebrow: '', heading: 'Your headline', subheading: 'A sentence of supporting copy.', ctaLabel: 'Read more', ctaHref: '' }),
    fields: [
      F('image', 'Hero image', 'image', { help: 'Required for the overlay layout — the visual behind the text.' }),
      F('layout', 'Layout', 'select', { options: [
        { value: 'overlay', label: 'Text over image' },
        { value: 'stacked', label: 'Image on top, text below' },
      ] }),
      F('overlay', 'Image darkening (overlay layout)', 'select', { options: [
        { value: 'light', label: 'Light' }, { value: 'medium', label: 'Medium' }, { value: 'dark', label: 'Dark' },
      ] }),
      F('align', 'Text align', 'select', { options: [{ value: 'center', label: 'Center' }, { value: 'left', label: 'Left' }] }),
      F('eyebrow', 'Eyebrow (small label)'),
      F('heading', 'Heading'),
      F('subheading', 'Subheading', 'textarea'),
      F('ctaLabel', 'Button label'),
      F('ctaHref', 'Button link', 'text', { placeholder: 'https://…' }),
    ],
  },
  heading: {
    type: 'heading', label: 'Heading', icon: '🔤', group: 'Content',
    make: () => ({ type: 'heading', heading: 'Section heading', subheading: '', align: 'left' }),
    fields: [
      F('heading', 'Heading'),
      F('subheading', 'Subheading', 'textarea'),
      F('align', 'Align', 'select', { options: [{ value: 'left', label: 'Left' }, { value: 'center', label: 'Center' }] }),
    ],
  },
  text: {
    type: 'text', label: 'Text', icon: '¶', group: 'Content',
    make: () => ({ type: 'text', body: 'Write your paragraph here. Leave a blank line to start a new paragraph.', align: 'left' }),
    fields: [
      F('body', 'Body', 'textarea'),
      F('align', 'Align', 'select', { options: [{ value: 'left', label: 'Left' }, { value: 'center', label: 'Center' }] }),
    ],
  },
  button: {
    type: 'button', label: 'Button', icon: '🔘', group: 'Content',
    make: () => ({ type: 'button', label: 'Get started', href: '', align: 'center', variant: 'solid', fullWidth: false }),
    fields: [
      F('label', 'Button label'),
      F('href', 'Button link', 'text', { placeholder: 'https://…' }),
      F('align', 'Align', 'select', { options: [{ value: 'left', label: 'Left' }, { value: 'center', label: 'Center' }, { value: 'right', label: 'Right' }] }),
      F('variant', 'Style', 'select', { options: [{ value: 'solid', label: 'Solid (brand fill)' }, { value: 'outline', label: 'Outline' }] }),
      F('fullWidth', 'Full width', 'bool'),
    ],
  },
  image: {
    type: 'image', label: 'Image', icon: '🏞️', group: 'Media',
    make: () => ({ type: 'image', url: '', alt: '', caption: '', href: '', width: 'full', radius: true }),
    fields: [
      F('url', 'Image', 'image'),
      F('alt', 'Alt text', 'text', { help: 'Shown if the image fails to load; read by screen readers.' }),
      F('caption', 'Caption'),
      F('href', 'Links to (optional)', 'text', { placeholder: 'https://…' }),
      F('width', 'Width', 'select', { options: [{ value: 'full', label: 'Full width' }, { value: 'inset', label: 'Inset (centered)' }] }),
      F('radius', 'Rounded corners', 'bool'),
    ],
  },
  imageText: {
    type: 'imageText', label: 'Image + Text', icon: '🧱', group: 'Layout',
    make: () => ({ type: 'imageText', image: '', heading: 'A focused point', body: 'Describe one thing, with an image alongside.', ctaLabel: '', ctaHref: '', imageSide: 'left' }),
    fields: [
      F('image', 'Image', 'image'),
      F('imageSide', 'Image on', 'select', { options: [{ value: 'left', label: 'Left' }, { value: 'right', label: 'Right' }] }),
      F('heading', 'Heading'),
      F('body', 'Body', 'textarea'),
      F('ctaLabel', 'Link label (optional)'),
      F('ctaHref', 'Link', 'text', { placeholder: 'https://…' }),
    ],
  },
  columns: {
    type: 'columns', label: 'Columns', icon: '▥', group: 'Layout',
    make: () => ({ type: 'columns', columns: [
      { heading: 'Column one', body: 'Short supporting copy.' },
      { heading: 'Column two', body: 'Short supporting copy.' },
    ] }),
    fields: [
      F('columns', 'Columns (2–3)', 'list', {
        addLabel: 'Add column', newItem: () => ({ heading: '', body: '' }),
        item: [F('image', 'Image', 'image'), F('heading', 'Heading'), F('body', 'Body', 'textarea'), F('ctaLabel', 'Link label'), F('ctaHref', 'Link')],
      }),
    ],
  },
  features: {
    type: 'features', label: 'Feature grid', icon: '✦', group: 'Content',
    make: () => ({ type: 'features', heading: 'Why it matters', subheading: '', items: [
      { icon: '✦', title: 'Feature one', body: 'Short description.' },
      { icon: '◆', title: 'Feature two', body: 'Short description.' },
    ] }),
    fields: [
      F('heading', 'Section heading'),
      F('subheading', 'Section subheading', 'textarea'),
      F('items', 'Features', 'list', {
        addLabel: 'Add feature', newItem: () => ({ icon: '', title: '', body: '' }),
        item: [F('icon', 'Icon / emoji'), F('title', 'Title'), F('body', 'Body', 'textarea')],
      }),
    ],
  },
  articles: {
    type: 'articles', label: 'Article cards', icon: '📰', group: 'Content',
    make: () => ({ type: 'articles', heading: 'From the blog', items: [
      { title: 'Article title', excerpt: 'A one-line summary to draw the click.', href: '', label: 'Read more' },
    ] }),
    fields: [
      F('heading', 'Section heading'),
      F('items', 'Articles', 'list', {
        addLabel: 'Add article', newItem: () => ({ title: '', excerpt: '', href: '', label: 'Read more' }),
        item: [F('image', 'Thumbnail', 'image'), F('title', 'Title'), F('excerpt', 'Excerpt', 'textarea'), F('href', 'Link', 'text', { placeholder: 'https://…' }), F('label', 'Link label')],
      }),
    ],
  },
  quote: {
    type: 'quote', label: 'Quote', icon: '❝', group: 'Social proof',
    make: () => ({ type: 'quote', quote: 'A short, punchy customer quote.', author: 'Full name', role: 'Title, Company' }),
    fields: [
      F('quote', 'Quote', 'textarea'),
      F('author', 'Author'),
      F('role', 'Role / company'),
    ],
  },
  stats: {
    type: 'stats', label: 'Stats band', icon: '📊', group: 'Social proof',
    make: () => ({ type: 'stats', heading: '', items: [
      { value: '500+', label: 'Customers' },
      { value: '98%', label: 'Satisfaction' },
      { value: '4.9', label: 'Avg rating' },
    ] }),
    fields: [
      F('heading', 'Section heading (optional)'),
      F('items', 'Stats (up to 4)', 'list', {
        addLabel: 'Add stat', newItem: () => ({ value: '', label: '' }),
        item: [F('value', 'Number', 'text', { placeholder: '500+' }), F('label', 'Label')],
      }),
    ],
  },
  divider: {
    type: 'divider', label: 'Divider', icon: '—', group: 'Layout',
    make: () => ({ type: 'divider' }),
    fields: [],
  },
  spacer: {
    type: 'spacer', label: 'Spacer', icon: '↕', group: 'Layout',
    make: () => ({ type: 'spacer', size: 'md' }),
    fields: [
      F('size', 'Height', 'select', { options: [{ value: 'sm', label: 'Small' }, { value: 'md', label: 'Medium' }, { value: 'lg', label: 'Large' }] }),
    ],
  },
  video: {
    type: 'video', label: 'Video', icon: '▶', group: 'Media',
    make: () => ({ type: 'video', url: '', poster: '', caption: '' }),
    fields: [
      F('url', 'Video link', 'text', { placeholder: 'https://… (email clients open it in the browser)' }),
      F('poster', 'Poster image', 'image', { help: 'Thumbnail shown in the email — clicking opens the video.' }),
      F('caption', 'Caption'),
    ],
  },
  footer: {
    type: 'footer', label: 'Footer / social', icon: '⚓', group: 'Layout',
    make: () => ({ type: 'footer', brandName: 'Matcha', tagline: 'HR, handled.', socials: [{ label: 'Website', href: '' }] }),
    fields: [
      F('brandName', 'Brand name'),
      F('tagline', 'Tagline'),
      F('socials', 'Social links', 'list', {
        addLabel: 'Add link', newItem: () => ({ label: '', href: '' }),
        item: [F('label', 'Label'), F('href', 'Link', 'text', { placeholder: 'https://…' })],
      }),
    ],
  },
}

export const BLOCK_ORDER = [
  'hero', 'heading', 'text', 'image', 'imageText', 'columns',
  'features', 'articles', 'quote', 'stats', 'button', 'video',
  'divider', 'spacer', 'footer',
]

// Block types that count as a "visual" for the mandatory-media check.
const MEDIA_TYPES = new Set(['hero', 'image', 'imageText', 'video'])

export function blockHasMedia(b: NLBlock): boolean {
  if (b.type === 'columns') return (b.columns as { image?: string }[] | undefined)?.some((c) => !!c?.image) ?? false
  if (b.type === 'articles') return (b.items as { image?: string }[] | undefined)?.some((c) => !!c?.image) ?? false
  if (!MEDIA_TYPES.has(b.type)) return false
  return !!(b.image || b.url || b.poster)
}

export function designHasMedia(design: NewsletterDesign | null | undefined): boolean {
  return !!design?.blocks?.some(blockHasMedia)
}

let _seq = 0
export function newBlockId(): string {
  // crypto.randomUUID is available in all target browsers; the counter is a
  // defensive fallback so ids never collide even without it.
  const rand = typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `${Date.now()}`
  return `blk_${rand}_${_seq++}`
}

export function makeBlock(type: string): NLBlock {
  const schema = BLOCK_SCHEMAS[type]
  if (!schema) throw new Error(`Unknown block type: ${type}`)
  return { id: newBlockId(), ...schema.make() } as NLBlock
}

export function emptyDesign(preset: ThemePreset = 'light'): NewsletterDesign {
  return { version: 1, theme: { preset, brandName: 'Matcha' }, blocks: [] }
}
