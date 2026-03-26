import { useEffect, useState } from 'react'
import { Badge, Button, Input, Modal } from '../../components/ui'
import { api } from '../../api/client'
import { Link2 } from 'lucide-react'

type BrokerContract = {
  id: string | null
  currency: string | null
  base_platform_fee: number | null
  pepm_rate: number | null
  minimum_monthly_commit: number | null
}

type Broker = {
  id: string
  name: string
  slug: string
  status: string
  support_routing: string
  billing_mode: string
  invoice_owner: string
  branding_mode: string
  active_member_count: number
  active_company_count: number
  active_contract: BrokerContract | null
  created_at: string
}

type BrokerListResponse = {
  brokers: Broker[]
}

type CreateForm = {
  broker_name: string
  owner_email: string
  owner_name: string
  owner_password: string
  slug: string
  support_routing: string
  billing_mode: string
  invoice_owner: string
}

const EMPTY_FORM: CreateForm = {
  broker_name: '',
  owner_email: '',
  owner_name: '',
  owner_password: '',
  slug: '',
  support_routing: 'shared',
  billing_mode: 'direct',
  invoice_owner: 'matcha',
}

type EditForm = {
  status: string
  support_routing: string
}

type CreateResult = {
  broker: { name: string; slug: string }
  owner: { email: string; password?: string; generated_password: boolean; email_sent: boolean }
}

type CompanyOption = { id: string; name: string; status: string; industry: string | null }

const statusBadge = (status: string) => {
  if (status === 'active') return <Badge variant="success">Active</Badge>
  if (status === 'suspended') return <Badge variant="warning">Suspended</Badge>
  if (status === 'terminated') return <Badge variant="danger">Terminated</Badge>
  return <Badge variant="warning">{status}</Badge>
}

