import { useState, useRef } from 'react'
import { Button, Input } from '../../../../components/ui'
import { LABEL } from '../../../../components/ui/typography'
import { INDUSTRY_OPTIONS } from '../../../../data/industryConstants'
import { api } from '../../../../api/client'
import LiteAddonsPanel from '../../../../components/tier-sidebars/LiteAddonsPanel'
import { EditableField } from './EditableField'
import { EditableSelect } from './EditableSelect'
import { PANEL, SIZE_OPTIONS, ARRANGEMENT_OPTIONS, EMPLOYMENT_TYPE_OPTIONS } from './constants'
import type { CompanyData } from './types'

type ProfileTabProps = {
  company: CompanyData
  setCompany: (company: CompanyData) => void
  updateField: (field: string, value: string | string[]) => Promise<void>
  showAddons: boolean
}

export function ProfileTab({ company, setCompany, updateField, showAddons }: ProfileTabProps) {
  // Logo upload
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Specialties
  const [editingSpecialties, setEditingSpecialties] = useState(false)
  const [specialtyDraft, setSpecialtyDraft] = useState('')

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

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="col-span-2 space-y-5">
          <div className={PANEL}>
            <h3 className={`${LABEL} mb-4`}>Company Information</h3>
            <dl className="space-y-1">
              <EditableField label="Company Name" value={company.name} onSave={(v) => updateField('name', v)} />
              <EditableSelect label="Industry" value={company.industry} options={INDUSTRY_OPTIONS} onSave={(v) => updateField('industry', v)} />
              <EditableSelect label="Company Size" value={company.size} options={SIZE_OPTIONS} onSave={(v) => updateField('size', v)} />
              <EditableField label="HQ City" value={company.headquarters_city} onSave={(v) => updateField('headquarters_city', v)} />
              <EditableField label="HQ State" value={company.headquarters_state} onSave={(v) => updateField('headquarters_state', v)} />
              <EditableSelect label="Work Arrangement" value={company.work_arrangement} options={ARRANGEMENT_OPTIONS} onSave={(v) => updateField('work_arrangement', v)} />
              <EditableSelect label="Default Employment Type" value={company.default_employment_type} options={EMPLOYMENT_TYPE_OPTIONS} onSave={(v) => updateField('default_employment_type', v)} />
            </dl>
          </div>

          {/* OSHA / ITA Filing Identity */}
          <div className={PANEL}>
            <h3 className={`${LABEL} mb-1`}>OSHA / ITA Filing Identity</h3>
            <p className="text-xs text-zinc-600 mb-4">
              Employer-level defaults used on OSHA Form 300A and ITA electronic filing. Establishments
              inherit EIN / NAICS unless overridden per location. The executive block populates the
              300A "Sign here" certification on every PDF.
            </p>
            <dl className="space-y-1">
              <EditableField label="Legal Name" value={company.legal_name} onSave={(v) => updateField('legal_name', v)} />
              <EditableField label="EIN" value={company.ein} onSave={(v) => updateField('ein', v)} />
              <EditableField label="NAICS Code" value={company.naics} onSave={(v) => updateField('naics', v)} />
              <EditableField label="Street Address" value={company.address} onSave={(v) => updateField('address', v)} />
              <EditableField label="ZIP" value={company.zip} onSave={(v) => updateField('zip', v)} />
              <EditableField label="Company Executive" value={company.executive_name} onSave={(v) => updateField('executive_name', v)} />
              <EditableField label="Executive Title" value={company.executive_title} onSave={(v) => updateField('executive_title', v)} />
              <EditableField label="Executive Phone" value={company.executive_phone} onSave={(v) => updateField('executive_phone', v)} />
            </dl>
          </div>

          {/* Healthcare Specialties */}
          <div className={PANEL}>
            <h3 className={`${LABEL} mb-3`}>Healthcare Specialties</h3>
            <div className="flex flex-wrap gap-2 mb-3">
              {(company.healthcare_specialties || []).length === 0 && (
                <p className="text-xs text-zinc-600 italic">No specialties set</p>
              )}
              {(company.healthcare_specialties || []).map((s) => (
                <span key={s} className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-md bg-white/[0.04] border border-white/[0.08] text-zinc-300">
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
          </div>
        </div>

        {/* Sidebar: logo */}
        <div className="space-y-5">
          <div className={`${PANEL} flex flex-col items-center gap-3`}>
            {company.logo_url ? (
              <img src={company.logo_url} alt={company.name} className="w-24 h-24 rounded-lg object-contain border border-white/[0.06]" />
            ) : (
              <div className="w-24 h-24 rounded-lg bg-white/[0.04] border border-white/[0.08] flex items-center justify-center">
                <span className="text-3xl font-bold text-zinc-600">{company.name.charAt(0)}</span>
              </div>
            )}
            <input ref={fileInputRef} type="file" accept="image/*" onChange={handleLogoUpload} className="hidden" />
            <Button size="sm" variant="ghost" onClick={() => fileInputRef.current?.click()} disabled={uploading}>
              {uploading ? 'Uploading...' : company.logo_url ? 'Change Logo' : 'Upload Logo'}
            </Button>
          </div>

          <div className={PANEL}>
            <h3 className={`${LABEL} mb-2`}>Quick Info</h3>
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
          </div>
        </div>
      </div>

      {/* Add-ons — Lite-family tenants only */}
      {showAddons && (
        <div>
          <h3 className={`${LABEL} mb-1`}>Add-ons</h3>
          <p className="text-xs text-zinc-600 mb-4">
            Extend your plan — add-ons bill monthly per employee alongside your subscription.
          </p>
          <LiteAddonsPanel />
        </div>
      )}
    </>
  )
}
