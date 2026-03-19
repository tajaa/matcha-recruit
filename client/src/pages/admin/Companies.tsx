import { useEffect, useState } from 'react'
import { Badge, Button, Input, Modal } from '../../components/ui'
import { api } from '../../api/client'
import {
  INDUSTRY_OPTIONS,
  HEALTHCARE_SPECIALTIES,
  SIZE_OPTIONS,
  HEALTHCARE_INDUSTRIES,
} from '../../data/industryConstants'

type Company = {
  id: string
  company_name: string
  industry: string | null
  healthcare_specialties: string[] | null
  company_size: string | null
  status: string
  created_at: string
  owner_email: string
  owner_name: string
}

type CompanyListResponse = {
  registrations: Company[]
  total: number
}

type RegisterForm = {
  company_name: string
  industry: string
  company_size: string
  healthcare_specialties: string[]
  headcount: string
  name: string
  email: string
  password: string
}

const EMPTY_FORM: RegisterForm = {
  company_name: '',
  industry: '',
  company_size: '',
  healthcare_specialties: [],
  headcount: '1',
  name: '',
  email: '',
  password: '',
}

const statusBadge = (status: string | null) => {
  if (!status || status === 'approved')
    return <Badge variant="success">Approved</Badge>
  if (status === 'pending')
    return <Badge variant="warning">Pending</Badge>
  return <Badge variant="danger">Rejected</Badge>
}

function industryLabel(value: string | null) {
  if (!value) return '—'
  return INDUSTRY_OPTIONS.find((o) => o.value === value)?.label ?? value
}

