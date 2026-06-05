import { useEffect, useMemo, useState } from 'react'
import { Bell, ClipboardCheck, Lock, MapPin, ScanLine, Scale, ShieldCheck, Sparkles } from 'lucide-react'
import { Card } from '../ui'
import { useComplianceData } from '../../hooks/compliance/useComplianceData'
import { useLocationDetail } from '../../hooks/compliance/useLocationDetail'
import { ComplianceLocationList } from './ComplianceLocationList'
import { ComplianceRequirementsTab } from './ComplianceRequirementsTab'
import { UpgradeUpsellCard } from '../UpgradeUpsellCard'

/**
 * Matcha-X read-only "taste" of Compliance (`compliance_lite`).
 *
 * Shows the real baseline the onboarding build wrote — per-location
 * requirements + a live summary — as the hero, then teases the locked Pro
 * tooling (monitoring, alerts, action plans, AI, wage-violations) behind a
 * blurred preview with an upgrade CTA. The Pro data endpoints are 403 for this
 * tier, so the blurred rows are an honest feature preview, not the user's data;
 * the sharp rows above them ARE the user's real upcoming changes.
 *
 * Dispatched from Compliance.tsx; the full tabbed Pro page is untouched.
 */
const noop = () => {}

export function ComplianceLiteView() {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const data = useComplianceData(selectedId, true)
  const detail = useLocationDetail(selectedId, true)

  // Auto-select the first location so the real requirements show immediately
  // instead of an empty "select a location" state.
  useEffect(() => {
    if (!selectedId && data.locations.length > 0) {
      setSelectedId(data.locations[0].id)
    }
  }, [selectedId, data.locations])

  const statesCovered = useMemo(
    () => new Set(data.locations.map((l) => (l.state || '').toUpperCase()).filter(Boolean)).size,
    [data.locations],
  )

  const selectedLoc = data.locations.find((l) => l.id === selectedId)
  const upcoming = data.summary?.upcoming_deadlines ?? []

  if (data.loading) {
    return <p className="text-sm text-zinc-500">Loading your compliance baseline…</p>
  }

  const stats: { label: string; value: number }[] = [
    { label: 'Locations', value: data.summary?.total_locations ?? data.locations.length },
    { label: 'Requirements', value: data.summary?.total_requirements ?? 0 },
    { label: 'States covered', value: statesCovered },
    { label: 'Upcoming changes', value: upcoming.length },
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
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

      {/* Real stat cards */}
      <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
        {stats.map((s) => (
          <Card key={s.label} className="px-4 py-3.5">
            <p className="text-2xl font-semibold text-zinc-100 tabular-nums">{s.value}</p>
            <p className="text-[11px] text-zinc-500 uppercase tracking-wide mt-0.5">{s.label}</p>
          </Card>
        ))}
      </div>

      {/* Hero: real requirements per location */}
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
          {selectedLoc ? (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <MapPin className="w-4 h-4 text-emerald-500" />
                <h2 className="text-base font-medium text-zinc-100">
                  {selectedLoc.city}, {selectedLoc.state}
                  {selectedLoc.name && <span className="text-zinc-500 ml-2 text-sm">({selectedLoc.name})</span>}
                </h2>
              </div>
              <ComplianceRequirementsTab
                requirements={detail.requirements}
                loading={detail.loading}
                onPin={noop}
                checkMessages={[]}
                facilityAttributes={selectedLoc.facility_attributes}
                readOnly
              />
            </div>
          ) : (
            <Card className="flex items-center justify-center h-40">
              <p className="text-sm text-zinc-600">Select a location to view its requirements</p>
            </Card>
          )}
        </div>
      </div>

      {/* Locked Pro tooling — blurred teaser */}
      <UnlockTeaser upcoming={upcoming} />
    </div>
  )
}

type UpcomingItem = { title: string; effective_date: string; days_until: number; location: string; category: string | null }

// What Pro unlocks — the rows blurred behind the upgrade wall. Honest preview
// copy (not the user's data); the real upcoming-change rows sit above, sharp.
const PREVIEW_ROWS: { icon: typeof Bell; title: string; sub: string; tag: string; tone: string }[] = [
  { icon: Bell, title: 'Minimum wage increase — action required', sub: 'Assign an owner and due date · 2 locations', tag: 'Alert', tone: 'text-amber-400' },
  { icon: Scale, title: 'Wage-violation detected for 3 employees', sub: 'Below local minimum after the July adjustment', tag: 'Risk', tone: 'text-red-400' },
  { icon: ClipboardCheck, title: 'New poster required: CA Minimum Wage 2026', sub: 'Auto-generated and tracked per location', tag: 'Posters', tone: 'text-sky-400' },
  { icon: ScanLine, title: 'Handbook policy gap — meal & rest breaks', sub: 'AI flagged 4 sections to update', tag: 'AI', tone: 'text-violet-400' },
]

function UnlockTeaser({ upcoming }: { upcoming: UpcomingItem[] }) {
  const real = upcoming.slice(0, 2)

  return (
    <Card className="p-0 overflow-hidden border-emerald-900/30">
      <div className="px-5 py-3 border-b border-zinc-800/60 bg-emerald-900/10 flex items-center gap-2">
        <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
        <h3 className="text-xs font-semibold uppercase tracking-wider text-emerald-300">
          Live monitoring &amp; tools
        </h3>
        <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-zinc-800/80 border border-zinc-700 px-2 py-0.5 text-[10px] font-medium text-zinc-300">
          <Lock className="w-2.5 h-2.5" /> Pro
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5">
        {/* Left: real upcoming (sharp) + blurred Pro previews under a fade + CTA */}
        <div className="lg:col-span-3 relative p-4 border-b lg:border-b-0 lg:border-r border-zinc-800/60">
          {real.length > 0 && (
            <>
              <p className="text-[11px] text-zinc-500 uppercase tracking-wide mb-2">We're already tracking these for you</p>
              <div className="space-y-2 mb-3">
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

          {/* Blurred preview rows — feature teaser */}
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
            {/* fade + lock overlay */}
            <div className="absolute inset-x-0 bottom-0 h-28 bg-gradient-to-t from-zinc-900 via-zinc-900/80 to-transparent" />
            <div className="absolute inset-0 flex items-end justify-center pb-1">
              <span className="inline-flex items-center gap-1.5 text-xs text-zinc-400">
                <Lock className="w-3.5 h-3.5" /> + live monitoring, action plans &amp; AI flags
              </span>
            </div>
          </div>
        </div>

        {/* Right: the actual upgrade CTA */}
        <div className="lg:col-span-2 p-4">
          <UpgradeUpsellCard
            source="compliance_lite:teaser"
            title="Unlock full Compliance"
            pitch="You're seeing the read-only baseline. Pro adds live monitoring as the law changes, assignable action plans, AI policy answers, and wage-violation detection."
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
