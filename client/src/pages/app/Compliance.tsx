import { useState, useCallback, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Lock } from 'lucide-react'
import { Button } from '../../components/ui'
import { useMe } from '../../hooks/useMe'
import { UpgradeUpsellCard } from '../../components/UpgradeUpsellCard'
import { useComplianceData } from '../../hooks/compliance/useComplianceData'
import { useLocationDetail } from '../../hooks/compliance/useLocationDetail'
import { useComplianceCheck } from '../../hooks/compliance/useComplianceCheck'
import { ComplianceOverviewTab } from '../../components/compliance/ComplianceOverviewTab'
import { ComplianceLocationList } from '../../components/compliance/ComplianceLocationList'
import { ComplianceLocationModal } from '../../components/compliance/ComplianceLocationModal'
import { ComplianceRequirementsTab } from '../../components/compliance/ComplianceRequirementsTab'
import { ComplianceAlertsTab } from '../../components/compliance/ComplianceAlertsTab'
import { ComplianceUpcomingTab } from '../../components/compliance/ComplianceUpcomingTab'
import { ComplianceHistoryTab } from '../../components/compliance/ComplianceHistoryTab'
import { CompliancePostersTab } from '../../components/compliance/CompliancePostersTab'
import { ComplianceCredentialsTab } from '../../components/compliance/ComplianceCredentialsTab'
import { ComplianceScanProgress } from '../../components/compliance/ComplianceScanProgress'
import { FacilityProfileBanner } from '../../components/compliance/FacilityProfileBanner'
import { RegulatoryQuickAsk } from '../../components/compliance/RegulatoryQuickAsk'
import { PayerPolicyNavigator } from '../../components/compliance/PayerPolicyNavigator'
import { ProtocolAnalysis } from '../../components/compliance/ProtocolAnalysis'
import { PolicyDrafter } from '../../components/compliance/PolicyDrafter'
import { updateAlertActionPlan } from '../../api/compliance'
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

// Tabs that belong to full Compliance (Pro). On the Matcha-X read-only taste
// (`compliance_lite`) these stay visible but locked behind an upgrade CTA — the
// read-only viewers (overview/requirements/upcoming) are the only live ones.
const PRO_TABS = new Set<Tab>([
  'credentials', 'alerts', 'history', 'posters', 'payer-policies', 'protocol-analysis', 'policy-drafting',
])

const PRO_TAB_PITCH: Partial<Record<Tab, string>> = {
  credentials: 'Track company certifications and license renewals with automatic expiry alerts.',
  alerts: 'Get monitored compliance alerts with assignable action plans as the law changes.',
  history: 'See the full audit trail of every compliance re-check for this location.',
  posters: 'Auto-generate and track the labor-law posters each location must display.',
  'payer-policies': 'Navigate payer contract requirements alongside your jurisdictional rules.',
  'protocol-analysis': 'AI analysis of your clinical/operational protocols against current law.',
  'policy-drafting': 'Draft compliant, jurisdiction-aware policies with AI.',
}

function ProLock({ tab }: { tab: Tab }) {
  return (
    <div className="max-w-md">
      <UpgradeUpsellCard
        source={`feature_gate:compliance:${tab}`}
        title="Unlock full Compliance"
        pitch={PRO_TAB_PITCH[tab] ?? 'This is part of full Compliance monitoring on Matcha Platform.'}
        bullets={[
          'Live re-research as laws change',
          'Monitored alerts + action plans',
          'Ask AI about any requirement',
          'Wage-violation detection',
        ]}
      />
    </div>
  )
}

