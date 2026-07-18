// This page already carried the Legal-Pilot frame classes on its Locations
// tab, same half-framed state Compliance was in: one tab framed, the other
// bare on the app canvas. PANEL was bg-zinc-950 — correct on the bare canvas,
// wrong once the whole page frame (below) is itself zinc-950 and PANEL would
// dissolve into it. Lifted to zinc-900/40, same as Compliance/Dashboard/
// Onboarding.
export const PANEL = 'rounded-lg border border-white/[0.06] bg-zinc-900/40 p-5'

export const SIZE_OPTIONS = [
  { value: '', label: 'Not set' },
  { value: 'startup', label: 'Startup (1-50)' },
  { value: 'mid', label: 'Mid-size (51-500)' },
  { value: 'enterprise', label: 'Enterprise (500+)' },
]

export const ARRANGEMENT_OPTIONS = [
  { value: '', label: 'Not set' },
  { value: 'onsite', label: 'On-site' },
  { value: 'hybrid', label: 'Hybrid' },
  { value: 'remote', label: 'Remote' },
]

export const EMPLOYMENT_TYPE_OPTIONS = [
  { value: '', label: 'Not set' },
  { value: 'full_time', label: 'Full-time' },
  { value: 'part_time', label: 'Part-time' },
  { value: 'contract', label: 'Contract' },
]
