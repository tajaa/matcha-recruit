import type { Pillar } from './types'

// Accents reuse the colors home/instruments/PlatformInstrument.tsx already
// assigns these domains (PLATFORM_DOMAINS), so the hero instrument and these
// pillar rows read as the same system rather than two different palettes.
export const PILLARS: Pillar[] = [
  {
    id: 'ehs',
    number: '01',
    title: 'Safety & EHS',
    tagline: 'Every incident captured, categorized, and routed.',
    description:
      'The safety work that usually slips through the cracks — captured the moment it happens, and defensible when it matters.',
    highlight: 'The safety layer that runs itself.',
    accent: '#d9b65f',
  },
  {
    id: 'grc',
    number: '02',
    title: 'Governance & Compliance',
    tagline: 'The rules that govern you, always current.',
    description:
      'Know what the law asks of you everywhere you operate — and hear about the changes before they land.',
    highlight: 'Audit-ready, without the fire drill.',
    accent: '#E2725B',
  },
  {
    id: 'er',
    number: '03',
    title: 'Employee Relations',
    tagline: 'Cases handled before they become claims.',
    description:
      'The hard people problems, handled and documented right — so a difficult conversation never turns into a lawsuit.',
    highlight: 'The hard conversations, documented right.',
    accent: '#86efac',
  },
  {
    id: 'convergence',
    number: '04',
    title: 'One Brain',
    tagline: 'Three disciplines, one live record.',
    description:
      'Safety, compliance, and people problems inform each other in real time — one honest view of where your risk really sits.',
    highlight: 'Risk surfaces before it compounds.',
    accent: '#A3C57D',
  },
]

export const PLATFORM_JSON_LD = {
  '@context': 'https://schema.org',
  '@graph': [
    {
      '@type': 'Service',
      '@id': 'https://hey-matcha.com/matcha-platform#service',
      name: 'Matcha Full Platform',
      serviceType: 'Unified workplace safety, compliance, and employee relations platform',
      url: 'https://hey-matcha.com/matcha-platform',
      provider: { '@type': 'Organization', name: 'Matcha', url: 'https://hey-matcha.com/' },
      areaServed: { '@type': 'Country', name: 'United States' },
      description:
        'Safety, compliance, and employee relations unified on one agentic platform — every signal informs the others, rolled into a single live risk index.',
    },
    {
      '@type': 'BreadcrumbList',
      itemListElement: [
        { '@type': 'ListItem', position: 1, name: 'Matcha', item: 'https://hey-matcha.com/' },
        { '@type': 'ListItem', position: 2, name: 'Full Platform', item: 'https://hey-matcha.com/matcha-platform' },
      ],
    },
  ],
}
