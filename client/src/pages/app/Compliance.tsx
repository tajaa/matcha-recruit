import { useState, useCallback, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Button } from '../../components/ui'
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
import { ComplianceScanProgress } from '../../components/compliance/ComplianceScanProgress'
import { FacilityProfileBanner } from '../../components/compliance/FacilityProfileBanner'
import { RegulatoryQuickAsk } from '../../components/compliance/RegulatoryQuickAsk'
import { PayerPolicyNavigator } from '../../components/compliance/PayerPolicyNavigator'
import { updateAlertActionPlan } from '../../api/compliance'
import type { BusinessLocation, LocationCreate, ComplianceActionPlanUpdate } from '../../types/compliance'

type Tab = 'overview' | 'requirements' | 'alerts' | 'upcoming' | 'history' | 'posters' | 'payer-policies'

const TABS: { value: Tab; label: string }[] = [
  { value: 'overview', label: 'Overview' },
  { value: 'requirements', label: 'Requirements' },
  { value: 'alerts', label: 'Alerts' },
  { value: 'upcoming', label: 'Upcoming' },
  { value: 'history', label: 'History' },
  { value: 'posters', label: 'Posters' },
  { value: 'payer-policies', label: 'Payer Policies' },
]

export default function Compliance() {
  const [searchParams] = useSearchParams()
  const [tab, setTab] = useState<Tab>('overview')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [showModal, setShowModal] = useState(false)
  const [editingLocation, setEditingLocation] = useState<BusinessLocation | null>(null)
  const [saving, setSaving] = useState(false)

  const data = useComplianceData(selectedId)
  const detail = useLocationDetail(selectedId)

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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 font-[Space_Grotesk] tracking-tight">Compliance</h1>
          <p className="mt-1 text-sm text-zinc-500">Jurisdictional requirements, alerts, and location management.</p>
        </div>
      </div>

      {/* Regulatory Q&A */}
      <RegulatoryQuickAsk locationId={selectedId} />

      {/* Tab nav */}
      <div className="flex items-center gap-1 mt-4 mb-5">
        {TABS.map((t) => (
          <Button key={t.value} variant={tab === t.value ? 'secondary' : 'ghost'} size="sm" onClick={() => setTab(t.value)}>
            {t.label}{t.value === 'alerts' && data.alerts.length > 0 ? ` (${data.alerts.length})` : ''}
          </Button>
        ))}
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

      {/* Location-contextual tabs */}
      {tab !== 'overview' && (
        <div className="grid grid-cols-3 gap-4">
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

                {tab === 'requirements' && (
                  <ComplianceRequirementsTab
                    requirements={detail.requirements}
                    loading={detail.loading}
                    onPin={handlePinRequirement}
                    checkMessages={check.messages}
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
                {tab === 'payer-policies' && (
                  <PayerPolicyNavigator
                    locationId={selectedId}
                    payerContracts={selectedLoc?.facility_attributes?.payer_contracts || []}
                  />
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
