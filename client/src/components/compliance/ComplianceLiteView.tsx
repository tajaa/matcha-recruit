import { useEffect, useMemo, useState } from 'react'
import { Bell, ClipboardCheck, Lock, MapPin, ScanLine, Scale, ShieldCheck, Sparkles } from 'lucide-react'
import { Button, Card } from '../ui'
import { useComplianceData } from '../../hooks/compliance/useComplianceData'
import { useLocationDetail } from '../../hooks/compliance/useLocationDetail'
import { ComplianceLocationList } from './ComplianceLocationList'
import { ComplianceRequirementsTab } from './ComplianceRequirementsTab'
import PendingResearchPanel from './PendingResearchPanel'
import { ComplianceUpcomingTab } from './ComplianceUpcomingTab'
import { UpgradeUpsellCard } from '../UpgradeUpsellCard'

/**
 * Matcha-X read-only "taste" of Compliance (`compliance_lite`).
 *
 * Mirrors the Pro tabbed page so it reads as the full product, but only the
 * read-only tabs (Overview / Requirements / Upcoming) are live — they show the
 * REAL baseline the onboarding build wrote. Every Pro tab is visible but locked
 * and renders a blurred upgrade teaser. The Pro data endpoints are 403 for this
 * tier, so the blurred rows are an honest feature preview; the sharp content is
 * the user's real data. Dispatched from Compliance.tsx; the Pro page is
 * untouched.
 */
type LiteTab =
  | 'overview' | 'requirements' | 'credentials' | 'alerts' | 'upcoming'
  | 'history' | 'posters' | 'payer-policies' | 'protocol-analysis' | 'policy-drafting'

// Overview is folded into Requirements (a slim stats strip on top), so the lite
// tab bar drops the standalone Overview. Same labels/order as Pro otherwise.
const TABS: { value: LiteTab; label: string }[] = [
  { value: 'requirements', label: 'Requirements' },
  { value: 'credentials', label: 'Certifications & Licenses' },
  { value: 'alerts', label: 'Alerts' },
  { value: 'upcoming', label: 'Upcoming' },
  { value: 'history', label: 'History' },
  { value: 'posters', label: 'Posters' },
  { value: 'payer-policies', label: 'Payer Policies' },
  { value: 'protocol-analysis', label: 'Protocol Analysis' },
  { value: 'policy-drafting', label: 'Policy Drafting' },
]

// Tabs that are live (read-only) on the lite taste. Everything else is locked.
const LIVE_TABS = new Set<LiteTab>(['requirements', 'upcoming'])
const LOCATION_TABS = new Set<LiteTab>(['requirements', 'upcoming'])

const noop = () => {}

