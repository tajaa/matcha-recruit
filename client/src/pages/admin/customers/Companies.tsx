import { AdminButton as Button, AdminInput as Input, AdminSelect } from '../../../components/admin/AdminUI'
import { AdminPageHeader } from '../../../components/admin/AdminPageHeader'
import { AdminList, AdminPagination } from '../../../components/admin/AdminList'
import { useAdminPagination } from '../../../components/admin/useAdminPagination'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge, DataTable, Modal } from '../../../components/ui'
import { api } from '../../../api/client'
import { useAsync } from '../../../hooks/useAsync'
import {
  INDUSTRY_OPTIONS,
  HEALTHCARE_SPECIALTIES,
  SIZE_OPTIONS,
  HEALTHCARE_INDUSTRIES,
} from '../../../data/industryConstants'

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
  signup_source: string | null
  is_personal: boolean
  is_test: boolean
  is_suspended: boolean
  deleted_at: string | null
  subscription: {
    pack_id: string
    status: string
    amount_cents: number
    stripe_subscription_id: string
    stripe_customer_id: string
    current_period_end: string | null
    canceled_at: string | null
  } | null
}

type Tier = 'all' | 'free' | 'lite' | 'x' | 'compliance' | 'platform' | 'personal'

const TIER_LABEL: Record<Exclude<Tier, 'all'>, string> = {
  free: 'Free',
  lite: 'Lite',
  x: 'Matcha-X',
  compliance: 'Compliance',
  platform: 'Platform',
  personal: 'Personal',
}

function tierFromCompany(c: Company): Exclude<Tier, 'all'> {
  if (c.is_personal) return 'personal'
  if (c.signup_source === 'resources_free') return 'free'
  if (c.signup_source === 'matcha_lite') return 'lite'
  if (c.signup_source === 'matcha_x') return 'x'
  if (c.signup_source === 'matcha_compliance') return 'compliance'
  return 'platform'
}

const TIER_BADGE_CLASS: Record<Exclude<Tier, 'all'>, string> = {
  free: 'border-zinc-600 bg-zinc-700/30 text-zinc-300',
  lite: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300',
  x: 'border-teal-500/40 bg-teal-500/10 text-teal-300',
  compliance: 'border-amber-500/40 bg-amber-500/10 text-amber-300',
  platform: 'border-violet-500/40 bg-violet-500/10 text-violet-300',
  personal: 'border-sky-500/40 bg-sky-500/10 text-sky-300',
}

