import { useState, useEffect, useCallback } from 'react'
import { useToast } from '../../../components/ui'
import { api } from '../../../api/client'
import { fetchLocations, createLocation, updateLocation, deleteLocation, fetchJurisdictions } from '../../../api/compliance/compliance'
import { ComplianceLocationModal } from '../../../components/compliance/ComplianceLocationModal'
import { useMe } from '../../../hooks/useMe'
import type { BusinessLocation, LocationCreate, JurisdictionOption } from '../../../types/compliance'
import { ProfileTab } from './CompanySettings/ProfileTab'
import { LocationsTab } from './CompanySettings/LocationsTab'
import type { Tab, CompanyData } from './CompanySettings/types'

export default function CompanySettings() {
  const { me, hasFeature } = useMe()
  const { toast } = useToast()
  const [tab, setTab] = useState<Tab>('profile')
  // Lite-family tenants manage their paid add-ons here (/app/company#addons).
  const isLiteFamily =
    me?.profile?.signup_source === 'matcha_lite' ||
    me?.profile?.signup_source === 'matcha_lite_essentials'
  const showAddons = isLiteFamily && hasFeature('incidents')
  const [company, setCompany] = useState<CompanyData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Locations state
  const [locations, setLocations] = useState<BusinessLocation[]>([])
  const [locationsLoading, setLocationsLoading] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [showModal, setShowModal] = useState(false)
  const [editingLocation, setEditingLocation] = useState<BusinessLocation | null>(null)
  const [saving, setSaving] = useState(false)
  const [jurisdictions, setJurisdictions] = useState<JurisdictionOption[]>([])

  const loadCompany = useCallback(async () => {
    try {
      const data = await api.get<CompanyData>('/companies/me')
      setCompany(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load company')
    } finally {
      setLoading(false)
    }
  }, [])

  const loadLocations = useCallback(async () => {
    setLocationsLoading(true)
    try {
      const locs = await fetchLocations()
      setLocations(locs)
    } finally {
      setLocationsLoading(false)
    }
  }, [])

  useEffect(() => { loadCompany() }, [loadCompany])

  useEffect(() => {
    if (tab === 'locations' && locations.length === 0) {
      loadLocations()
    }
  }, [tab, locations.length, loadLocations])

  async function updateField(field: string, value: string | string[]) {
    if (!company) return
    const updated = await api.patch<CompanyData>(`/companies/${company.id}`, { [field]: value || null })
    setCompany(updated)
  }

  async function handleLocationSubmit(formData: LocationCreate, editId?: string) {
    setSaving(true)
    try {
      if (editId) {
        await updateLocation(editId, formData)
      } else {
        const loc = await createLocation(formData)
        setSelectedId(loc.id)
      }
      await loadLocations()
      setShowModal(false)
      setEditingLocation(null)
    } finally {
      setSaving(false)
    }
  }

  async function handleDeleteLocation(locId: string) {
    try {
      await deleteLocation(locId)
      if (selectedId === locId) setSelectedId(null)
      await loadLocations()
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to delete location', 'error')
    }
  }

  function handleEditLocation(loc: BusinessLocation) {
    setEditingLocation(loc)
    setShowModal(true)
  }

  if (loading) return <p className="text-sm text-zinc-500">Loading...</p>
  if (error) return <p className="text-sm text-red-400">{error}</p>
  if (!company) return <p className="text-sm text-zinc-500">No company found.</p>

  return (
    // Same page frame as Compliance/Dashboard/Onboarding: one bg-zinc-950
    // shell, masthead + tab bands, padded content below.
    <div className="overflow-hidden rounded-xl border border-white/[0.06] bg-zinc-950">
      <div className="border-b border-white/[0.06] px-5 py-4">
        <h1 className="text-2xl font-light tracking-tight text-zinc-50">Company</h1>
        <p className="mt-1 text-sm italic text-zinc-500" style={{ fontFamily: 'Fraunces, Georgia, serif' }}>
          Manage your company profile and locations.
        </p>
      </div>

      {/* Tabs — was a bordered pill group floating below the header; now the
          same mono tab-band treatment as Compliance/Legal Pilot, since this
          page sits in the same kind of frame now. */}
      <div className="flex items-center gap-1 border-b border-white/[0.06] px-5 py-1.5">
        {(['profile', 'locations'] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`rounded px-2 py-1 font-mono text-[10px] uppercase tracking-[0.15em] transition-colors ${
              tab === t
                ? 'bg-white/[0.06] text-zinc-100'
                : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            {t === 'profile' ? 'Profile' : `Locations${locations.length > 0 ? ` (${locations.length})` : ''}`}
          </button>
        ))}
      </div>

      <div className="p-5 space-y-5">

      {/* Profile Tab */}
      {tab === 'profile' && (
        <ProfileTab
          company={company}
          setCompany={setCompany}
          updateField={updateField}
          showAddons={showAddons}
        />
      )}

      {/* Locations Tab */}
      {tab === 'locations' && (
        <LocationsTab
          locations={locations}
          locationsLoading={locationsLoading}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onEdit={handleEditLocation}
          onDelete={handleDeleteLocation}
          onAdd={() => {
            setEditingLocation(null)
            setShowModal(true)
            if (jurisdictions.length === 0) {
              fetchJurisdictions().then(setJurisdictions)
            }
          }}
          readOnly={!hasFeature('compliance')}
          loadLocations={loadLocations}
        />
      )}

      </div>

      <ComplianceLocationModal
        open={showModal}
        onClose={() => { setShowModal(false); setEditingLocation(null) }}
        editingLocation={editingLocation}
        jurisdictions={jurisdictions}
        onSubmit={handleLocationSubmit}
        saving={saving}
      />
    </div>
  )
}