export function ComplianceLiteView() {
  const [tab, setTab] = useState<LiteTab>('requirements')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const data = useComplianceData(selectedId, true)
  const detail = useLocationDetail(selectedId, true)

  // Auto-select the first location so the contextual tabs show data immediately.
  useEffect(() => {
    if (!selectedId && data.locations.length > 0) setSelectedId(data.locations[0].id)
  }, [selectedId, data.locations])

  const statesCovered = useMemo(
    () => new Set(data.locations.map((l) => (l.state || '').toUpperCase()).filter(Boolean)).size,
    [data.locations],
  )

  const selectedLoc = data.locations.find((l) => l.id === selectedId)
  const summary = data.summary
  const upcoming = summary?.upcoming_deadlines ?? []

  if (data.loading) {
    return <p className="text-sm text-zinc-500">Loading your compliance baseline…</p>
  }

  const stats: { label: string; value: number }[] = [
    { label: 'Locations', value: summary?.total_locations ?? data.locations.length },
    { label: 'Requirements', value: summary?.total_requirements ?? 0 },
    { label: 'States covered', value: statesCovered },
    { label: 'Upcoming changes', value: upcoming.length },
  ]

  return (
    <div>
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-semibold text-zinc-100">Compliance</h1>
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-950/50 border border-emerald-800/40 px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-emerald-300/90">
              <ShieldCheck className="w-2.5 h-2.5" /> Baseline ready
            </span>
          </div>
          <p className="mt-1 text-sm text-zinc-500">
            Your jurisdictional requirements across {data.locations.length} location{data.locations.length === 1 ? '' : 's'},
            built from your offices. Upgrade for live monitoring, alerts and AI tools.
          </p>
        </div>
      </div>

      {/* Tab nav — same set as Pro; Pro-only tabs show a lock */}
      <div className="flex items-center gap-1 mt-4 mb-5 flex-wrap">
        {TABS.map((t) => {
          const locked = !LIVE_TABS.has(t.value)
          return (
            <Button key={t.value} variant={tab === t.value ? 'secondary' : 'ghost'} size="sm" onClick={() => setTab(t.value)}>
              {locked && <Lock className="w-3 h-3 mr-1 text-zinc-500" />}
              {t.label}
            </Button>
          )
        })}
      </div>

      {/* Overview folded in: a slim stats strip sits on top of Requirements */}
      {tab === 'requirements' && (
        <div className="flex items-stretch rounded-lg border border-zinc-800 bg-zinc-900/40 divide-x divide-zinc-800 mb-4 overflow-hidden">
          {stats.map((s) => (
            <div key={s.label} className="px-4 py-2.5 flex-1 min-w-0">
              <p className="text-[10px] text-zinc-500 uppercase tracking-wider truncate">{s.label}</p>
              <p className="text-base font-semibold text-zinc-100 tabular-nums mt-0.5">{s.value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Location-contextual live tabs */}
      {LOCATION_TABS.has(tab) && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="col-span-1">
            <ComplianceLocationList
              locations={data.locations}
              selectedId={selectedId}
              onSelect={setSelectedId}
              onEdit={noop}
              onDelete={noop}
              onAdd={noop}
              loading={data.loading}
              readOnly
            />
          </div>
          <div className="col-span-2">
            {!selectedLoc ? (
              <Card className="flex items-center justify-center h-40">
                <p className="text-sm text-zinc-600">Select a location to view details</p>
              </Card>
            ) : (
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <MapPin className="w-4 h-4 text-emerald-500" />
                  <h2 className="text-base font-medium text-zinc-100">
                    {selectedLoc.city}, {selectedLoc.state}
                    {selectedLoc.name && <span className="text-zinc-500 ml-2 text-sm">({selectedLoc.name})</span>}
                  </h2>
                </div>
                {tab === 'requirements' && <PendingResearchPanel />}
                {tab === 'requirements' && (
                  <ComplianceRequirementsTab
                    requirements={detail.requirements}
                    loading={detail.loading}
                    onPin={noop}
                    checkMessages={[]}
                    facilityAttributes={selectedLoc.facility_attributes}
                    readOnly
                    previewCategoryLimit={2}
                  />
                )}
                {tab === 'upcoming' && (
                  <ComplianceUpcomingTab legislation={detail.upcomingLegislation} loading={detail.loading} />
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Locked Pro tabs — blurred teaser */}
      {!LIVE_TABS.has(tab) && <UnlockTeaser tab={tab} upcoming={upcoming} />}
    </div>
  )
}

type UpcomingItem = { title: string; effective_date: string; days_until: number; location: string; category: string | null }

const TAB_PITCH: Partial<Record<LiteTab, string>> = {
  credentials: 'Track company certifications and license renewals with automatic expiry alerts.',
  alerts: 'Get monitored compliance alerts with assignable action plans as the law changes.',
  history: 'See the full audit trail of every compliance re-check for each location.',
  posters: 'Auto-generate and track the labor-law posters each location must display.',
  'payer-policies': 'Navigate payer contract requirements alongside your jurisdictional rules.',
  'protocol-analysis': 'AI analysis of your clinical/operational protocols against current law.',
  'policy-drafting': 'Draft compliant, jurisdiction-aware policies with AI.',
}

// Illustrative preview of the Pro tooling (not the user's data — those endpoints
// are 403 for lite). The sharp rows above ARE the user's real upcoming changes.
const PREVIEW_ROWS: { icon: typeof Bell; title: string; sub: string; tag: string; tone: string }[] = [
  { icon: Bell, title: 'Minimum wage increase — action required', sub: 'Assign an owner and due date · 2 locations', tag: 'Alert', tone: 'text-amber-400' },
  { icon: Scale, title: 'Wage-violation detected for 3 employees', sub: 'Below local minimum after the July adjustment', tag: 'Risk', tone: 'text-red-400' },
  { icon: ClipboardCheck, title: 'New poster required: CA Minimum Wage 2026', sub: 'Auto-generated and tracked per location', tag: 'Posters', tone: 'text-sky-400' },
  { icon: ScanLine, title: 'Handbook policy gap — meal & rest breaks', sub: 'AI flagged 4 sections to update', tag: 'AI', tone: 'text-violet-400' },
]

function UnlockTeaser({ tab, upcoming }: { tab: LiteTab; upcoming: UpcomingItem[] }) {
  const real = upcoming.slice(0, 2)
  const pitch = TAB_PITCH[tab] ?? 'Full Compliance monitoring on Matcha Platform.'

  return (
    <Card className="p-0 overflow-hidden border-emerald-900/30">
      <div className="px-5 py-3 border-b border-zinc-800/60 bg-emerald-900/10 flex items-center gap-2">
        <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
        <h3 className="text-xs font-semibold uppercase tracking-wider text-emerald-300">Live monitoring &amp; tools</h3>
        <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-zinc-800/80 border border-zinc-700 px-2 py-0.5 text-[10px] font-medium text-zinc-300">
          <Lock className="w-2.5 h-2.5" /> Pro
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5">
        {/* Real upcoming (sharp) + blurred Pro previews under a fade */}
        <div className="lg:col-span-3 relative p-4 border-b lg:border-b-0 lg:border-r border-zinc-800/60">
          {real.length > 0 && (
            <>
              <p className="text-[11px] text-zinc-500 uppercase tracking-wide mb-2">We're already tracking these for you</p>
              <div className="space-y-2 mb-4">
                {real.map((d, i) => (
                  <div key={i} className="flex items-center justify-between gap-3 rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2.5">
                    <div className="min-w-0">
                      <p className="text-sm text-zinc-200 truncate">{d.title}</p>
                      <p className="text-[11px] text-zinc-500 mt-0.5">{d.location} · {new Date(d.effective_date).toLocaleDateString()}</p>
                    </div>
                    <span className={`text-sm font-mono font-semibold shrink-0 ${d.days_until <= 30 ? 'text-red-400' : d.days_until <= 90 ? 'text-amber-400' : 'text-zinc-500'}`}>
                      {d.days_until <= 0 ? 'NOW' : `${d.days_until}d`}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}

          <div className="relative">
            <p className="text-[11px] text-zinc-500 uppercase tracking-wide mb-2">Unlock to act on them</p>
            <div className="space-y-2 blur-[3px] select-none pointer-events-none" aria-hidden="true">
              {PREVIEW_ROWS.map((r) => (
                <div key={r.title} className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2.5">
                  <r.icon className={`w-4 h-4 shrink-0 ${r.tone}`} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-zinc-200 truncate">{r.title}</p>
                    <p className="text-[11px] text-zinc-500 mt-0.5 truncate">{r.sub}</p>
                  </div>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 shrink-0">{r.tag}</span>
                </div>
              ))}
            </div>
            <div className="absolute inset-x-0 bottom-0 h-28 bg-gradient-to-t from-zinc-900 via-zinc-900/80 to-transparent" />
            <div className="absolute inset-0 flex items-end justify-center pb-1">
              <span className="inline-flex items-center gap-1.5 text-xs text-zinc-400">
                <Lock className="w-3.5 h-3.5" /> + live monitoring, action plans &amp; AI flags
              </span>
            </div>
          </div>
        </div>

        {/* Upgrade CTA */}
        <div className="lg:col-span-2 p-4">
          <UpgradeUpsellCard
            source={`compliance_lite:${tab}`}
            title="Unlock full Compliance"
            pitch={pitch}
            bullets={[
              'Live re-research when laws change',
              'Monitored alerts + action plans',
              'Ask AI about any requirement',
              'Wage-violation detection',
              'Posters + certification tracking',
            ]}
          />
        </div>
      </div>
    </Card>
  )
}
