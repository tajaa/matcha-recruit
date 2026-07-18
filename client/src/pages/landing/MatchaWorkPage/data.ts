export const PILLARS: { id: string; title: string; caption: string; stats: { label: string; value: string }[] }[] = [
  {
    id: 'interviews',
    title: 'Voice Interviews',
    caption:
      'Gemini-powered live voice interviews with real-time transcription, language-proficiency scoring, and structured error analysis. Panel-ready reports the moment the call ends.',
    stats: [
      { label: 'Duration', value: '18:42' },
      { label: 'CEFR', value: 'C1' },
      { label: 'Confidence', value: '94%' },
    ],
  },
  {
    id: 'workspace',
    title: 'Document Workspace',
    caption:
      'Multi-threaded projects for compliance research, regulatory reasoning chains, and long-form drafting. Export to PDF or DOCX when you’re done.',
    stats: [
      { label: 'Threads', value: '12' },
      { label: 'Citations', value: '87' },
      { label: 'Drafts', value: '3' },
    ],
  },
]

export type Pillar = (typeof PILLARS)[number]

export const BAR_COUNT = 48

export const WORKSPACE_THREADS = [
  {
    title: 'CA meal period waivers',
    status: 'Drafting',
    lines: 842,
    color: '#d7ba7d',
    steps: [
      'Identify jurisdictions: CA (Labor Code §512)',
      'Applicable exemptions: healthcare waivers',
      'Waiver scope: shifts ≤6h, signed consent',
      'Revocation rights: 1-day written notice',
      'Cross-ref: Brinker v. Superior Court',
    ],
  },
  {
    title: 'NY paid sick leave analysis',
    status: 'Complete',
    lines: 1204,
    color: '#86efac',
    steps: [
      'Identify jurisdictions: NY state + NYC',
      'Accrual rate: 1h per 30h worked',
      'Caps: 40h (small), 56h (large)',
      'Carryover + payout rules',
      'Cross-ref: Labor Law §196-b',
    ],
  },
  {
    title: 'FLSA overtime memo',
    status: 'Research',
    lines: 612,
    color: '#9a8a70',
    steps: [
      'Identify classification: exempt vs. non-exempt',
      'Salary threshold: $58,656 (2024 rule)',
      'Duties test: executive, admin, professional',
      'State overlay: CA, WA, NY minimums',
      'Cross-ref: 29 CFR §541',
    ],
  },
]
