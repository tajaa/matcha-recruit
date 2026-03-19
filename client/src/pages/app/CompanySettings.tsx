import { useState, useEffect, useCallback, useRef } from 'react'
import { Button, Card, Input, Select, Badge } from '../../components/ui'
import { api } from '../../api/client'
import { fetchLocations, createLocation, updateLocation, deleteLocation, fetchJurisdictions } from '../../api/compliance'
import { ComplianceLocationList } from '../../components/compliance/ComplianceLocationList'
import { ComplianceLocationModal } from '../../components/compliance/ComplianceLocationModal'
import { FacilityProfileBanner } from '../../components/compliance/FacilityProfileBanner'
import type { BusinessLocation, LocationCreate, JurisdictionOption } from '../../types/compliance'

type Tab = 'profile' | 'locations'

interface CompanyData {
  id: string
  name: string
  industry: string | null
  size: string | null
  logo_url: string | null
  headquarters_state: string | null
  headquarters_city: string | null
  work_arrangement: string | null
  default_employment_type: string | null
  healthcare_specialties: string[] | null
}

const SIZE_OPTIONS = [
  { value: '', label: 'Not set' },
  { value: 'startup', label: 'Startup (1-50)' },
  { value: 'mid', label: 'Mid-size (51-500)' },
  { value: 'enterprise', label: 'Enterprise (500+)' },
]

const ARRANGEMENT_OPTIONS = [
  { value: '', label: 'Not set' },
  { value: 'onsite', label: 'On-site' },
  { value: 'hybrid', label: 'Hybrid' },
  { value: 'remote', label: 'Remote' },
]

const EMPLOYMENT_TYPE_OPTIONS = [
  { value: '', label: 'Not set' },
  { value: 'full_time', label: 'Full-time' },
  { value: 'part_time', label: 'Part-time' },
  { value: 'contract', label: 'Contract' },
]

type EditableFieldProps = {
  label: string
  value: string | null
  onSave: (value: string) => Promise<void>
  type?: string
}

function EditableField({ label, value, onSave, type = 'text' }: EditableFieldProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value ?? '')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')

  async function handleBlur() {
    const trimmed = draft.trim()
    if (trimmed === (value ?? '')) {
      setEditing(false)
      return
    }
    setSaving(true)
    setSaveError('')
    try {
      await onSave(trimmed)
      setEditing(false)
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  if (editing) {
    return (
      <div>
        <dt className="text-zinc-500 text-xs">{label}</dt>
        <dd className="mt-1">
          <Input
            label=""
            type={type}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={handleBlur}
            onKeyDown={(e) => { if (e.key === 'Enter') handleBlur() }}
            autoFocus
            disabled={saving}
            className="!py-1 text-sm"
          />
          {saveError && <p className="text-[10px] text-red-400 mt-0.5">{saveError}</p>}
        </dd>
      </div>
    )
  }

  return (
    <div
      className="cursor-pointer group rounded-md px-2 py-1.5 -mx-2 hover:bg-zinc-800/50 transition-colors"
      onClick={() => { setDraft(value ?? ''); setEditing(true) }}
    >
      <dt className="text-zinc-500 text-xs">{label}</dt>
      <dd className="text-zinc-200 text-sm mt-0.5 flex items-center justify-between gap-2">
        <span>{value || <span className="text-zinc-600 italic">Not set</span>}</span>
        <svg className="w-3 h-3 text-zinc-600 opacity-0 group-hover:opacity-100 transition-opacity shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
        </svg>
      </dd>
    </div>
  )
}

type EditableSelectProps = {
  label: string
  value: string | null
  options: { value: string; label: string }[]
  onSave: (value: string) => Promise<void>
}

function EditableSelect({ label, value, options, onSave }: EditableSelectProps) {
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)

  async function handleChange(newValue: string) {
    if (newValue === (value ?? '')) {
      setEditing(false)
      return
    }
    setSaving(true)
    try {
      await onSave(newValue)
      setEditing(false)
    } finally {
      setSaving(false)
    }
  }

  const displayLabel = options.find((o) => o.value === value)?.label

  if (editing) {
    return (
      <div>
        <dt className="text-zinc-500 text-xs">{label}</dt>
        <dd className="mt-1">
          <Select
            label=""
            options={options}
            value={value ?? ''}
            onChange={(e) => handleChange(e.target.value)}
            onBlur={() => setEditing(false)}
            autoFocus
            disabled={saving}
          />
        </dd>
      </div>
    )
  }

  return (
    <div
      className="cursor-pointer group rounded-md px-2 py-1.5 -mx-2 hover:bg-zinc-800/50 transition-colors"
      onClick={() => setEditing(true)}
    >
      <dt className="text-zinc-500 text-xs">{label}</dt>
      <dd className="text-zinc-200 text-sm mt-0.5 flex items-center justify-between gap-2">
        <span>{displayLabel || <span className="text-zinc-600 italic">Not set</span>}</span>
        <svg className="w-3 h-3 text-zinc-600 opacity-0 group-hover:opacity-100 transition-opacity shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
        </svg>
      </dd>
    </div>
  )
}

