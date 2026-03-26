import { useCallback, useEffect, useMemo, useState } from 'react'
import { Button, Select } from '../../components/ui'
import {
  fetchCredentialTypes,
  fetchRoleCategories,
  fetchTemplates,
  approveTemplate,
  rejectTemplate,
  triggerResearch,
  deleteTemplate,
  previewRequirements,
} from '../../api/credentialTemplates'
import type {
  CredentialType,
  RoleCategory,
  CredentialRequirementTemplate,
  PreviewResult,
} from '../../types/credential-templates'
import { STATUS_COLORS, PRIORITY_COLORS } from '../../types/credential-templates'

const US_STATES = [
  { value: 'AL', label: 'Alabama' }, { value: 'AK', label: 'Alaska' }, { value: 'AZ', label: 'Arizona' },
  { value: 'AR', label: 'Arkansas' }, { value: 'CA', label: 'California' }, { value: 'CO', label: 'Colorado' },
  { value: 'CT', label: 'Connecticut' }, { value: 'DE', label: 'Delaware' }, { value: 'FL', label: 'Florida' },
  { value: 'GA', label: 'Georgia' }, { value: 'HI', label: 'Hawaii' }, { value: 'ID', label: 'Idaho' },
  { value: 'IL', label: 'Illinois' }, { value: 'IN', label: 'Indiana' }, { value: 'IA', label: 'Iowa' },
  { value: 'KS', label: 'Kansas' }, { value: 'KY', label: 'Kentucky' }, { value: 'LA', label: 'Louisiana' },
  { value: 'ME', label: 'Maine' }, { value: 'MD', label: 'Maryland' }, { value: 'MA', label: 'Massachusetts' },
  { value: 'MI', label: 'Michigan' }, { value: 'MN', label: 'Minnesota' }, { value: 'MS', label: 'Mississippi' },
  { value: 'MO', label: 'Missouri' }, { value: 'MT', label: 'Montana' }, { value: 'NE', label: 'Nebraska' },
  { value: 'NV', label: 'Nevada' }, { value: 'NH', label: 'New Hampshire' }, { value: 'NJ', label: 'New Jersey' },
  { value: 'NM', label: 'New Mexico' }, { value: 'NY', label: 'New York' }, { value: 'NC', label: 'North Carolina' },
  { value: 'ND', label: 'North Dakota' }, { value: 'OH', label: 'Ohio' }, { value: 'OK', label: 'Oklahoma' },
  { value: 'OR', label: 'Oregon' }, { value: 'PA', label: 'Pennsylvania' }, { value: 'RI', label: 'Rhode Island' },
  { value: 'SC', label: 'South Carolina' }, { value: 'SD', label: 'South Dakota' }, { value: 'TN', label: 'Tennessee' },
  { value: 'TX', label: 'Texas' }, { value: 'UT', label: 'Utah' }, { value: 'VT', label: 'Vermont' },
  { value: 'VA', label: 'Virginia' }, { value: 'WA', label: 'Washington' }, { value: 'WV', label: 'West Virginia' },
  { value: 'WI', label: 'Wisconsin' }, { value: 'WY', label: 'Wyoming' }, { value: 'DC', label: 'District of Columbia' },
]

