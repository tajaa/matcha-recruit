import { cvNewElement } from './canvasHelpers'
import { F, type BlockSchema } from './types'

export const BLOCK_SCHEMAS: Record<string, BlockSchema> = {
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
  canvas: {
    label: 'Blank / Freeform',
    make: () => ({
      type: 'canvas', grid: { cols: 24, rowH: 24, rows: 30 }, mobile: { cols: 8, rowH: 24, rows: 60 },
      elements: [cvNewElement('heading', 2)],
    }),
    fields: [],  // canvas uses its own inspector/form editor, not generic Field rows
  },
}

export const BLOCK_ORDER = ['hero', 'features', 'split', 'bento', 'stats', 'credentials', 'logos', 'gallery', 'pricing', 'testimonial', 'reviews', 'faq', 'cta', 'store', 'booking', 'menu', 'hours', 'map', 'posts', 'text', 'contact', 'newsletter', 'canvas']