function TierBadge({ c }: { c: Company }) {
  const tier = tierFromCompany(c)
  return (
    <span className={`inline-block text-[10px] px-1.5 py-0.5 rounded border ${TIER_BADGE_CLASS[tier]}`}>
      {TIER_LABEL[tier]}
    </span>
  )
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
  const [filter, setFilter] = useState<'all' | 'pending' | 'approved' | 'rejected'>('all')
  const [tier, setTier] = useState<Tier>('all')
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState('newest')
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState<RegisterForm>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [addError, setAddError] = useState('')
  const [runningAssessment, setRunningAssessment] = useState<string | null>(null)

  const {
    data: companies,
    loading,
    error,
    setData: setCompanies,
    reload: fetchCompanies,
  } = useAsync(
    () => {
      const qs = new URLSearchParams()
      if (filter !== 'all') qs.set('status', filter)
      if (tier !== 'all') qs.set('tier', tier)
      const params = qs.toString() ? `?${qs.toString()}` : ''
      return api
        .get<CompanyListResponse>(`/admin/business-registrations${params}`)
        .then((res) => res.registrations)
    },
    [filter, tier],
    [],
  )

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase()
    return companies.filter((company) => [company.company_name, company.owner_email, company.owner_name].some((value) => (value ?? '').toLowerCase().includes(query)))
      .sort((a, b) => sort === 'name' ? a.company_name.localeCompare(b.company_name) || a.id.localeCompare(b.id) : new Date(b.created_at).getTime() - new Date(a.created_at).getTime() || a.id.localeCompare(b.id))
  }, [companies, search, sort])
  const pagination = useAdminPagination(filtered, JSON.stringify([search, filter, tier, sort]))

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
    <AdminList>
      <AdminPageHeader
        title="Companies"
        description="Manage registered businesses and approvals."
        actions={
          <Button size="sm" onClick={() => setShowAdd(true)}>
            Add Company
          </Button>
        }
      />

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Input aria-label="Search companies" placeholder="Search company, owner, or email…" value={search} onChange={(event) => setSearch(event.target.value)} className="max-w-xs py-1.5! text-xs!" />
        <AdminSelect aria-label="Company status" value={filter} onChange={(event) => setFilter(event.target.value as typeof filter)} className="py-1.5! text-xs!">
          <option value="all">All statuses</option><option value="pending">Pending</option><option value="approved">Approved</option><option value="rejected">Rejected</option>
        </AdminSelect>
        <AdminSelect aria-label="Company tier" value={tier} onChange={(event) => setTier(event.target.value as Tier)} className="py-1.5! text-xs!">
          <option value="all">All tiers</option>{Object.entries(TIER_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </AdminSelect>
        <AdminSelect aria-label="Sort companies" value={sort} onChange={(event) => setSort(event.target.value)} className="py-1.5! text-xs!"><option value="newest">Newest first</option><option value="name">Name A–Z</option></AdminSelect>
      </div>

      {/* Table */}
      <div className="mt-3">
        <AdminPagination pagination={pagination} />
        <DataTable
          rows={pagination.rows}
          rowKey={(c) => c.id}
          loading={loading}
          error={error}
          emptyText="No companies found."
          columns={[
            {
              key: 'company',
              header: 'Company',
              render: (c) => (
                <>
                  <Link to={`/admin/companies/${c.id}`} className="font-medium text-zinc-100 hover:text-emerald-400 transition-colors">{c.company_name}</Link>
                  <p className="text-xs text-zinc-500">{c.owner_email}</p>
                  {c.is_test && (
                    <span
                      className="inline-block mt-1 mr-1 text-[10px] px-1.5 py-0.5 rounded border border-amber-500/40 bg-amber-500/10 text-amber-300"
                      title="Test/demo tenant — synced automatically between dev and prod on every deploy."
                    >
                      TEST
                    </span>
                  )}
                  {c.is_suspended && (
                    <span
                      className="inline-block mt-1 text-[10px] px-1.5 py-0.5 rounded border border-red-500/40 bg-red-500/10 text-red-300"
                      title="The company owner is suspended; other users in the company may not be."
                    >
                      Owner suspended
                    </span>
                  )}
                </>
              ),
            },
            { key: 'tier', header: 'Tier', render: (c) => <TierBadge c={c} /> },
            {
              key: 'industry',
              header: 'Industry',
              render: (c) => (
                <>
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
                </>
              ),
            },
            { key: 'size', header: 'Size', render: (c) => c.company_size ?? '—' },
            { key: 'status', header: 'Status', render: (c) => statusBadge(c.status) },
            {
              key: 'actions',
              header: 'Actions',
              align: 'right',
              render: (c) =>
                c.status === 'pending' ? (
                  <div className="flex justify-end gap-2">
                    <Button size="sm" onClick={() => approve(c.id)}>Approve</Button>
                    <Button size="sm" variant="ghost" onClick={() => reject(c.id)}>Reject</Button>
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
                ) : null,
            },
          ]}
        />
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
                <AdminSelect
                  value={form.industry}
                  onChange={(e) => setForm({ ...form, industry: e.target.value, healthcare_specialties: [] })} className="w-full"
                >
                  <option value="">Select industry...</option>
                  {INDUSTRY_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </AdminSelect>
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Company Size</label>
                <AdminSelect
                  value={form.company_size}
                  onChange={(e) => setForm({ ...form, company_size: e.target.value })} className="w-full"
                >
                  <option value="">Select size...</option>
                  {SIZE_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </AdminSelect>
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
    </AdminList>
  )
}
