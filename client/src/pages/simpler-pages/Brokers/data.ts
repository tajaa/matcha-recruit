import type { Pillar, RiskBand } from './types'

// ── Hero (kept from the original /brokers page) ────────────────────────────

export const BAND_COLOR: Record<RiskBand, string> = {
  critical: '#ff6b6b',
  elevated: '#f5b545',
  stable: '#6ee7a8',
}

export const RADAR_ROWS: { client: string; band: RiskBand; metric: string; delta: string }[] = [
  { client: 'Northgate Logistics', band: 'critical', metric: 'TRIR 6.2', delta: '+1.4' },
  { client: 'Cedar Valley Mfg', band: 'elevated', metric: 'Lost days 14', delta: '+5.0' },
  { client: 'Harbor Foods Co', band: 'stable', metric: 'DART 1.1', delta: '−0.3' },
  { client: 'Atlas Care Group', band: 'elevated', metric: 'Near miss ×3', delta: 'new' },
  { client: 'Summit Builders', band: 'stable', metric: 'TRIR 0.9', delta: '−0.2' },
]

export const BROKERS_JSON_LD = {
  '@context': 'https://schema.org',
  '@type': 'Service',
  name: 'Matcha for Brokers',
  url: 'https://hey-matcha.com/matcha-brokers',
  description:
    "A book-of-business intelligence layer for P&C brokers — exposure-weighted risk curve, workers' comp loss-control portfolio, and AI-drafted client outreach.",
  serviceType: 'Insurance brokerage software',
}

// ── Simplified pillars ─────────────────────────────────────────────────────

export const PILLARS: Pillar[] = [
  {
    id: 'risk-curve',
    number: '01',
    title: 'Risk Curve',
    tagline: 'See the renewal before it hits your desk.',
    description:
      'Walk into renewal prep already knowing which accounts are deteriorating — months before the carrier re-rates them.',
    highlight: 'A loss curve you can act on beats a loss run you can only read.',
  },
  {
    id: 'wc',
    number: '02',
    title: 'Loss Control',
    tagline: 'The whole book, ranked by who needs you.',
    description:
      'Triage your book in seconds, so the loss-control call goes to the account that needs it — not the one that shouts loudest.',
    highlight: 'One screen ranks every client by safety deterioration.',
  },
  {
    id: 'command',
    number: '03',
    title: 'Command Center',
    tagline: 'Every account, every signal, one queue.',
    description:
      'A flagged trend becomes a client conversation with the talking points already written — so outreach starts before the renewal does.',
    highlight: 'Every alert is a client conversation waiting to happen.',
  },
]