export default function Brokers() {
  const [brokers, setBrokers] = useState<Broker[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState<CreateForm>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [addError, setAddError] = useState('')
  const [result, setResult] = useState<CreateResult | null>(null)

  // Edit state
  const [editBroker, setEditBroker] = useState<Broker | null>(null)
  const [editForm, setEditForm] = useState<EditForm>({ status: '', support_routing: '' })
  const [editSaving, setEditSaving] = useState(false)
  const [editError, setEditError] = useState('')

  // Book view state
  const [bookBroker, setBookBroker] = useState<Broker | null>(null)
  const [bookSetups, setBookSetups] = useState<any[]>([])
  const [bookLoading, setBookLoading] = useState(false)

  async function viewBook(b: Broker) {
    setBookBroker(b)
    setBookLoading(true)
    try {
      const res = await api.get<{ setups: any[] }>(`/admin/brokers/${b.id}/client-setups`)
      setBookSetups(res.setups)
    } catch { setBookSetups([]) }
    setBookLoading(false)
  }

  // Link company state
  const [linkBroker, setLinkBroker] = useState<Broker | null>(null)
  const [companies, setCompanies] = useState<CompanyOption[]>([])
  const [companiesLoading, setCompaniesLoading] = useState(false)
  const [selectedCompanyId, setSelectedCompanyId] = useState('')
  const [linkSaving, setLinkSaving] = useState(false)
  const [linkError, setLinkError] = useState('')
  const [linkSuccess, setLinkSuccess] = useState('')

  function fetchBrokers() {
    setLoading(true)
    api.get<BrokerListResponse>('/admin/brokers')
      .then((res) => setBrokers(res.brokers))
      .catch(() => setBrokers([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchBrokers() }, [])

  const filtered = brokers.filter((b) =>
    b.name.toLowerCase().includes(search.toLowerCase()) ||
    b.slug.toLowerCase().includes(search.toLowerCase())
  )

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setAddError('')
    setSaving(true)
    try {
      const res = await api.post<CreateResult>(
        '/admin/brokers',
        {
          broker_name: form.broker_name.trim(),
          owner_email: form.owner_email.trim(),
          owner_name: form.owner_name.trim(),
          owner_password: form.owner_password.trim() || undefined,
          slug: form.slug.trim() || undefined,
          support_routing: form.support_routing,
          billing_mode: form.billing_mode,
          invoice_owner: form.invoice_owner,
        }
      )
      setShowAdd(false)
      setForm(EMPTY_FORM)
      setResult(res)
      fetchBrokers()
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Failed to create broker')
    } finally {
      setSaving(false)
    }
  }

  function openEdit(b: Broker) {
    setEditBroker(b)
    setEditForm({ status: b.status, support_routing: b.support_routing })
    setEditError('')
  }

  async function handleEdit(e: React.FormEvent) {
    e.preventDefault()
    if (!editBroker) return
    setEditError('')
    setEditSaving(true)
    try {
      await api.patch(`/admin/brokers/${editBroker.id}`, {
        status: editForm.status,
        support_routing: editForm.support_routing,
      })
      setEditBroker(null)
      fetchBrokers()
    } catch (err) {
      setEditError(err instanceof Error ? err.message : 'Update failed')
    } finally {
      setEditSaving(false)
    }
  }

  function closeAdd() {
    setShowAdd(false)
    setAddError('')
    setForm(EMPTY_FORM)
  }

  function closeResult() {
    setResult(null)
  }

  async function openLinkCompany(b: Broker) {
    setLinkBroker(b)
    setSelectedCompanyId('')
    setLinkError('')
    setLinkSuccess('')
    setCompaniesLoading(true)
    try {
      const res = await api.get<{ registrations: CompanyOption[] }>('/admin/business-registrations')
      setCompanies(res.registrations)
    } catch {
      setCompanies([])
    }
    setCompaniesLoading(false)
  }

  async function handleLinkCompany() {
    if (!linkBroker || !selectedCompanyId) return
    setLinkSaving(true)
    setLinkError('')
    setLinkSuccess('')
    try {
      await api.put(`/admin/brokers/${linkBroker.id}/companies/${selectedCompanyId}`, {
        status: 'active',
        permissions: { can_view_compliance: true, can_view_employees: true },
      })
      const company = companies.find(c => c.id === selectedCompanyId)
      setLinkSuccess(`${company?.name ?? 'Company'} linked to ${linkBroker.name}`)
      setSelectedCompanyId('')
      fetchBrokers()
    } catch (err) {
      setLinkError(err instanceof Error ? err.message : 'Failed to link company')
    } finally {
      setLinkSaving(false)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 font-[Space_Grotesk] tracking-tight">
            Brokers
          </h1>
          <p className="mt-2 text-sm text-zinc-500">
            Manage broker channel partners and their owner accounts.
          </p>
        </div>
        <Button size="sm" onClick={() => setShowAdd(true)}>
          Add Broker
        </Button>
      </div>

      <div className="mt-6">
        <Input
          label=""
          placeholder="Search brokers..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
      </div>

      <div className="mt-6">
        {loading ? (
          <p className="text-sm text-zinc-500">Loading...</p>
        ) : filtered.length === 0 ? (
          <p className="text-sm text-zinc-500">No brokers found.</p>
        ) : (
          <div className="overflow-hidden rounded-xl border border-zinc-800">
            <table className="w-full text-sm text-left">
              <thead className="bg-zinc-900/50 text-zinc-400">
                <tr>
                  <th className="px-4 py-3 font-medium">Broker</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Members</th>
                  <th className="px-4 py-3 font-medium">Companies</th>
                  <th className="px-4 py-3 font-medium">Billing</th>
                  <th className="px-4 py-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800">
                {filtered.map((b) => (
                  <tr key={b.id} className="text-zinc-300">
                    <td className="px-4 py-3">
                      <p className="font-medium text-zinc-100">{b.name}</p>
                      <p className="text-xs text-zinc-500">/{b.slug}</p>
                    </td>
                    <td className="px-4 py-3">{statusBadge(b.status)}</td>
                    <td className="px-4 py-3">{b.active_member_count}</td>
                    <td className="px-4 py-3">{b.active_company_count}</td>
                    <td className="px-4 py-3">
                      <span className="text-xs text-zinc-400 capitalize">{b.billing_mode}</span>
                      {b.active_contract?.pepm_rate ? (
                        <span className="ml-1 text-xs text-zinc-500">
                          ${b.active_contract.pepm_rate}/pepm
                        </span>
                      ) : null}
                    </td>
                    <td className="px-4 py-3 text-right space-x-1">
                      <Button size="sm" variant="ghost" onClick={() => viewBook(b)}>
                        Book
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => openLinkCompany(b)}>
                        <Link2 size={12} className="mr-1" />
                        Link
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => openEdit(b)}>
                        Edit
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Create Modal */}
      <Modal open={showAdd} onClose={closeAdd} title="Add Broker" width="lg">
        <form onSubmit={handleCreate} className="space-y-4">
          <div>
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium mb-2">Broker Info</p>
            <div className="grid grid-cols-2 gap-3">
              <Input
                label="Broker Name"
                value={form.broker_name}
                onChange={(e) => setForm({ ...form, broker_name: e.target.value })}
                required
              />
              <Input
                label="Slug (optional)"
                placeholder="auto-generated"
                value={form.slug}
                onChange={(e) => setForm({ ...form, slug: e.target.value })}
              />
            </div>
          </div>

          <div>
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium mb-2">Owner Account</p>
            <div className="grid grid-cols-2 gap-3">
              <Input
                label="Full Name"
                value={form.owner_name}
                onChange={(e) => setForm({ ...form, owner_name: e.target.value })}
                required
              />
              <Input
                label="Email"
                type="email"
                value={form.owner_email}
                onChange={(e) => setForm({ ...form, owner_email: e.target.value })}
                required
              />
              <Input
                label="Password (optional)"
                type="password"
                placeholder="auto-generated if blank"
                value={form.owner_password}
                onChange={(e) => setForm({ ...form, owner_password: e.target.value })}
              />
            </div>
          </div>

          <div>
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium mb-2">Configuration</p>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Support Routing</label>
                <select
                  value={form.support_routing}
                  onChange={(e) => setForm({ ...form, support_routing: e.target.value })}
                  className="w-full bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
                >
                  <option value="shared">Shared</option>
                  <option value="broker_first">Broker First</option>
                  <option value="matcha_first">Matcha First</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Billing Mode</label>
                <select
                  value={form.billing_mode}
                  onChange={(e) => setForm({ ...form, billing_mode: e.target.value })}
                  className="w-full bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
                >
                  <option value="direct">Direct</option>
                  <option value="reseller">Reseller</option>
                  <option value="hybrid">Hybrid</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Invoice Owner</label>
                <select
                  value={form.invoice_owner}
                  onChange={(e) => setForm({ ...form, invoice_owner: e.target.value })}
                  className="w-full bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
                >
                  <option value="matcha">Matcha</option>
                  <option value="broker">Broker</option>
                </select>
              </div>
            </div>
          </div>

          {addError && <p className="text-sm text-red-400">{addError}</p>}

          <div className="flex items-center gap-2 pt-2 border-t border-zinc-800">
            <Button
              type="submit"
              size="sm"
              disabled={saving || !form.broker_name.trim() || !form.owner_email.trim() || !form.owner_name.trim()}
            >
              {saving ? 'Creating...' : 'Create Broker'}
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={closeAdd}>
              Cancel
            </Button>
          </div>
        </form>
      </Modal>

      {/* Edit Modal */}
      <Modal open={!!editBroker} onClose={() => setEditBroker(null)} title={`Edit — ${editBroker?.name}`} width="md">
        {editBroker && (
          <form onSubmit={handleEdit} className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Status</label>
                <select
                  value={editForm.status}
                  onChange={(e) => setEditForm({ ...editForm, status: e.target.value })}
                  className="w-full bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
                >
                  <option value="active">Active</option>
                  <option value="suspended">Suspended</option>
                  <option value="terminated">Terminated</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Support Routing</label>
                <select
                  value={editForm.support_routing}
                  onChange={(e) => setEditForm({ ...editForm, support_routing: e.target.value })}
                  className="w-full bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
                >
                  <option value="shared">Shared</option>
                  <option value="broker_first">Broker First</option>
                  <option value="matcha_first">Matcha First</option>
                </select>
              </div>
            </div>

            {editForm.status === 'terminated' && (
              <p className="text-xs text-red-400 bg-red-900/20 border border-red-800/30 rounded px-2 py-1.5">
                Terminating a broker will prevent them from logging in and managing clients. Existing client links will remain but no new onboarding will be possible.
              </p>
            )}

            {editError && <p className="text-sm text-red-400">{editError}</p>}

            <div className="flex items-center gap-2 pt-2 border-t border-zinc-800">
              <Button type="submit" size="sm" disabled={editSaving}>
                {editSaving ? 'Saving...' : 'Save Changes'}
              </Button>
              <Button type="button" variant="ghost" size="sm" onClick={() => setEditBroker(null)}>
                Cancel
              </Button>
            </div>
          </form>
        )}
      </Modal>

      {/* Book of Business Modal */}
      <Modal open={!!bookBroker} onClose={() => setBookBroker(null)} title={`${bookBroker?.name ?? ''} — Book of Business`} width="lg">
        {bookLoading ? (
          <p className="text-sm text-zinc-500 py-4">Loading...</p>
        ) : bookSetups.length === 0 ? (
          <p className="text-sm text-zinc-500 py-4">No client setups submitted by this broker.</p>
        ) : (
          <div className="space-y-3 max-h-[60vh] overflow-y-auto">
            {bookSetups.map((s: any) => (
              <div key={s.id} className="border border-zinc-800 rounded-lg p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-zinc-100">{s.company_name}</p>
                    <p className="text-xs text-zinc-500">
                      {s.industry ?? '—'} · {s.company_size ?? '—'} · {s.headcount ? `${s.headcount} employees` : '—'}
                    </p>
                  </div>
                  <Badge variant={s.status === 'activated' ? 'success' : s.status === 'invited' ? 'warning' : 'neutral'}>
                    {s.status}
                  </Badge>
                </div>
                {s.contact_name && (
                  <p className="text-xs text-zinc-400">Contact: {s.contact_name} {s.contact_email ? `· ${s.contact_email}` : ''} {s.contact_phone ? `· ${s.contact_phone}` : ''}</p>
                )}
                {s.locations && s.locations.length > 0 && (
                  <div>
                    <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Locations / Jurisdictions</p>
                    <div className="flex flex-wrap gap-1">
                      {s.locations.map((loc: any, i: number) => (
                        <span key={i} className="text-[11px] bg-zinc-800 text-zinc-300 px-2 py-0.5 rounded">
                          {loc.city}{loc.state ? `, ${loc.state}` : ''} {loc.type ? `(${loc.type})` : ''}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {s.specialties && (
                  <div>
                    <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Specialties</p>
                    <p className="text-xs text-zinc-300">{s.specialties}</p>
                  </div>
                )}
                {s.notes && (
                  <div>
                    <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Notes</p>
                    <p className="text-xs text-zinc-400">{s.notes}</p>
                  </div>
                )}
                <p className="text-[10px] text-zinc-600">Submitted {new Date(s.created_at).toLocaleDateString()}</p>
              </div>
            ))}
          </div>
        )}
      </Modal>

      {/* Link Company Modal */}
      <Modal open={!!linkBroker} onClose={() => setLinkBroker(null)} title={`Link Company to ${linkBroker?.name ?? ''}`} width="md">
        <div className="space-y-4">
          {companiesLoading ? (
            <p className="text-sm text-zinc-500">Loading companies...</p>
          ) : (
            <>
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Select Company</label>
                <select
                  value={selectedCompanyId}
                  onChange={(e) => setSelectedCompanyId(e.target.value)}
                  className="w-full bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
                >
                  <option value="">Choose a company...</option>
                  {companies.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} — {c.status}{c.industry ? ` (${c.industry})` : ''}
                    </option>
                  ))}
                </select>
              </div>

              {linkError && <p className="text-sm text-red-400">{linkError}</p>}
              {linkSuccess && (
                <div className="text-sm text-emerald-400 bg-emerald-900/20 border border-emerald-800/30 rounded px-3 py-2">
                  {linkSuccess}
                </div>
              )}

              <div className="flex items-center gap-2 pt-2 border-t border-zinc-800">
                <Button size="sm" onClick={handleLinkCompany} disabled={linkSaving || !selectedCompanyId}>
                  {linkSaving ? 'Linking...' : 'Link Company'}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setLinkBroker(null)}>
                  {linkSuccess ? 'Done' : 'Cancel'}
                </Button>
              </div>
            </>
          )}
        </div>
      </Modal>

      {/* Success Modal */}
      <Modal open={!!result} onClose={closeResult} title="Broker Created" width="md">
        {result && (
          <div className="space-y-4">
            <div className="bg-zinc-800/50 rounded-lg p-3 space-y-1">
              <p className="text-xs text-zinc-500 uppercase tracking-wider font-medium">Broker</p>
              <p className="text-zinc-100 font-medium">{result.broker.name}</p>
              <p className="text-xs text-zinc-500">/{result.broker.slug}</p>
            </div>
            <div className="bg-zinc-800/50 rounded-lg p-3 space-y-1">
              <p className="text-xs text-zinc-500 uppercase tracking-wider font-medium">Owner Account</p>
              <p className="text-zinc-100">{result.owner.email}</p>
              {result.owner.generated_password && result.owner.password && (
                <div className="mt-2">
                  <p className="text-xs text-zinc-500 mb-1">Generated password (share securely):</p>
                  <code className="block bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-emerald-400 text-sm font-mono select-all">
                    {result.owner.password}
                  </code>
                </div>
              )}
              {result.owner.email_sent && (
                <p className="text-xs text-emerald-500 mt-1">Welcome email sent.</p>
              )}
            </div>
            <div className="flex justify-end pt-2 border-t border-zinc-800">
              <Button size="sm" onClick={closeResult}>Done</Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
