import { useEffect, useState, useCallback } from 'react'
import { api } from '../../api/client'
import {
  fetchCompanyCompliance,
  fetchAdminLocationRequirements,
  adminCreateLocation,
  adminAddRequirement,
  adminRemoveRequirement,
  fetchRepositoryRequirements,
} from '../../api/compliance'
import { Badge, Button, Input, Modal, Select } from '../../components/ui'
import { Plus, Trash2, RefreshCw } from 'lucide-react'
import type { BusinessLocation, ComplianceRequirement, LocationCreate } from '../../types/compliance'

type Company = { id: string; company_name: string; industry: string | null; status: string }
type LocationWithCounts = BusinessLocation & { category_counts: Record<string, number> }
type ReqWithGov = ComplianceRequirement & { governance_source: string }
type RepoReq = {
  id: string; category: string; regulation_key: string; jurisdiction_level: string
  jurisdiction_name: string; title: string; description: string | null
  current_value: string | null; source_url: string | null; effective_date: string | null
}

export default function ComplianceManagement() {
  const [companies, setCompanies] = useState<Company[]>([])
  const [companyId, setCompanyId] = useState('')
  const [locations, setLocations] = useState<LocationWithCounts[]>([])
  const [locationId, setLocationId] = useState('')
  const [requirements, setRequirements] = useState<ReqWithGov[]>([])
  const [catFilter, setCatFilter] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Modals
  const [showAddLoc, setShowAddLoc] = useState(false)
  const [locCity, setLocCity] = useState('')
  const [locState, setLocState] = useState('')
  const [locName, setLocName] = useState('')
  const [addingLoc, setAddingLoc] = useState(false)

  const [showAddReq, setShowAddReq] = useState(false)
  const [repoReqs, setRepoReqs] = useState<RepoReq[]>([])
  const [repoSearch, setRepoSearch] = useState('')
  const [addingReqId, setAddingReqId] = useState<string | null>(null)

  // Load companies on mount
  useEffect(() => {
    api.get<{ registrations: Company[] }>('/admin/business-registrations?status=approved')
      .then((res) => setCompanies(res.registrations))
      .catch(() => {})
  }, [])

  // Load company compliance when selected
  const loadCompliance = useCallback(async (cid: string) => {
    if (!cid) { setLocations([]); setLocationId(''); setRequirements([]); return }
    setLoading(true)
    setError(null)
    try {
      const res = await fetchCompanyCompliance(cid)
      setLocations(res.locations)
      setLocationId('')
      setRequirements([])
    } catch { setError('Failed to load compliance data') }
    setLoading(false)
  }, [])

  // Load requirements when location selected
  const loadRequirements = useCallback(async (lid: string) => {
    if (!lid || !companyId) { setRequirements([]); return }
    setLoading(true)
    try {
      const res = await fetchAdminLocationRequirements(companyId, lid, catFilter || undefined)
      setRequirements(res.requirements)
    } catch { setError('Failed to load requirements') }
    setLoading(false)
  }, [companyId, catFilter])

  useEffect(() => { loadRequirements(locationId) }, [locationId, loadRequirements])

  // Categories from current location
  const selectedLoc = locations.find((l) => l.id === locationId)
  const categories = selectedLoc?.category_counts ? Object.keys(selectedLoc.category_counts).sort() : []

  // Add location
  async function handleAddLocation() {
    if (!locCity.trim() || !locState.trim() || !companyId) return
    setAddingLoc(true)
    setError(null)
    try {
      await adminCreateLocation(companyId, { city: locCity.trim(), state: locState.trim().toUpperCase(), name: locName.trim() || undefined } as LocationCreate)
      setShowAddLoc(false)
      setLocCity(''); setLocState(''); setLocName('')
      await loadCompliance(companyId)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create location')
    }
    setAddingLoc(false)
  }

  // Add requirement from repo
  async function handleAddReq(repoId: string) {
    if (!companyId || !locationId) return
    setAddingReqId(repoId)
    try {
      await adminAddRequirement(companyId, locationId, repoId)
      setRepoReqs((prev) => prev.filter((r) => r.id !== repoId))
      await loadRequirements(locationId)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add requirement')
    }
    setAddingReqId(null)
  }

  // Remove admin-added requirement
  async function handleRemoveReq(reqId: string) {
    if (!companyId || !locationId) return
    try {
      await adminRemoveRequirement(companyId, locationId, reqId)
      await loadRequirements(locationId)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove requirement')
    }
  }

  // Open add-requirement modal
  async function openAddReqModal() {
    setShowAddReq(true)
    setRepoSearch('')
    try {
      const res = await fetchRepositoryRequirements(companyId, locationId)
      setRepoReqs(res.requirements)
    } catch { setRepoReqs([]) }
  }

  const filteredRepo = repoReqs.filter((r) =>
    !repoSearch || r.title.toLowerCase().includes(repoSearch.toLowerCase()) || r.category.toLowerCase().includes(repoSearch.toLowerCase()),
  )

  return (
    <div>
      <h1 className="text-2xl font-semibold text-zinc-100">Compliance Management</h1>
      <p className="mt-1 text-sm text-zinc-500">View and manage compliance requirements for client companies.</p>

      {error && (
        <div className="mt-3 p-2 rounded border border-red-800/50 bg-red-900/20 text-sm text-red-400 flex justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-red-500 text-xs">Dismiss</button>
        </div>
      )}

      {/* Company + Location selectors */}
      <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
        <Select
          label="Company"
          placeholder="Select a company..."
          options={companies.map((c) => ({ value: c.id, label: c.company_name }))}
          value={companyId}
          onChange={(e) => { setCompanyId(e.target.value); loadCompliance(e.target.value) }}
        />
        {companyId && (
          <div>
            <Select
              label="Location"
              placeholder="Select a location..."
              options={locations.map((l) => ({ value: l.id, label: `${l.city}, ${l.state} (${l.requirements_count} reqs)` }))}
              value={locationId}
              onChange={(e) => { setLocationId(e.target.value); setCatFilter('') }}
            />
          </div>
        )}
        {companyId && (
          <div className="flex items-end">
            <Button size="sm" onClick={() => setShowAddLoc(true)}><Plus className="h-3.5 w-3.5" /> Add Location</Button>
          </div>
        )}
      </div>

      {/* Location summary cards */}
      {companyId && locations.length > 0 && !locationId && (
        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {locations.map((loc) => (
            <button
              key={loc.id}
              onClick={() => setLocationId(loc.id)}
              className="text-left p-3 rounded-lg border border-zinc-700 bg-zinc-800/50 hover:border-emerald-600 transition-colors"
            >
              <div className="text-sm font-medium text-zinc-200">{loc.name || `${loc.city}, ${loc.state}`}</div>
              <div className="text-xs text-zinc-500 mt-1">{loc.city}, {loc.state}</div>
              <div className="mt-2 flex gap-2 flex-wrap">
                <Badge variant="neutral">{loc.requirements_count} reqs</Badge>
                {loc.unread_alerts_count > 0 && <Badge variant="warning">{loc.unread_alerts_count} alerts</Badge>}
                <Badge variant={loc.data_status === 'synced' ? 'success' : 'neutral'}>{loc.data_status}</Badge>
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Requirements table */}
      {locationId && (
        <div className="mt-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-medium text-zinc-200">
                {selectedLoc?.name || `${selectedLoc?.city}, ${selectedLoc?.state}`}
              </h2>
              {categories.length > 0 && (
                <select
                  value={catFilter}
                  onChange={(e) => setCatFilter(e.target.value)}
                  className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-300"
                >
                  <option value="">All categories</option>
                  {categories.map((c) => (
                    <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>
                  ))}
                </select>
              )}
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" onClick={openAddReqModal}><Plus className="h-3.5 w-3.5" /> Add Requirement</Button>
              <Button size="sm" variant="secondary" onClick={() => loadRequirements(locationId)}><RefreshCw className="h-3.5 w-3.5" /></Button>
            </div>
          </div>

          {loading ? (
            <p className="text-sm text-zinc-500">Loading...</p>
          ) : requirements.length === 0 ? (
            <p className="text-sm text-zinc-500">No requirements found.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-zinc-500 text-xs border-b border-zinc-800">
                    <th className="pb-2 pr-3">Category</th>
                    <th className="pb-2 pr-3">Title</th>
                    <th className="pb-2 pr-3">Level</th>
                    <th className="pb-2 pr-3">Value</th>
                    <th className="pb-2 pr-3">Source</th>
                    <th className="pb-2 w-16"></th>
                  </tr>
                </thead>
                <tbody>
                  {requirements.map((r) => (
                    <tr key={r.id} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                      <td className="py-2 pr-3 text-zinc-400">{r.category.replace(/_/g, ' ')}</td>
                      <td className="py-2 pr-3 text-zinc-200">{r.title}</td>
                      <td className="py-2 pr-3 text-zinc-500 text-xs">{r.jurisdiction_level}</td>
                      <td className="py-2 pr-3 text-zinc-300 text-xs max-w-[200px] truncate">{r.current_value || '—'}</td>
                      <td className="py-2 pr-3">
                        {r.governance_source === 'admin_override' && (
                          <Badge variant="warning">admin</Badge>
                        )}
                      </td>
                      <td className="py-2">
                        {r.governance_source === 'admin_override' && (
                          <button onClick={() => handleRemoveReq(r.id)} className="text-zinc-500 hover:text-red-400" title="Remove">
                            <Trash2 size={14} />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Add Location Modal */}
      <Modal open={showAddLoc} onClose={() => setShowAddLoc(false)} title="Add Location">
        <div className="space-y-3">
          <Input label="City" value={locCity} onChange={(e) => setLocCity(e.target.value)} placeholder="San Diego" required />
          <Input label="State" value={locState} onChange={(e) => setLocState(e.target.value)} placeholder="CA" maxLength={2} required />
          <Input label="Name (optional)" value={locName} onChange={(e) => setLocName(e.target.value)} placeholder="San Diego Lab" />
          <div className="flex justify-end gap-2 pt-2">
            <Button size="sm" variant="secondary" onClick={() => setShowAddLoc(false)}>Cancel</Button>
            <Button size="sm" onClick={handleAddLocation} disabled={addingLoc || !locCity.trim() || !locState.trim()}>
              {addingLoc ? 'Creating...' : 'Create Location'}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Add Requirement Modal */}
      <Modal open={showAddReq} onClose={() => setShowAddReq(false)} title="Add Requirement from Repository">
        <div className="space-y-3">
          <Input label="" value={repoSearch} onChange={(e) => setRepoSearch(e.target.value)} placeholder="Search requirements..." />
          {filteredRepo.length === 0 ? (
            <p className="text-sm text-zinc-500">No unassigned requirements found.</p>
          ) : (
            <div className="max-h-80 overflow-y-auto space-y-1">
              {filteredRepo.map((r) => (
                <div key={r.id} className="flex items-center justify-between p-2 rounded bg-zinc-800/50 border border-zinc-700/50">
                  <div className="min-w-0 flex-1">
                    <div className="text-sm text-zinc-200 truncate">{r.title}</div>
                    <div className="text-xs text-zinc-500">{r.category.replace(/_/g, ' ')} · {r.jurisdiction_level}</div>
                  </div>
                  <Button
                    size="sm"
                    onClick={() => handleAddReq(r.id)}
                    disabled={addingReqId === r.id}
                    className="ml-2 shrink-0"
                  >
                    {addingReqId === r.id ? '...' : '+'}
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </Modal>
    </div>
  )
}
