import { useState, useCallback, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Button } from '../../components/ui'
import { useComplianceData } from '../../hooks/compliance/useComplianceData'
import { useLocationDetail } from '../../hooks/compliance/useLocationDetail'
import { useComplianceCheck } from '../../hooks/compliance/useComplianceCheck'
import { ComplianceRiskCockpit } from '../../components/compliance/ComplianceRiskCockpit'
import { useRiskSummary } from '../../hooks/compliance/useRiskSummary'
import { ComplianceLocationList } from '../../components/compliance/ComplianceLocationList'
import { ComplianceLocationModal } from '../../components/compliance/ComplianceLocationModal'
import { ComplianceRequirementsTab } from '../../components/compliance/ComplianceRequirementsTab'
import { ComplianceAlertsTab } from '../../components/compliance/ComplianceAlertsTab'
import { ComplianceUpcomingTab } from '../../components/compliance/ComplianceUpcomingTab'
import { ComplianceHistoryTab } from '../../components/compliance/ComplianceHistoryTab'
import { CompliancePostersTab } from '../../components/compliance/CompliancePostersTab'
import { ComplianceCredentialsTab } from '../../components/compliance/ComplianceCredentialsTab'
import { ComplianceScanProgress } from '../../components/compliance/ComplianceScanProgress'
import PendingResearchPanel from '../../components/compliance/PendingResearchPanel'
import { FacilityProfileBanner } from '../../components/compliance/FacilityProfileBanner'
import { RegulatoryQuickAsk } from '../../components/compliance/RegulatoryQuickAsk'
import { PayerPolicyNavigator } from '../../components/compliance/PayerPolicyNavigator'
import { ProtocolAnalysis } from '../../components/compliance/ProtocolAnalysis'
import { PolicyDrafter } from '../../components/compliance/PolicyDrafter'
import { updateAlertActionPlan } from '../../api/compliance'
import { useMe } from '../../hooks/useMe'
import { ComplianceLiteView } from '../../components/compliance/ComplianceLiteView'
import { CLINICAL_ENTITY_TYPES } from '../../types/compliance'
import type { BusinessLocation, LocationCreate, ComplianceActionPlanUpdate } from '../../types/compliance'

type Tab = 'overview' | 'requirements' | 'credentials' | 'alerts' | 'upcoming' | 'history' | 'posters' | 'payer-policies' | 'protocol-analysis' | 'policy-drafting'

