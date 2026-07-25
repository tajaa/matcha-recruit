import type { Pillar, RadarRow, RiskBand } from './types'

// ── Hero (kept from the original /brokers page) ────────────────────────────

export const BAND_COLOR: Record<RiskBand, string> = {
  critical: '#ff6b6b',
  elevated: '#f5b545',
  stable: '#6ee7a8',
}

// Same three words the real Accounts table uses (ClientTable.tsx `Status`
// column) — the marketing instrument borrows the product's own vocabulary
// rather than inventing new labels.
export const STATUS_LABEL: Record<RiskBand, string> = {
  critical: 'At Risk',
  elevated: 'Watch',
  stable: 'Healthy',
}

export const RADAR_ROWS: RadarRow[] = [
  { client: 'Northgate Logistics', band: 'critical', metric: 'TRIR 6.2', delta: '+1.4', trir: '6.2', premiumDelta: '+$34K' },
  { client: 'Cedar Valley Mfg', band: 'elevated', metric: 'Lost days 14', delta: '+5.0', trir: '3.4', premiumDelta: '+$18K' },
  { client: 'Harbor Foods Co', band: 'stable', metric: 'DART 1.1', delta: '−0.3', trir: '1.1', premiumDelta: '−$4K' },
  { client: 'Atlas Care Group', band: 'elevated', metric: 'Near miss ×3', delta: 'new', trir: '2.6', premiumDelta: '+$9K' },
  { client: 'Summit Builders', band: 'stable', metric: 'TRIR 0.9', delta: '−0.2', trir: '0.9', premiumDelta: '−$6K' },
]

// One illustrative sample book, held constant across the hero instrument and
// the money band so the numbers read as one coherent portfolio rather than
// two different demos. Directional only — see BOOK_MONEY.caveat.
export const TOTAL_ACCOUNTS = 24
export const TOTAL_EMPLOYEES = 1240

export const BOOK_MONEY = {
  expectedLoss: '$967K',
  expectedLossSub: `${TOTAL_ACCOUNTS} clients modeled · headcount`,
  pml99: '$3.4M',
  pml99Sub: '1-in-100-yr tail',
  premiumDelta: '+$34K',
  premiumDeltaSub: '~18pt mod increase · 1.62× sector median',
  commission: '$148K',
  commissionSub: 'across the placed book',
  adverseDev: '+$400K',
  adverseDevSub: 'reported $1.2M → ultimate $1.6M',
  caveat: 'Directional, not a priced actuarial estimate. Not a quote.',
}

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
      'Walk into renewal prep already knowing which accounts are deteriorating — months before the carrier re-rates them. Off-platform clients plot on the same curve, so the read covers your whole book, not just what runs on Matcha.',
    highlight: 'A loss curve you can act on beats a loss run you can only read.',
    accent: BAND_COLOR.critical,
  },
  {
    id: 'wc',
    number: '02',
    title: 'Loss Control',
    tagline: 'The whole book, ranked by who needs you.',
    description:
      'Triage your book in seconds, so the loss-control call goes to the account that needs it — not the one that shouts loudest.',
    highlight: 'One screen ranks every client by safety deterioration.',
    accent: BAND_COLOR.elevated,
  },
  {
    id: 'command',
    number: '03',
    title: 'Command Center',
    tagline: 'Every account, every signal, one queue.',
    description:
      'A flagged trend becomes a client conversation with the talking points already written — so outreach starts before the renewal does.',
    highlight: 'Every alert is a client conversation waiting to happen.',
    accent: BAND_COLOR.stable,
  },
  {
    id: 'submission',
    number: '04',
    title: 'Submission Packet',
    tagline: 'Walk into the carrier meeting already holding the file.',
    description:
      'Every account builds its own carrier-facing packet as it goes — loss data, readiness, your commentary — so taking an account to market is an export, not a week of assembling PDFs.',
    highlight: 'The terms-winning artifact — take it to market at renewal.',
    accent: BAND_COLOR.critical,
  },
  {
    id: 'pilot',
    number: '05',
    title: 'Broker Pilot',
    tagline: 'Ask the whole file a question.',
    description:
      'Drop in a loss run, a dec page, a competing quote — Broker Pilot reads it against everything already on file for that client and answers in grounded, cited observations, not a guess.',
    highlight: 'Every answer cites the record it came from.',
    accent: BAND_COLOR.elevated,
  },
]
