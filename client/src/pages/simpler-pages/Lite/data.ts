import type { Pillar } from './types'

// Accents pulled from the same visual family as the other rebuilt pages —
// no fixed upstream palette for Lite's four domains, so these are chosen for
// contrast against noir and against each other.
export const PILLARS: Pillar[] = [
  {
    id: 'incidents',
    number: '01',
    title: 'Incident Reporting',
    tagline: 'A magic link per location. No login, no app.',
    description:
      'A link anyone can open and file into in seconds — so incidents get reported when they happen, not weeks later in a binder no one reads.',
    highlight: 'Every incident, a defensible record — no compliance team required.',
    accent: '#86efac',
  },
  {
    id: 'hris',
    number: '02',
    title: 'HRIS/CSV Import',
    tagline: 'Your employee roster, already there.',
    description:
      'Connect Gusto, Rippling, BambooHR, or ADP — or just drop in a CSV. Every incident and OSHA log pulls from the same roster, so no one re-types a name.',
    highlight: 'One less spreadsheet to keep in sync.',
    accent: '#7FB2C9',
  },
  {
    id: 'ir_analysis',
    number: '03',
    title: 'IR Analysis',
    tagline: 'The signal in the noise, surfaced early.',
    description:
      "Repeat problems get flagged before they compound — so a small issue gets handled while it's still small, not after it's a claim.",
    highlight: 'The pattern no single manager would catch.',
    accent: '#F2C14E',
  },
  {
    id: 'osha',
    number: '04',
    title: 'OSHA Logs',
    tagline: 'The logs an audit asks for — always current.',
    description:
      'The recordkeeping that usually means a year-end scramble stays up to date on its own, a click from ready whenever you need it.',
    highlight: 'Audit-ready any time, no re-keying.',
    accent: '#E2725B',
  },
]

// The one CoverageGrid entry that wasn't a restatement of a pillar — kept as
// a small capability index alongside the four, not a second full section.
export const CAPABILITY_EXTRA = {
  id: 'resources',
  title: 'HR resource hub',
  caption:
    'The everyday HR documents your team reaches for, ready to use — no starting from a blank page.',
}

export const LITE_JSON_LD = {
  '@context': 'https://schema.org',
  '@graph': [
    {
      '@type': 'Service',
      '@id': 'https://hey-matcha.com/matcha-lite#service',
      name: 'Matcha Lite',
      serviceType: 'Incident reporting, OSHA recordkeeping, and HR records for small teams',
      url: 'https://hey-matcha.com/matcha-lite',
      provider: { '@type': 'Organization', name: 'Matcha', url: 'https://hey-matcha.com/' },
      areaServed: { '@type': 'Country', name: 'United States' },
      description:
        'The everyday intake layer for small teams — magic-link incident reporting, HRIS/CSV roster import, IR pattern analysis, and self-updating OSHA 300 logs.',
    },
    {
      '@type': 'BreadcrumbList',
      itemListElement: [
        { '@type': 'ListItem', position: 1, name: 'Matcha', item: 'https://hey-matcha.com/' },
        { '@type': 'ListItem', position: 2, name: 'Matcha Lite', item: 'https://hey-matcha.com/matcha-lite' },
      ],
    },
  ],
}