const TABS: { value: Tab; label: string }[] = [
  { value: 'overview', label: 'Overview' },
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

// Payer/protocol/policy tabs only apply to clinical-care facilities. A dental
// office, pharmacy, or lab never sees them (a dental office can carry payer
// contracts and still not need payer policies — the gate is the entity type).
const CLINICAL_TABS: Tab[] = ['payer-policies', 'protocol-analysis', 'policy-drafting']

// Route gate admits compliance OR compliance_lite. Dispatch here: full
// `compliance` (Pro) → the tabbed page below; the Matcha-X read-only taste
// (`compliance_lite` only) → a purpose-built view of the baseline + a teaser
// of the locked Pro tooling (avoids bending the Pro tabs into a thin shell).
export default function Compliance() {
  const { hasFeature, loading } = useMe()
  if (loading) return null
  if (hasFeature('compliance_lite') && !hasFeature('compliance')) {
    return <ComplianceLiteView />
  }
  return <ComplianceFull />
}

function ComplianceFull() {
  const [searchParams] = useSearchParams()
  const [tab, setTab] = useState<Tab>('overview')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [showModal, setShowModal] = useState(false)
  const [editingLocation, setEditingLocation] = useState<BusinessLocation | null>(null)
  const [saving, setSaving] = useState(false)
  // A cited requirement to focus when opened from the "Ask" sources. The title
  // rides along as the fallback when the catalog row isn't in the location's
  // materialized list.
  const [targetReq, setTargetReq] = useState<{ id: string; title?: string | null } | null>(null)

  // Open a requirement cited by the regulatory Q&A: jump to the Requirements
  // tab (selecting a location if none is), and mark the row to focus.
  const openSourceRequirement = useCallback((requirementId: string, title?: string | null) => {
    setTab('requirements')
    setTargetReq({ id: requirementId, title })
  }, [])

  const data = useComplianceData(selectedId)
  const detail = useLocationDetail(selectedId)
  const risk = useRiskSummary()

  const onCheckComplete = useCallback(() => {
    detail.refetch()
    data.refreshAll()
    risk.refetch()
  }, [detail, data, risk])

  const check = useComplianceCheck(onCheckComplete)

  // Clinical-tab gate: only a clinical-care facility sees payer/protocol/policy.
  const isClinical = data.locations.some(
    (l) => l.is_active && !!l.facility_attributes?.entity_type
      && CLINICAL_ENTITY_TYPES.has(l.facility_attributes.entity_type),
  )
  const visibleTabs = isClinical ? TABS : TABS.filter((t) => !CLINICAL_TABS.includes(t.value))

  // Deep-link support
  const [deepLinked, setDeepLinked] = useState(false)
  useEffect(() => {
    if (deepLinked || data.loading || data.locations.length === 0) return
    const paramLocationId = searchParams.get('location_id')
    const paramTab = searchParams.get('tab') as Tab | null
    if (paramLocationId && data.locations.find((l) => l.id === paramLocationId)) {
      setSelectedId(paramLocationId)
      // Auto-switch to a location-contextual tab so the detail panel is visible
      if (!paramTab) {
        setTab('requirements')
      }
    }
    if (paramTab && visibleTabs.some((t) => t.value === paramTab)) {
      setTab(paramTab)
    }
    setDeepLinked(true)
  }, [data.loading, data.locations, searchParams, deepLinked])

  // Load jurisdictions when modal opens
  useEffect(() => {
    if (showModal && data.jurisdictions.length === 0) {
      data.loadJurisdictions()
    }
  }, [showModal, data])

  // The Requirements tab needs a selected location; if a source was opened from
  // the "Ask" box without one, select the first.
  useEffect(() => {
    if (targetReq && !selectedId && data.locations.length > 0) {
      setSelectedId(data.locations[0].id)
    }
  }, [targetReq, selectedId, data.locations])

  // Picking a location by hand retires any pending citation. A location with no
  // requirements can never consume one (the tab can't tell "empty because none"
  // from "empty because still fetching"), and an armed target would otherwise
  // fire its title-search at whatever location is opened next.
  function handleSelectLocation(locId: string | null) {
    setTargetReq(null)
    setSelectedId(locId)
  }

  async function handleLocationSubmit(formData: LocationCreate, editId?: string) {
    setSaving(true)
    try {
      if (editId) {
        await data.updateLocation(editId, formData)
      } else {
        const loc = await data.createLocation(formData)
        setSelectedId(loc.id)
      }
      setShowModal(false)
      setEditingLocation(null)
    } finally { setSaving(false) }
  }

  function handleEdit(loc: BusinessLocation) {
    setEditingLocation(loc)
    setShowModal(true)
  }

  async function handleDelete(locId: string) {
    await data.deleteLocation(locId)
    if (selectedId === locId) setSelectedId(null)
  }

  async function handleAlertAction(alertId: string, action: 'read' | 'dismiss') {
    if (action === 'read') await data.markAlertRead(alertId)
    else await data.dismissAlert(alertId)
  }

  async function handleUpdateActionPlan(alertId: string, plan: ComplianceActionPlanUpdate) {
    await updateAlertActionPlan(alertId, plan)
    await data.loadAlerts('unread')
  }

  async function handlePinRequirement(reqId: string, isPinned: boolean) {
    await data.togglePin(reqId, isPinned)
    detail.loadRequirements()
  }

  const selectedLoc = data.locations.find((l) => l.id === selectedId)

  if (data.loading) return <p className="text-sm text-zinc-500">Loading...</p>

  return (
    // One frame around the whole surface, matching Legal Pilot
    // (LegalDefense/index.tsx:80). Before this, only the location tabs were
    // framed (see the grid below) while the header, ask box and the entire
    // overview cockpit sat bare on AppLayout's canvas — so #1e1e1e showed
    // through every gap between the near-black cards, which is what read as a
    // brown page. The canvas is now zinc-950 and #1e1e1e survives only as the
    // gutter outside the frame. Height is left to the content: the action
    // queue runs long, and a viewport-locked console would trap it in a
    // cramped scroller.
    <div className="overflow-hidden rounded-xl border border-white/[0.06] bg-zinc-950">
      {/* Masthead. The subtitle was set in LABEL — uppercase and letter-spaced,
          which is right for a two-word field label and wrong for a sentence:
          sixty characters of tracked caps is slow to read and shouts. It now
          uses the editorial voice the rest of the app headers already speak
          (see IRList.tsx) — light sans headline, Fraunces italic beneath. */}
      <div className="border-b border-white/[0.06] px-5 py-4">
        <h1 className="text-2xl font-light tracking-tight text-zinc-50">Compliance</h1>
        <p
          className="mt-1 text-sm italic text-zinc-500"
          style={{ fontFamily: 'Fraunces, Georgia, serif' }}
        >
          Jurisdictional requirements, alerts, and location management.
        </p>
      </div>

      {/* Regulatory Q&A */}
      <div className="border-b border-white/[0.06] px-5 py-4">
        <RegulatoryQuickAsk locationId={selectedId} onOpenSource={openSourceRequirement} />
      </div>

      {/* Tab nav. These were <Button variant=secondary|ghost> — chunky pills
          standing in for tabs, which is what made the head of the page feel
          heavy. Same treatment Legal Pilot uses for its inner tabs. */}
      <div className="flex items-center gap-1 overflow-x-auto border-b border-white/[0.06] px-5 py-1.5">
        {visibleTabs.map((t) => (
          <button
            key={t.value}
            type="button"
            onClick={() => setTab(t.value)}
            className={`shrink-0 rounded px-2 py-1 font-mono text-[10px] uppercase tracking-[0.15em] transition-colors ${
              tab === t.value
                ? 'bg-white/[0.06] text-zinc-100'
                : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            {t.label}
            {t.value === 'alerts' && data.alerts.length > 0 && (
              <span className="ml-1.5 tabular-nums text-zinc-500">{data.alerts.length}</span>
            )}
          </button>
        ))}
      </div>

      <div className="p-5">
      {/* Overview tab — the manager risk cockpit (no location context needed) */}
      {tab === 'overview' && (
        <ComplianceRiskCockpit
          riskSummary={risk.data}
          loading={risk.loading}
          pinnedReqs={data.pinnedRequirements}
          onOpenAlerts={() => setTab('alerts')}
          onUpdateActionPlan={handleUpdateActionPlan}
          onActioned={() => { risk.refetch(); data.loadAlerts('unread') }}
        />
      )}

      {/* Certifications & Licenses (company-level, no location context) */}
      {tab === 'credentials' && (
        <ComplianceCredentialsTab companyId={searchParams.get('company_id') || undefined} />
      )}

      {/* Location-contextual tabs. This grid used to carry the page's only
          frame; the page frame now provides it, so it keeps the split and its
          divider but drops the border/bg that would nest a frame in a frame. */}
      {tab !== 'overview' && tab !== 'credentials' && (
        <div className="-m-5 md:grid md:grid-cols-3">
          {/* Left: location list */}
          <div className="border-b border-white/[0.06] p-4 md:col-span-1 md:border-b-0 md:border-r">
            <ComplianceLocationList
              locations={data.locations}
              selectedId={selectedId}
              onSelect={handleSelectLocation}
              onEdit={handleEdit}
              onDelete={handleDelete}
              onAdd={() => { setEditingLocation(null); setShowModal(true) }}
              loading={data.loading}
            />
          </div>

          {/* Right: content area */}
          <div className="p-4 md:col-span-2">
            {!selectedId ? (
              <div className="flex items-center justify-center h-40">
                <p className="text-sm text-zinc-600">Select a location to view details</p>
              </div>
            ) : (
              <div>
                {/* Location header */}
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <h2 className="text-base font-medium text-zinc-100">
                      {selectedLoc?.city}, {selectedLoc?.state}
                      {selectedLoc?.name && <span className="text-zinc-500 ml-2 text-sm">({selectedLoc.name})</span>}
                    </h2>
                    {selectedLoc && selectedLoc.employee_count > 0 && (
                      <p className="text-[11px] text-zinc-500 mt-0.5">{selectedLoc.employee_count} employees</p>
                    )}
                  </div>
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={check.scanning}
                    onClick={() => check.runCheck(selectedId!)}
                  >
                    {check.scanning ? 'Scanning...' : 'Run Compliance Check'}
                  </Button>
                </div>

                <FacilityProfileBanner
                  locationId={selectedId!}
                  facilityAttributes={selectedLoc?.facility_attributes}
                  onUpdated={() => data.loadLocations()}
                  allLocations={data.locations}
                  source={selectedLoc?.source}
                />

                <ComplianceScanProgress scanning={check.scanning} messages={check.messages} />

                {tab === 'requirements' && <PendingResearchPanel />}

                {tab === 'requirements' && (
                  <ComplianceRequirementsTab
                    requirements={detail.requirements}
                    loading={detail.loading}
                    onPin={handlePinRequirement}
                    checkMessages={check.messages}
                    facilityAttributes={selectedLoc?.facility_attributes}
                    targetReq={targetReq}
                    onTargetConsumed={() => setTargetReq(null)}
                  />
                )}
                {tab === 'alerts' && (
                  <ComplianceAlertsTab
                    alerts={data.alerts}
                    loading={false}
                    onMarkRead={(id) => handleAlertAction(id, 'read')}
                    onDismiss={(id) => handleAlertAction(id, 'dismiss')}
                    onUpdateActionPlan={handleUpdateActionPlan}
                  />
                )}
                {tab === 'upcoming' && (
                  <ComplianceUpcomingTab
                    legislation={detail.upcomingLegislation}
                    loading={detail.loading}
                  />
                )}
                {tab === 'history' && (
                  <ComplianceHistoryTab
                    checkLog={detail.checkLog}
                    loading={detail.loading}
                  />
                )}
                {tab === 'posters' && (
                  <CompliancePostersTab locationId={selectedId!} />
                )}
                {tab === 'payer-policies' && isClinical && (
                  <PayerPolicyNavigator
                    locationId={selectedId}
                    payerContracts={selectedLoc?.facility_attributes?.payer_contracts || []}
                  />
                )}
                {tab === 'protocol-analysis' && isClinical && (
                  <ProtocolAnalysis locationId={selectedId} />
                )}
                {tab === 'policy-drafting' && isClinical && (
                  <PolicyDrafter locationId={selectedId} />
                )}
              </div>
            )}
          </div>
        </div>
      )}

      </div>

      {/* Location modal */}
      <ComplianceLocationModal
        open={showModal}
        onClose={() => { setShowModal(false); setEditingLocation(null) }}
        editingLocation={editingLocation}
        jurisdictions={data.jurisdictions}
        onSubmit={handleLocationSubmit}
        saving={saving}
      />
    </div>
  )
}
