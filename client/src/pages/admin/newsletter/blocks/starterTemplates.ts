// Professionally-designed starter layouts for the block builder. Each is a
// scaffold the admin fills in (images are left blank so the mandatory-media
// hint nudges them to add a real visual). Blocks are stored without ids;
// `instantiateStarter` assigns fresh ids when one is applied.

import { newBlockId, type NewsletterDesign, type NLBlock, type ThemePreset } from './schema'

export type Starter = {
  key: string
  name: string
  description: string
  preset: ThemePreset
  blocks: Omit<NLBlock, 'id'>[]
}

export const STARTERS: Starter[] = [
  {
    key: 'announcement',
    name: 'Announcement',
    description: 'A single, focused message with a hero and one clear call to action.',
    preset: 'light',
    blocks: [
      { type: 'hero', layout: 'overlay', overlay: 'dark', align: 'center', image: '', eyebrow: 'ANNOUNCEMENT', heading: 'Something new is here', subheading: 'One or two sentences on why it matters to your readers.', ctaLabel: 'Learn more', ctaHref: '' },
      { type: 'text', align: 'center', body: 'Add the details of your announcement here. Keep it short and skimmable — a paragraph or two is plenty.' },
      { type: 'button', label: 'Read the full story', href: '', align: 'center', variant: 'solid' },
      { type: 'divider' },
      { type: 'footer', brandName: 'Matcha', tagline: 'HR, handled.', socials: [{ label: 'Website', href: '' }] },
    ],
  },
  {
    key: 'digest',
    name: 'Content digest',
    description: 'A roundup of links — perfect for a weekly or monthly newsletter.',
    preset: 'light',
    blocks: [
      { type: 'heading', align: 'left', heading: 'This month at Matcha', subheading: 'The stories, updates, and resources worth your time.' },
      { type: 'articles', heading: 'Featured reads', items: [
        { image: '', title: 'Headline of your first story', excerpt: 'A one-line summary that earns the click.', href: '', label: 'Read more' },
        { image: '', title: 'Headline of your second story', excerpt: 'A one-line summary that earns the click.', href: '', label: 'Read more' },
        { image: '', title: 'Headline of your third story', excerpt: 'A one-line summary that earns the click.', href: '', label: 'Read more' },
      ] },
      { type: 'divider' },
      { type: 'footer', brandName: 'Matcha', tagline: 'HR, handled.', socials: [{ label: 'Website', href: '' }, { label: 'LinkedIn', href: '' }] },
    ],
  },
  {
    key: 'product',
    name: 'Product update',
    description: 'Show off new features with a hero, feature grid, stats, and a CTA.',
    preset: 'light',
    blocks: [
      { type: 'hero', layout: 'overlay', overlay: 'dark', align: 'center', image: '', eyebrow: 'PRODUCT UPDATE', heading: "What's new this release", subheading: 'A quick tour of everything we shipped.', ctaLabel: 'See the changelog', ctaHref: '' },
      { type: 'heading', align: 'left', heading: 'Highlights', subheading: 'Three things we think you’ll love.' },
      { type: 'features', items: [
        { icon: '⚡', title: 'Faster', body: 'Describe the improvement in a sentence.' },
        { icon: '🛡️', title: 'Safer', body: 'Describe the improvement in a sentence.' },
        { icon: '📊', title: 'Smarter', body: 'Describe the improvement in a sentence.' },
        { icon: '✨', title: 'Nicer', body: 'Describe the improvement in a sentence.' },
      ] },
      { type: 'stats', heading: 'By the numbers', items: [
        { value: '10k+', label: 'Teams' }, { value: '99.9%', label: 'Uptime' }, { value: '4.9', label: 'Rating' },
      ] },
      { type: 'button', label: 'Try it now', href: '', align: 'center', variant: 'solid' },
      { type: 'divider' },
      { type: 'footer', brandName: 'Matcha', tagline: 'HR, handled.', socials: [{ label: 'Website', href: '' }] },
    ],
  },
  {
    key: 'welcome',
    name: 'Welcome',
    description: 'Onboard a new subscriber with a warm intro and next steps.',
    preset: 'light',
    blocks: [
      { type: 'hero', layout: 'stacked', align: 'center', image: '', eyebrow: 'WELCOME', heading: 'Glad you’re here 👋', subheading: 'Here’s what to expect from us — and how to get the most out of it.' },
      { type: 'imageText', imageSide: 'left', image: '', heading: 'Start here', body: 'Point new readers to the one thing they should do first.', ctaLabel: 'Get started', ctaHref: '' },
      { type: 'features', heading: 'What you’ll get', items: [
        { icon: '📩', title: 'Weekly insights', body: 'Straight to your inbox.' },
        { icon: '🎁', title: 'Subscriber perks', body: 'Exclusive resources and offers.' },
      ] },
      { type: 'button', label: 'Explore Matcha', href: '', align: 'center', variant: 'solid' },
      { type: 'divider' },
      { type: 'footer', brandName: 'Matcha', tagline: 'HR, handled.', socials: [{ label: 'Website', href: '' }] },
    ],
  },
]

export function instantiateStarter(starter: Starter): NewsletterDesign {
  return {
    version: 1,
    theme: { preset: starter.preset, brandName: 'Matcha' },
    blocks: starter.blocks.map((b) => ({ ...b, id: newBlockId() } as NLBlock)),
  }
}