export default function CredentialTemplates() {
  const [credTypes, setCredTypes] = useState<CredentialType[]>([])
  const [roles, setRoles] = useState<RoleCategory[]>([])
  const [templates, setTemplates] = useState<CredentialRequirementTemplate[]>([])
  const [loading, setLoading] = useState(true)
  const [filterState, setFilterState] = useState('')
  const [filterRole, setFilterRole] = useState('')
  const [researching, setResearching] = useState(false)
  const [tab, setTab] = useState<'templates' | 'preview'>('templates')

  // Preview state
  const [previewState, setPreviewState] = useState('')
  const [previewTitle, setPreviewTitle] = useState('')
  const [previewResult, setPreviewResult] = useState<PreviewResult | null>(null)
  const [previewing, setPreviewing] = useState(false)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [ct, rc, tmpl] = await Promise.all([
        fetchCredentialTypes(),
        fetchRoleCategories(),
        fetchTemplates({ state: filterState || undefined, role_category_id: filterRole || undefined }),
      ])
      setCredTypes(ct)
      setRoles(rc)
      setTemplates(tmpl)
    } catch (e) {
      console.error('Failed to load credential template data', e)
    } finally {
      setLoading(false)
    }
  }, [filterState, filterRole])

  useEffect(() => { loadData() }, [loadData])

  const grouped = useMemo(() => {
    const map = new Map<string, CredentialRequirementTemplate[]>()
    for (const t of templates) {
      const key = `${t.state}|${t.role_key || t.role_category_id}`
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(t)
    }
    return map
  }, [templates])

  const handleApprove = async (id: string) => {
    await approveTemplate(id)
    loadData()
  }

  const handleReject = async (id: string) => {
    await rejectTemplate(id)
    loadData()
  }

  const handleDelete = async (id: string) => {
    await deleteTemplate(id)
    loadData()
  }

  const handleResearch = async () => {
    if (!filterState || !filterRole) return
    setResearching(true)
    try {
      await triggerResearch({ state: filterState, role_category_id: filterRole })
      loadData()
    } catch (e) {
      console.error('Research failed', e)
    } finally {
      setResearching(false)
    }
  }

  const handlePreview = async () => {
    if (!previewState || !previewTitle) return
    setPreviewing(true)
    try {
      const result = await previewRequirements({ state: previewState, job_title: previewTitle })
      setPreviewResult(result)
    } catch (e) {
      console.error('Preview failed', e)
    } finally {
      setPreviewing(false)
    }
  }

  const clinicalRoles = useMemo(() => roles.filter(r => r.is_clinical), [roles])

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Loading credential templates...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-zinc-100">Credential Requirements</h1>
          <p className="text-xs text-zinc-500 mt-0.5">
            Manage jurisdiction + role-specific credential requirements. AI-researched templates can be reviewed and customized.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setTab('templates')}
            className={`px-3 py-1.5 text-xs rounded-md transition-colors ${tab === 'templates' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'}`}
          >
            Templates
          </button>
          <button
            onClick={() => setTab('preview')}
            className={`px-3 py-1.5 text-xs rounded-md transition-colors ${tab === 'preview' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'}`}
          >
            Preview
          </button>
        </div>
      </div>

      {tab === 'templates' && (
        <>
          {/* Filters + Research */}
          <div className="flex items-end gap-3">
            <div className="w-48">
              <Select
                label="State"
                options={US_STATES}
                placeholder="All states"
                value={filterState}
                onChange={(e) => setFilterState(e.target.value)}
              />
            </div>
            <div className="w-56">
              <Select
                label="Role Category"
                options={clinicalRoles.map(r => ({ value: r.id, label: r.label }))}
                placeholder="All roles"
                value={filterRole}
                onChange={(e) => setFilterRole(e.target.value)}
              />
            </div>
            {filterState && filterRole && (
              <Button onClick={handleResearch} disabled={researching} className="mb-0.5">
                {researching ? 'Researching...' : 'Research with AI'}
              </Button>
            )}
          </div>

          {/* Stats */}
          <div className="flex items-center gap-4 text-xs text-zinc-500">
            <span>{templates.length} templates</span>
            <span>{templates.filter(t => t.review_status === 'pending').length} pending review</span>
            <span>{new Set(templates.map(t => t.state)).size} states</span>
            <span>{credTypes.length} credential types</span>
          </div>

          {/* Template groups */}
          {templates.length === 0 ? (
            <div className="text-center py-16 text-zinc-600 text-sm">
              No templates found. Select a state and role, then click "Research with AI" to generate requirements.
            </div>
          ) : (
            <div className="space-y-4">
              {Array.from(grouped.entries()).map(([groupKey, items]) => {
                const first = items[0]
                const stateName = US_STATES.find(s => s.value === first.state)?.label || first.state
                const roleName = first.role_label || first.role_key || 'Unknown'
                const pendingCount = items.filter(t => t.review_status === 'pending').length

                return (
                  <div key={groupKey} className="rounded-lg border border-zinc-800 bg-zinc-900/50">
                    <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-zinc-200">{roleName}</span>
                        <span className="text-xs text-zinc-500">{stateName}</span>
                        {pendingCount > 0 && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400">
                            {pendingCount} pending
                          </span>
                        )}
                      </div>
                      <span className="text-[10px] text-zinc-600">{items.length} requirements</span>
                    </div>
                    <div className="divide-y divide-zinc-800/50">
                      {items.map(t => (
                        <div key={t.id} className="flex items-center justify-between px-4 py-2.5 group">
                          <div className="flex items-center gap-3 min-w-0">
                            <span className={`text-[10px] uppercase tracking-wider font-bold w-16 ${PRIORITY_COLORS[t.priority] || 'text-zinc-500'}`}>
                              {t.priority}
                            </span>
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="text-sm text-zinc-200">{t.ct_label || t.credential_type_id}</span>
                                <span className={`text-[10px] px-1.5 py-0.5 rounded ${STATUS_COLORS[t.review_status] || 'bg-zinc-800 text-zinc-500'}`}>
                                  {t.review_status.replace('_', ' ')}
                                </span>
                                {!t.is_required && (
                                  <span className="text-[10px] text-zinc-600">optional</span>
                                )}
                              </div>
                              {t.notes && (
                                <p className="text-[10px] text-zinc-600 mt-0.5 truncate max-w-md">{t.notes}</p>
                              )}
                            </div>
                          </div>
                          <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                            <span className="text-[10px] text-zinc-600 mr-2">
                              {t.due_days}d &middot; {t.source.replace('_', ' ')}
                              {t.ai_confidence != null && ` &middot; ${Math.round(t.ai_confidence * 100)}%`}
                            </span>
                            {t.review_status === 'pending' && (
                              <>
                                <button onClick={() => handleApprove(t.id)} className="text-[10px] px-2 py-1 rounded bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20">
                                  Approve
                                </button>
                                <button onClick={() => handleReject(t.id)} className="text-[10px] px-2 py-1 rounded bg-red-500/10 text-red-400 hover:bg-red-500/20">
                                  Reject
                                </button>
                              </>
                            )}
                            {t.company_id && (
                              <button onClick={() => handleDelete(t.id)} className="text-[10px] px-2 py-1 rounded bg-zinc-800 text-zinc-500 hover:text-zinc-300">
                                Remove
                              </button>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </>
      )}

      {tab === 'preview' && (
        <div className="space-y-4">
          <p className="text-xs text-zinc-500">
            Preview what credential requirements would apply for a given state and job title. No data is saved.
          </p>
          <div className="flex items-end gap-3">
            <div className="w-48">
              <Select
                label="State"
                options={US_STATES}
                placeholder="Select state"
                value={previewState}
                onChange={(e) => setPreviewState(e.target.value)}
              />
            </div>
            <div className="flex-1">
              <label className="block text-sm font-medium text-zinc-300 mb-1.5">Job Title</label>
              <input
                type="text"
                value={previewTitle}
                onChange={(e) => setPreviewTitle(e.target.value)}
                placeholder="e.g. Registered Nurse, CNA, Pharmacist"
                className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3.5 py-2.5 text-sm text-zinc-100 outline-none focus:border-zinc-500 focus:ring-1 focus:ring-zinc-500 transition-colors"
                onKeyDown={(e) => e.key === 'Enter' && handlePreview()}
              />
            </div>
            <Button onClick={handlePreview} disabled={previewing || !previewState || !previewTitle} className="mb-0.5">
              {previewing ? 'Loading...' : 'Preview'}
            </Button>
          </div>

          {previewResult && (
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50">
              <div className="px-4 py-3 border-b border-zinc-800 flex items-center gap-3">
                <span className="text-sm font-medium text-zinc-200">
                  {previewResult.role_category?.label || 'Unknown role'}
                </span>
                <span className="text-xs text-zinc-500">
                  {US_STATES.find(s => s.value === previewResult.state)?.label} &middot; "{previewResult.job_title}"
                </span>
                <span className="text-[10px] text-zinc-600">
                  {previewResult.requirements.length} requirements
                </span>
              </div>
              {previewResult.requirements.length === 0 ? (
                <div className="px-4 py-8 text-center text-sm text-zinc-600">
                  No credential requirements for this role.
                </div>
              ) : (
                <div className="divide-y divide-zinc-800/50">
                  {previewResult.requirements.map((r, i) => (
                    <div key={i} className="flex items-center justify-between px-4 py-2.5">
                      <div className="flex items-center gap-3">
                        <span className={`text-[10px] uppercase tracking-wider font-bold w-16 ${PRIORITY_COLORS[r.priority] || 'text-zinc-500'}`}>
                          {r.priority}
                        </span>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-sm text-zinc-200">{r.credential_type_label}</span>
                            {!r.is_required && <span className="text-[10px] text-zinc-600">optional</span>}
                          </div>
                          {r.notes && <p className="text-[10px] text-zinc-600 mt-0.5">{r.notes}</p>}
                        </div>
                      </div>
                      <div className="text-[10px] text-zinc-600">
                        {r.due_days}d &middot; {r.source.replace('_', ' ')}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
