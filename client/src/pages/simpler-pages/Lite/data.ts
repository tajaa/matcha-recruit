import type { Pillar } from './types'

export const PILLARS: Pillar[] = [
  {
    id: 'incidents',
    number: '01',
    title: 'Incident Reporting',
    tagline: 'A magic link per location. No login, no app.',
    description:
      'A link anyone can open and file into in seconds — so incidents get reported when they happen, not weeks later in a binder no one reads.',
    highlight: 'Every incident, a defensible record — no compliance team required.',
  },
  {
    id: 'hris',
    number: '02',
    title: 'HRIS/CSV Import',
    tagline: 'Your employee roster, already there.',
    description:
      'Connect Gusto, Rippling, BambooHR, or ADP — or just drop in a CSV. Every incident and OSHA log pulls from the same roster, so no one re-types a name.',
    highlight: 'One less spreadsheet to keep in sync.',
  },
  {
    id: 'ir_analysis',
    number: '03',
    title: 'IR Analysis',
    tagline: 'The signal in the noise, surfaced early.',
    description:
      'Repeat problems get flagged before they compound — so a small issue gets handled while it’s still small, not after it’s a claim.',
    highlight: 'The pattern no single manager would catch.',
  },
  {
    id: 'osha',
    number: '04',
    title: 'OSHA Logs',
    tagline: 'The logs an audit asks for — always current.',
    description:
      'The recordkeeping that usually means a year-end scramble stays up to date on its own, a click from ready whenever you need it.',
    highlight: 'Audit-ready any time, no re-keying.',
  },
]