export default function Compliance() {
  const [searchParams] = useSearchParams()
  const [tab, setTab] = useState<Tab>('overview')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [showModal, setShowModal] = useState(false)
  const [editingLocation, setEditingLocation] = useState<BusinessLocation | null>(null)
  const [saving, setSaving] = useState(false)

  // Matcha-X read-only taste: has the lite flag but not full `compliance`.
  const { hasFeature } = useMe()
  const isLite = hasFeature('compliance_lite') && !hasFeature('compliance')

  const data = useComplianceData(selectedId, isLite)
  const detail = useLocationDetail(selectedId, isLite)

  const onCheckComplete = useCallback(() => {
    detail.refetch()
    data.refreshAll()
  }, [detail, data])

  const check = useComplianceCheck(onCheckComplete)

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
    if (paramTab && TABS.some((t) => t.value === paramTab)) {
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
    <div>
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 sm:gap-0">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">Compliance</h1>
          <p className="mt-1 text-sm text-zinc-500">
            {isLite
              ? 'Your jurisdictional requirements baseline — read-only. Upgrade for monitoring, alerts and AI tools.'
              : 'Jurisdictional requirements, alerts, and location management.'}
          </p>
        </div>
      </div>

      {/* Regulatory Q&A (AI ask — full Compliance only) */}
      {!isLite && <RegulatoryQuickAsk locationId={selectedId} />}

      {/* Tab nav */}
      <div className="flex items-center gap-1 mt-4 mb-5">
        {TABS.map((t) => {
          const locked = isLite && PRO_TABS.has(t.value)
          return (
            <Button key={t.value} variant={tab === t.value ? 'secondary' : 'ghost'} size="sm" onClick={() => setTab(t.value)}>
              {locked && <Lock className="w-3 h-3 mr-1 text-zinc-500" />}
              {t.label}{t.value === 'alerts' && !isLite && data.alerts.length > 0 ? ` (${data.alerts.length})` : ''}
            </Button>
          )
        })}
      </div>

      {/* Overview tab (no location context needed) */}
      {tab === 'overview' && (
        <ComplianceOverviewTab
          summary={data.summary}
          alerts={data.alerts}
          pinnedReqs={data.pinnedRequirements}
          onViewAllAlerts={() => setTab('alerts')}
          onAlertAction={handleAlertAction}
        />
      )}

      {/* Certifications & Licenses (company-level, no location context) */}
      {tab === 'credentials' && (
        isLite
          ? <ProLock tab="credentials" />
          : <ComplianceCredentialsTab companyId={searchParams.get('company_id') || undefined} />
      )}

      {/* Pro tabs on the lite taste — locked, shown without needing a location */}
      {isLite && tab !== 'credentials' && PRO_TABS.has(tab) && (
        <div className="mt-2"><ProLock tab={tab} /></div>
      )}

      {/* Location-contextual tabs */}
      {tab !== 'overview' && tab !== 'credentials' && !(isLite && PRO_TABS.has(tab)) && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Left: location list */}
          <div className="col-span-1">
            <ComplianceLocationList
              locations={data.locations}
              selectedId={selectedId}
              onSelect={setSelectedId}
              onEdit={handleEdit}
              onDelete={handleDelete}
              onAdd={() => { setEditingLocation(null); setShowModal(true) }}
              loading={data.loading}
              readOnly={isLite}
            />
          </div>

          {/* Right: content area */}
          <div className="col-span-2">
            {!selectedId ? (
              <div className="flex items-center justify-center h-40 border border-zinc-800 rounded-lg">
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
                  {isLite ? (
                    <Button variant="ghost" size="sm" disabled title="Live re-checks are part of full Compliance (Pro)">
                      <Lock className="w-3 h-3 mr-1" />Run Compliance Check
                    </Button>
                  ) : (
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={check.scanning}
                      onClick={() => check.runCheck(selectedId!)}
                    >
                      {check.scanning ? 'Scanning...' : 'Run Compliance Check'}
                    </Button>
                  )}
                </div>

                <FacilityProfileBanner
                  locationId={selectedId!}
                  facilityAttributes={selectedLoc?.facility_attributes}
                  onUpdated={() => data.loadLocations()}
                  allLocations={data.locations}
                  source={selectedLoc?.source}
                  readOnly={isLite}
                />

                <ComplianceScanProgress scanning={check.scanning} messages={check.messages} />

                {tab === 'requirements' && (
                  <ComplianceRequirementsTab
                    requirements={detail.requirements}
                    loading={detail.loading}
                    onPin={handlePinRequirement}
                    checkMessages={check.messages}
                    facilityAttributes={selectedLoc?.facility_attributes}
                    readOnly={isLite}
                  />
                )}
                {tab === 'alerts' && !isLite && (
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
                {tab === 'history' && !isLite && (
                  <ComplianceHistoryTab
                    checkLog={detail.checkLog}
                    loading={detail.loading}
                  />
                )}
                {tab === 'posters' && !isLite && (
                  <CompliancePostersTab locationId={selectedId!} />
                )}
                {tab === 'payer-policies' && !isLite && (
                  <PayerPolicyNavigator
                    locationId={selectedId}
                    payerContracts={selectedLoc?.facility_attributes?.payer_contracts || []}
                  />
                )}
                {tab === 'protocol-analysis' && !isLite && (
                  <ProtocolAnalysis locationId={selectedId} />
                )}
                {tab === 'policy-drafting' && !isLite && (
                  <PolicyDrafter locationId={selectedId} />
                )}
              </div>
            )}
          </div>
        </div>
      )}

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
