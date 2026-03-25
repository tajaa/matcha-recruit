import { useEffect, useState } from 'react'
import { Badge, Button, Input, Modal } from '../../components/ui'
import { api } from '../../api/client'

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

type CreateResult = {
  broker: { name: string; slug: string }
  owner: { email: string; password?: string; generated_password: boolean; email_sent: boolean }
}

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

  function closeAdd() {
    setShowAdd(false)
    setAddError('')
    setForm(EMPTY_FORM)
  }

  function closeResult() {
    setResult(null)
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