export default function CompanySettings() {
  const [tab, setTab] = useState<Tab>('profile')
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

  // Logo upload
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Specialties
  const [editingSpecialties, setEditingSpecialties] = useState(false)
  const [specialtyDraft, setSpecialtyDraft] = useState('')

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

  async function handleLogoUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file || !company) return
    setUploading(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const result = await api.upload<{ url: string }>(`/companies/${company.id}/logo`, fd)
      setCompany({ ...company, logo_url: result.url })
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
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
    await deleteLocation(locId)
    if (selectedId === locId) setSelectedId(null)
    await loadLocations()
  }

  function handleEditLocation(loc: BusinessLocation) {
    setEditingLocation(loc)
    setShowModal(true)
  }

  function handleAddSpecialty() {
    const trimmed = specialtyDraft.trim()
    if (!trimmed || !company) return
    const current = company.healthcare_specialties || []
    if (current.includes(trimmed)) { setSpecialtyDraft(''); return }
    const updated = [...current, trimmed]
    updateField('healthcare_specialties', updated)
    setSpecialtyDraft('')
  }

  function handleRemoveSpecialty(s: string) {
    if (!company) return
    const updated = (company.healthcare_specialties || []).filter((x) => x !== s)
    updateField('healthcare_specialties', updated)
  }

  if (loading) return <p className="text-sm text-zinc-500">Loading...</p>
  if (error) return <p className="text-sm text-red-400">{error}</p>
  if (!company) return <p className="text-sm text-zinc-500">No company found.</p>

  const selectedLoc = locations.find((l) => l.id === selectedId)

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <h1 className="text-2xl font-semibold text-zinc-100 font-[Space_Grotesk] tracking-tight">Company</h1>
      </div>
      <p className="text-sm text-zinc-500 mb-5">Manage your company profile and locations.</p>

      {/* Tabs */}
      <div className="flex gap-1 mb-5">
        {(['profile', 'locations'] as const).map((t) => (
          <Button key={t} variant={tab === t ? 'secondary' : 'ghost'} size="sm" onClick={() => setTab(t)}>
            {t === 'profile' ? 'Profile' : `Locations${locations.length > 0 ? ` (${locations.length})` : ''}`}
          </Button>
        ))}
      </div>

      {/* Profile Tab */}
      {tab === 'profile' && (
        <div className="grid grid-cols-3 gap-6">
          <div className="col-span-2 space-y-5">
            <Card>
              <h3 className="text-sm font-medium text-zinc-300 mb-4">Company Information</h3>
              <dl className="space-y-1">
                <EditableField label="Company Name" value={company.name} onSave={(v) => updateField('name', v)} />
                <EditableField label="Industry" value={company.industry} onSave={(v) => updateField('industry', v)} />
                <EditableSelect label="Company Size" value={company.size} options={SIZE_OPTIONS} onSave={(v) => updateField('size', v)} />
                <EditableField label="HQ City" value={company.headquarters_city} onSave={(v) => updateField('headquarters_city', v)} />
                <EditableField label="HQ State" value={company.headquarters_state} onSave={(v) => updateField('headquarters_state', v)} />
                <EditableSelect label="Work Arrangement" value={company.work_arrangement} options={ARRANGEMENT_OPTIONS} onSave={(v) => updateField('work_arrangement', v)} />
                <EditableSelect label="Default Employment Type" value={company.default_employment_type} options={EMPLOYMENT_TYPE_OPTIONS} onSave={(v) => updateField('default_employment_type', v)} />
              </dl>
            </Card>

            {/* Healthcare Specialties */}
            <Card>
              <h3 className="text-sm font-medium text-zinc-300 mb-3">Healthcare Specialties</h3>
              <div className="flex flex-wrap gap-2 mb-3">
                {(company.healthcare_specialties || []).length === 0 && (
                  <p className="text-xs text-zinc-600 italic">No specialties set</p>
                )}
                {(company.healthcare_specialties || []).map((s) => (
                  <span key={s} className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-md bg-zinc-800 border border-zinc-700 text-zinc-300">
                    {s}
                    <button type="button" onClick={() => handleRemoveSpecialty(s)} className="text-zinc-600 hover:text-zinc-300 transition-colors ml-0.5">&times;</button>
                  </span>
                ))}
              </div>
              {editingSpecialties ? (
                <div className="flex items-center gap-2">
                  <Input
                    label=""
                    value={specialtyDraft}
                    onChange={(e) => setSpecialtyDraft(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAddSpecialty() } }}
                    placeholder="e.g. Cardiology"
                    autoFocus
                    className="!py-1 text-sm flex-1"
                  />
                  <Button size="sm" onClick={handleAddSpecialty} disabled={!specialtyDraft.trim()}>Add</Button>
                  <Button size="sm" variant="ghost" onClick={() => { setEditingSpecialties(false); setSpecialtyDraft('') }}>Done</Button>
                </div>
              ) : (
                <Button size="sm" variant="ghost" onClick={() => setEditingSpecialties(true)}>+ Add Specialty</Button>
              )}
            </Card>
          </div>

          {/* Sidebar: logo */}
          <div className="space-y-5">
            <Card className="flex flex-col items-center gap-3">
              {company.logo_url ? (
                <img src={company.logo_url} alt={company.name} className="w-24 h-24 rounded-lg object-contain border border-zinc-800" />
              ) : (
                <div className="w-24 h-24 rounded-lg bg-zinc-800 border border-zinc-700 flex items-center justify-center">
                  <span className="text-3xl font-bold text-zinc-600">{company.name.charAt(0)}</span>
                </div>
              )}
              <input ref={fileInputRef} type="file" accept="image/*" onChange={handleLogoUpload} className="hidden" />
              <Button size="sm" variant="ghost" onClick={() => fileInputRef.current?.click()} disabled={uploading}>
                {uploading ? 'Uploading...' : company.logo_url ? 'Change Logo' : 'Upload Logo'}
              </Button>
            </Card>

            <Card>
              <h3 className="text-sm font-medium text-zinc-300 mb-2">Quick Info</h3>
              <dl className="space-y-2 text-xs">
                <div>
                  <dt className="text-zinc-500">Industry</dt>
                  <dd className="text-zinc-300">{company.industry || 'Not set'}</dd>
                </div>
                <div>
                  <dt className="text-zinc-500">Size</dt>
                  <dd className="text-zinc-300">{SIZE_OPTIONS.find((o) => o.value === company.size)?.label || 'Not set'}</dd>
                </div>
                <div>
                  <dt className="text-zinc-500">Headquarters</dt>
                  <dd className="text-zinc-300">
                    {company.headquarters_city && company.headquarters_state
                      ? `${company.headquarters_city}, ${company.headquarters_state}`
                      : 'Not set'}
                  </dd>
                </div>
              </dl>
            </Card>
          </div>
        </div>
      )}

      {/* Locations Tab */}
      {tab === 'locations' && (
        <div className="grid grid-cols-3 gap-4">
          <div className="col-span-1">
            <ComplianceLocationList
              locations={locations}
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
              loading={locationsLoading}
            />
          </div>

          <div className="col-span-2">
            {!selectedId ? (
              <div className="flex items-center justify-center h-40 border border-zinc-800 rounded-lg">
                <p className="text-sm text-zinc-600">Select a location to view details</p>
              </div>
            ) : (
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <h2 className="text-base font-medium text-zinc-100">
                      {selectedLoc?.city}, {selectedLoc?.state}
                      {selectedLoc?.name && <span className="text-zinc-500 ml-2 text-sm">({selectedLoc.name})</span>}
                    </h2>
                    <div className="flex items-center gap-2 mt-0.5">
                      {selectedLoc?.source === 'employee_derived' && (
                        <Badge variant="neutral">
                          <span className="text-purple-400">Auto-created from employee</span>
                        </Badge>
                      )}
                      {selectedLoc && selectedLoc.employee_count > 0 && (
                        <span className="text-[11px] text-zinc-500">{selectedLoc.employee_count} employees</span>
                      )}
                    </div>
                  </div>
                </div>

                <FacilityProfileBanner
                  locationId={selectedId}
                  facilityAttributes={selectedLoc?.facility_attributes}
                  onUpdated={() => loadLocations()}
                  allLocations={locations}
                  source={selectedLoc?.source}
                />

                <Card>
                  <h3 className="text-sm font-medium text-zinc-300 mb-3">Location Details</h3>
                  <dl className="grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <dt className="text-zinc-500 text-xs">City</dt>
                      <dd className="text-zinc-200">{selectedLoc?.city}</dd>
                    </div>
                    <div>
                      <dt className="text-zinc-500 text-xs">State</dt>
                      <dd className="text-zinc-200">{selectedLoc?.state}</dd>
                    </div>
                    {selectedLoc?.county && (
                      <div>
                        <dt className="text-zinc-500 text-xs">County</dt>
                        <dd className="text-zinc-200">{selectedLoc.county}</dd>
                      </div>
                    )}
                    {selectedLoc?.zipcode && (
                      <div>
                        <dt className="text-zinc-500 text-xs">ZIP Code</dt>
                        <dd className="text-zinc-200">{selectedLoc.zipcode}</dd>
                      </div>
                    )}
                    {selectedLoc?.address && (
                      <div className="col-span-2">
                        <dt className="text-zinc-500 text-xs">Address</dt>
                        <dd className="text-zinc-200">{selectedLoc.address}</dd>
                      </div>
                    )}
                    <div>
                      <dt className="text-zinc-500 text-xs">Requirements</dt>
                      <dd className="text-zinc-200">{selectedLoc?.requirements_count ?? 0}</dd>
                    </div>
                    <div>
                      <dt className="text-zinc-500 text-xs">Employees</dt>
                      <dd className="text-zinc-200">{selectedLoc?.employee_count ?? 0}</dd>
                    </div>
                    {selectedLoc?.employee_names && selectedLoc.employee_names.length > 0 && (
                      <div className="col-span-2">
                        <dt className="text-zinc-500 text-xs mb-1">Assigned Employees</dt>
                        <dd className="flex flex-wrap gap-1.5">
                          {selectedLoc.employee_names.map((name) => (
                            <span key={name} className="text-xs px-2 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-zinc-700/60">{name}</span>
                          ))}
                        </dd>
                      </div>
                    )}
                  </dl>
                </Card>
              </div>
            )}
          </div>
        </div>
      )}

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
