// One-click page presets for the Cappe site editor. Each preset seeds a page's
// content.blocks with a pre-built, fully-editable section stack — so a creator
// can spin up a styled Shop / About / Contact / Services page instead of an
// empty canvas. Block shapes mirror the editor's BLOCK_SCHEMAS make() defaults;
// every field stays editable in the page editor afterwards.
import type { CappeBlock } from '../types/cappe'

export type CappePagePreset = {
  id: string
  label: string
  blurb: string
  title: string
  blocks: CappeBlock[]
}

export const PAGE_PRESETS: CappePagePreset[] = [
  {
    id: 'shop',
    label: 'Shop',
    blurb: 'Storefront with a hero, your products, trust badges & a signup.',
    title: 'Shop',
    blocks: [
      { type: 'hero', heading: 'Shop the collection', subheading: 'Browse our latest products — secure checkout, fast fulfilment.', style: 'centered', cta: 'Browse products', ctaHref: '#shop' },
      { type: 'store', heading: 'Featured products', subheading: 'Hand-picked favourites from our catalogue.' },
      { type: 'features', heading: 'Why shop with us', items: [
        { icon: '🚚', title: 'Fast shipping', body: 'Orders ship within 1–2 business days.' },
        { icon: '↩️', title: 'Easy returns', body: '30-day, no-questions-asked returns.' },
        { icon: '🔒', title: 'Secure checkout', body: 'Encrypted payments you can trust.' },
      ] },
      { type: 'newsletter', heading: 'Get 10% off your first order', subheading: 'Join the list for early drops and members-only deals.' },
    ],
  },
  {
    id: 'about',
    label: 'About',
    blurb: 'Tell your story — hero, narrative, values, gallery & a CTA.',
    title: 'About',
    blocks: [
      { type: 'hero', heading: 'About us', subheading: 'The people, the mission, and why we do what we do.', style: 'split' },
      { type: 'split', eyebrow: 'Our story', heading: 'How it started', body: 'Share the origin story — what sparked this, the problem you set out to solve, and where you are today.', bullets: ['Founded with a clear purpose', 'Built on craft and care', 'Growing with our community'] },
      { type: 'features', heading: 'What we stand for', items: [
        { icon: '✦', title: 'Quality first', body: 'We sweat the details so you don’t have to.' },
        { icon: '◆', title: 'Honest & open', body: 'Transparent pricing and straight talk.' },
        { icon: '▲', title: 'Customer-obsessed', body: 'Your experience drives every decision.' },
      ] },
      { type: 'gallery', heading: 'Behind the scenes', images: [] },
      { type: 'cta', heading: 'Want to work with us?', subheading: 'We’d love to hear from you.', cta: 'Get in touch', ctaHref: '/p/contact' },
    ],
  },
  {
    id: 'contact',
    label: 'Contact',
    blurb: 'A focused contact page — hero, message form & a map.',
    title: 'Contact',
    blocks: [
      { type: 'hero', heading: 'Get in touch', subheading: 'Questions, quotes, or just to say hi — we reply fast.', style: 'minimal' },
      { type: 'contact', heading: 'Send a message', subheading: 'Fill in the form and we’ll get back to you.', fields: ['name', 'email', 'message'], formSlug: 'contact' },
      { type: 'map', heading: 'Find us' },
    ],
  },
  {
    id: 'services',
    label: 'Services',
    blurb: 'Showcase offerings — hero, services, pricing & booking CTA.',
    title: 'Services',
    blocks: [
      { type: 'hero', heading: 'Services', subheading: 'Everything we offer, and how we can help.', style: 'centered', cta: 'Book a session', ctaHref: '#book' },
      { type: 'features', heading: 'What we offer', items: [
        { icon: '✦', title: 'Service one', body: 'Describe the outcome a client gets.' },
        { icon: '◆', title: 'Service two', body: 'Describe the outcome a client gets.' },
        { icon: '▲', title: 'Service three', body: 'Describe the outcome a client gets.' },
      ] },
      { type: 'pricing', heading: 'Pricing', plans: [
        { name: 'Starter', price: '$0', period: '/mo', features: ['Feature one', 'Feature two'], cta: 'Choose' },
        { name: 'Pro', price: '$24', period: '/mo', features: ['Everything in Starter', 'Feature three', 'Feature four'], cta: 'Choose', highlighted: true },
      ] },
      { type: 'cta', heading: 'Ready to start?', cta: 'Book now', ctaHref: '#book' },
    ],
  },
]
