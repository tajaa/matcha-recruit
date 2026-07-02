// Tenant-facing "What's New" feed. Static, code-shipped (like adminUpdates.ts):
// add an entry here when a feature lands, scope it to the tiers that can use it
// via `audiences` (companies.signup_source values), and every matching tenant
// sees it on /app/whats-new with an unseen badge in their sidebar.
//
// Keep entries answering four questions: what shipped, where to find it,
// whether it's included / an add-on / an upgrade, and why it matters.

export type TenantUpdateAvailability = 'included' | 'addon' | 'upgrade'

export type TenantUpdateLocation = {
  label: string
  /** In-app route. Omit when the location is inside a modal/panel with no URL. */
  to?: string
}

export type TenantUpdate = {
  id: string
  /** ISO date (yyyy-mm-dd) the feature shipped. Feed renders newest first. */
  date: string
  /** signup_source values that should see this entry. */
  audiences: string[]
  title: string
  summary: string
  whereToFind: TenantUpdateLocation[]
  availability: TenantUpdateAvailability
  whyItMatters: string
}

export const TENANT_UPDATES: TenantUpdate[] = [
  {
    id: 'lite-addons-panel',
    date: '2026-07-01',
    audiences: ['matcha_lite', 'matcha_lite_essentials'],
    title: 'Self-serve add-ons on your Company page',
    summary:
      'A new Add-ons section lets you turn optional capabilities on and off yourself — no sales call. Each add-on is a separate monthly subscription priced per employee, and you can cancel any time (it stays active until the end of the billing period).',
    whereToFind: [{ label: 'Company → Add-ons', to: '/app/company#addons' }],
    availability: 'included',
    whyItMatters:
      'You only pay for the capabilities you actually use, and you can try one for a single month without a contract change.',
  },
  {
    id: 'addon-voice-intake',
    date: '2026-07-01',
    audiences: ['matcha_lite', 'matcha_lite_essentials'],
    title: 'Voice dictation for incident reports',
    summary:
      'A Dictate button on the new-incident form records a spoken account and pre-fills the description, reporter, date, location, and witnesses for you to review before submitting. Nothing is filed automatically — you always confirm the final record.',
    whereToFind: [
      { label: 'Incidents → New Incident → Dictate' },
      { label: 'Enable it under Company → Add-ons', to: '/app/company#addons' },
    ],
    availability: 'addon',
    whyItMatters:
      'Frontline reports get captured in the reporter’s own words minutes after the event, instead of being retyped from memory at the end of a shift — faster filing and fewer omissions on what becomes a legal record.',
  },
  {
    id: 'addon-hris-sync',
    date: '2026-07-01',
    audiences: ['matcha_lite'],
    title: 'HRIS roster sync',
    summary:
      'Connect your HRIS (Rippling, BambooHR, ADP, QuickBooks, and more) and keep the employee roster in sync automatically instead of re-uploading CSVs when people join or leave.',
    whereToFind: [
      { label: 'Employees → Sync from HRIS', to: '/app/employees' },
      { label: 'Enable it under Company → Add-ons', to: '/app/company#addons' },
    ],
    availability: 'addon',
    whyItMatters:
      'Incident insights, OSHA logs, and headcount-based views are only as good as the roster behind them — syncing removes the stale-roster gap between HR changes and your safety records.',
  },
  {
    id: 'addon-handbook-watch',
    date: '2026-07-01',
    audiences: ['matcha_lite', 'matcha_lite_essentials'],
    title: 'Handbook Watch — scheduled freshness monitoring',
    summary:
      'We periodically re-check your published handbooks against current law and email you when a policy goes stale. The manual freshness check on each handbook stays free — this add-on makes it automatic.',
    whereToFind: [
      { label: 'Handbooks → open a handbook → Freshness panel', to: '/app/handbooks' },
      { label: 'Enable it under Company → Add-ons', to: '/app/company#addons' },
    ],
    availability: 'addon',
    whyItMatters:
      'Employment law changes on legislative calendars, not on your review schedule — automatic monitoring catches outdated policies before an employee dispute does.',
  },
  {
    id: 'essentials-lite-upgrade',
    date: '2026-07-01',
    audiences: ['matcha_lite_essentials'],
    title: 'Upgrade to Matcha Lite from inside the app',
    summary:
      'Essentials can now upgrade to full Matcha Lite self-serve. Upgrading unlocks the employee roster (CSV import and directory), OSHA 300/301/300A logs, and the roster-linked incident insight suite. Your existing incidents and handbooks carry over untouched, and the old subscription is replaced automatically.',
    whereToFind: [
      { label: 'Upgrade panel at the bottom of the sidebar' },
      { label: 'Locked OSHA Logs / Employees entries open the same panel' },
    ],
    availability: 'upgrade',
    whyItMatters:
      'OSHA recordkeeping applies to most employers with more than 10 employees — the upgrade gets you compliant logs plus per-person incident history without re-registering or re-entering data.',
  },
  {
    id: 'compliance-four-pillars',
    date: '2026-07-01',
    audiences: ['matcha_compliance'],
    title: 'Your workspace now covers four pillars',
    summary:
      'Matcha Compliance bundles four tools: jurisdictional compliance monitoring, the handbook audit, policy management, and credential tracking with an employee roster. All four are live in your sidebar.',
    whereToFind: [
      { label: 'Compliance', to: '/app/compliance' },
      { label: 'Handbook Audit', to: '/app/resources/handbook-audit' },
      { label: 'Policy Management', to: '/app/policies' },
      { label: 'Credentialing', to: '/app/credential-templates' },
    ],
    availability: 'included',
    whyItMatters:
      'Jurisdiction requirements, the policies that satisfy them, and the credentials that prove them live in one place — no cross-referencing spreadsheets across tools.',
  },
]

/** Entries visible to a tenant, newest first. */
export function updatesForSource(source: string | null | undefined): TenantUpdate[] {
  if (!source) return []
  return TENANT_UPDATES
    .filter((u) => u.audiences.includes(source))
    .sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0))
}

// Seen-state: a per-user localStorage set of entry ids. Id-based (not
// date-based) so backfilling an entry with an older date still badges.
function seenKey(userId: string): string {
  return `matcha_whats_new_seen_${userId}`
}

function getSeenIds(userId: string): Set<string> {
  try {
    const raw = localStorage.getItem(seenKey(userId))
    return new Set(raw ? (JSON.parse(raw) as string[]) : [])
  } catch {
    return new Set()
  }
}

export function unseenTenantUpdatesCount(
  userId: string,
  source: string | null | undefined,
): number {
  const seen = getSeenIds(userId)
  return updatesForSource(source).filter((u) => !seen.has(u.id)).length
}

export function markTenantUpdatesSeen(
  userId: string,
  source: string | null | undefined,
): void {
  const seen = getSeenIds(userId)
  for (const u of updatesForSource(source)) seen.add(u.id)
  localStorage.setItem(seenKey(userId), JSON.stringify([...seen]))
}