export default function Companies() {
  const [companies, setCompanies] = useState<Company[]>([])
  const [filter, setFilter] = useState<'all' | 'pending' | 'approved' | 'rejected'>('all')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState<RegisterForm>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [addError, setAddError] = useState('')
  const [runningAssessment, setRunningAssessment] = useState<string | null>(null)

  function fetchCompanies() {
    setLoading(true)
    const params = filter !== 'all' ? `?status=${filter}` : ''
    api.get<CompanyListResponse>(`/admin/business-registrations${params}`)
      .then((res) => setCompanies(res.registrations))
      .catch(() => setCompanies([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchCompanies() }, [filter])

  const filtered = companies.filter((c) =>
    c.company_name.toLowerCase().includes(search.toLowerCase())
  )

  async function approve(id: string) {
    await api.post(`/admin/business-registrations/${id}/approve`)
    setCompanies((prev) =>
      prev.map((c) => (c.id === id ? { ...c, status: 'approved' } : c))
    )
  }

  async function runAssessment(id: string) {
    setRunningAssessment(id)
    try {
      await api.post(`/risk-assessment/admin/run/${id}`, {})
    } finally {
      setRunningAssessment(null)
    }
  }

  async function reject(id: string) {
    const reason = prompt('Rejection reason:')
    if (!reason) return
    await api.post(`/admin/business-registrations/${id}/reject`, { reason })
    setCompanies((prev) =>
      prev.map((c) => (c.id === id ? { ...c, status: 'rejected' } : c))
    )
  }

  function toggleSpecialty(val: string) {
    setForm((f) => ({
      ...f,
      healthcare_specialties: f.healthcare_specialties.includes(val)
        ? f.healthcare_specialties.filter((s) => s !== val)
        : [...f.healthcare_specialties, val],
    }))
  }

  async function handleAddCompany(e: React.FormEvent) {
    e.preventDefault()
    setAddError('')
    setSaving(true)
    try {
      const showSpecialties = HEALTHCARE_INDUSTRIES.has(form.industry)
      await api.post('/auth/register/business', {
        company_name: form.company_name,
        industry: form.industry || undefined,
        company_size: form.company_size || undefined,
        healthcare_specialties: showSpecialties && form.healthcare_specialties.length > 0
          ? form.healthcare_specialties : undefined,
        headcount: parseInt(form.headcount, 10) || 1,
        name: form.name,
        email: form.email,
        password: form.password,
      })
      setShowAdd(false)
      setForm(EMPTY_FORM)
      fetchCompanies()
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setSaving(false)
    }
  }

  const showSpecialties = HEALTHCARE_INDUSTRIES.has(form.industry)

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 font-[Space_Grotesk] tracking-tight">
            Companies
          </h1>
          <p className="mt-2 text-sm text-zinc-500">
            Manage registered businesses and approvals.
          </p>
        </div>
        <Button size="sm" onClick={() => setShowAdd(true)}>
          Add Company
        </Button>
      </div>

      {/* Filters */}
      <div className="mt-6 flex items-center gap-3">
        <Input
          label=""
          placeholder="Search companies..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <div className="flex gap-1 ml-auto">
          {(['all', 'pending', 'approved', 'rejected'] as const).map((s) => (
            <Button
              key={s}
              variant={filter === s ? 'primary' : 'ghost'}
              size="sm"
              onClick={() => setFilter(s)}
            >
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </Button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="mt-6">
        {loading ? (
          <p className="text-sm text-zinc-500">Loading...</p>
        ) : filtered.length === 0 ? (
          <p className="text-sm text-zinc-500">No companies found.</p>
        ) : (
          <div className="overflow-hidden rounded-xl border border-zinc-800">
            <table className="w-full text-sm text-left">
              <thead className="bg-zinc-900/50 text-zinc-400">
                <tr>
                  <th className="px-4 py-3 font-medium">Company</th>
                  <th className="px-4 py-3 font-medium">Industry</th>
                  <th className="px-4 py-3 font-medium">Size</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800">
                {filtered.map((c) => (
                  <tr key={c.id} className="text-zinc-300">
                    <td className="px-4 py-3">
                      <p className="font-medium text-zinc-100">{c.company_name}</p>
                      <p className="text-xs text-zinc-500">{c.owner_email}</p>
                    </td>
                    <td className="px-4 py-3">
                      <span>{industryLabel(c.industry)}</span>
                      {c.healthcare_specialties && c.healthcare_specialties.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {c.healthcare_specialties.map((s) => (
                            <span key={s} className="text-[10px] px-1.5 py-0.5 rounded-full border border-violet-500/30 bg-violet-500/10 text-violet-300">
                              {HEALTHCARE_SPECIALTIES.find((x) => x.value === s)?.label ?? s}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">{c.company_size ?? '—'}</td>
                    <td className="px-4 py-3">{statusBadge(c.status)}</td>
                    <td className="px-4 py-3 text-right">
                      {c.status === 'pending' ? (
                        <div className="flex justify-end gap-2">
                          <Button size="sm" onClick={() => approve(c.id)}>
                            Approve
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => reject(c.id)}>
                            Reject
                          </Button>
                        </div>
                      ) : (!c.status || c.status === 'approved') ? (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => runAssessment(c.id)}
                          disabled={runningAssessment === c.id}
                        >
                          {runningAssessment === c.id ? 'Running...' : 'Run Assessment'}
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add Company Modal */}
      <Modal open={showAdd} onClose={() => { setShowAdd(false); setAddError('') }} title="Add Company" width="lg">
        <form onSubmit={handleAddCompany} className="space-y-4">
          {/* Company info */}
          <div>
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium mb-2">Company Info</p>
            <div className="grid grid-cols-2 gap-3">
              <Input
                label="Company Name"
                value={form.company_name}
                onChange={(e) => setForm({ ...form, company_name: e.target.value })}
                required
              />
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Industry</label>
                <select
                  value={form.industry}
                  onChange={(e) => setForm({ ...form, industry: e.target.value, healthcare_specialties: [] })}
                  className="w-full bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
                >
                  <option value="">Select industry...</option>
                  {INDUSTRY_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Company Size</label>
                <select
                  value={form.company_size}
                  onChange={(e) => setForm({ ...form, company_size: e.target.value })}
                  className="w-full bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
                >
                  <option value="">Select size...</option>
                  {SIZE_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>
              <Input
                label="Headcount"
                type="number"
                value={form.headcount}
                onChange={(e) => setForm({ ...form, headcount: e.target.value })}
                required
              />
            </div>
          </div>

          {/* Healthcare specialties */}
          {showSpecialties && (
            <div>
              <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium mb-2">
                Healthcare Specialties
              </p>
              <div className="border border-zinc-800 rounded-lg p-3 grid grid-cols-3 gap-1.5">
                {HEALTHCARE_SPECIALTIES.map((s) => (
                  <button
                    key={s.value}
                    type="button"
                    onClick={() => toggleSpecialty(s.value)}
                    className={`text-xs text-left px-2 py-1.5 rounded transition-colors ${
                      form.healthcare_specialties.includes(s.value)
                        ? 'bg-violet-500/20 text-violet-300'
                        : 'text-zinc-500 hover:text-zinc-300 bg-zinc-800/30'
                    }`}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
              <p className="text-[10px] text-zinc-600 mt-1">
                Selected specialties determine which compliance categories apply.
              </p>
            </div>
          )}

          {/* Account info */}
          <div>
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium mb-2">First Admin User</p>
            <div className="grid grid-cols-2 gap-3">
              <Input
                label="Full Name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
              />
              <Input
                label="Email"
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                required
              />
              <Input
                label="Password"
                type="password"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                required
              />
            </div>
          </div>

          {addError && <p className="text-sm text-red-400">{addError}</p>}

          <div className="flex items-center gap-2 pt-2 border-t border-zinc-800">
            <Button type="submit" size="sm" disabled={saving || !form.company_name.trim() || !form.email.trim()}>
              {saving ? 'Creating...' : 'Create Company'}
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => { setShowAdd(false); setAddError('') }}>
              Cancel
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
