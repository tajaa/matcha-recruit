import { useEffect, useState } from 'react'
import { Building2, Plus, Loader2, Send, AlertCircle } from 'lucide-react'
import { Button, Input, Modal, Badge } from '../../components/ui'
import { api } from '../../api/client'

type ClientSetup = {
  id: string
  company_name: string
  contact_name: string | null
  contact_email: string | null
  status: string
  invite_token: string | null
  invite_expires_at: string | null
  created_at: string
}

type SetupForm = {
  company_name: string
  contact_name: string
  contact_email: string
  contact_phone: string
  industry: string
  company_size: string
  headcount: string
  invite_immediately: boolean
}

const EMPTY_SETUP: SetupForm = {
  company_name: '',
  contact_name: '',
  contact_email: '',
  contact_phone: '',
  industry: '',
  company_size: '',
  headcount: '1',
  invite_immediately: true,
}

const statusBadge = (status: string) => {
  if (status === 'active' || status === 'registered') return <Badge variant="success">{status}</Badge>
  if (status === 'invited' || status === 'pending') return <Badge variant="warning">{status}</Badge>
  if (status === 'expired') return <Badge variant="danger">Expired</Badge>
  return <Badge variant="warning">{status}</Badge>
}

export default function BrokerClients() {
  const [setups, setSetups] = useState<ClientSetup[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState<SetupForm>(EMPTY_SETUP)
  const [saving, setSaving] = useState(false)
  const [addError, setAddError] = useState('')
  const [sendingInvite, setSendingInvite] = useState<string | null>(null)

  function fetchSetups() {
    setLoading(true)
    api.get<{ setups: ClientSetup[] }>('/brokers/client-setups')
      .then((res) => setSetups(res.setups))
      .catch(() => setError('Unable to load client setups'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchSetups() }, [])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setAddError('')
    setSaving(true)
    try {
      await api.post('/brokers/client-setups', {
        company_name: form.company_name.trim(),
        contact_name: form.contact_name.trim() || undefined,
        contact_email: form.contact_email.trim() || undefined,
        contact_phone: form.contact_phone.trim() || undefined,
        industry: form.industry.trim() || undefined,
        company_size: form.company_size.trim() || undefined,
        headcount: parseInt(form.headcount, 10) || undefined,
        invite_immediately: form.invite_immediately,
      })
      setShowAdd(false)
      setForm(EMPTY_SETUP)
      fetchSetups()
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Failed to create client setup')
    } finally {
      setSaving(false)
    }
  }

  async function sendInvite(setupId: string) {
    setSendingInvite(setupId)
    try {
      await api.post(`/brokers/client-setups/${setupId}/invite`, { expires_days: 14 })
      fetchSetups()
    } catch {}
    setSendingInvite(null)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 text-zinc-500 animate-spin" />
      </div>
    )
  }

  if (error && setups.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-zinc-500">
        <AlertCircle className="h-8 w-8 mb-2" />
        <p className="text-sm">{error}</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight">Client Onboarding</h1>
          <p className="text-sm text-zinc-500 mt-1">Create and manage client setups for your referred companies.</p>
        </div>
        <Button size="sm" onClick={() => setShowAdd(true)}>
          <Plus size={14} className="mr-1" />
          Add Client
        </Button>
      </div>

      {setups.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-zinc-500 border border-zinc-800 rounded-xl border-dashed">
          <Building2 className="h-10 w-10 mb-3 text-zinc-600" />
          <p className="text-sm font-medium text-zinc-400">No client setups yet</p>
          <p className="text-xs mt-1">Create a client setup to start onboarding a company.</p>
          <Button size="sm" className="mt-4" onClick={() => setShowAdd(true)}>
            Add Your First Client
          </Button>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-zinc-800">
          <table className="w-full text-sm text-left">
            <thead className="bg-zinc-900/50 text-zinc-400">
              <tr>
                <th className="px-4 py-3 font-medium">Company</th>
                <th className="px-4 py-3 font-medium">Contact</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Created</th>
                <th className="px-4 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {setups.map((s) => (
                <tr key={s.id} className="text-zinc-300">
                  <td className="px-4 py-3">
                    <p className="font-medium text-zinc-100">{s.company_name}</p>
                  </td>
                  <td className="px-4 py-3">
                    <p className="text-zinc-300">{s.contact_name || '—'}</p>
                    <p className="text-xs text-zinc-500">{s.contact_email || ''}</p>
                  </td>
                  <td className="px-4 py-3">{statusBadge(s.status)}</td>
                  <td className="px-4 py-3 text-xs text-zinc-500">
                    {new Date(s.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {(s.status === 'draft' || s.status === 'expired') && s.contact_email && (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={sendingInvite === s.id}
                        onClick={() => sendInvite(s.id)}
                      >
                        <Send size={12} className="mr-1" />
                        {sendingInvite === s.id ? 'Sending...' : 'Send Invite'}
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Add Client Setup Modal */}
      <Modal open={showAdd} onClose={() => { setShowAdd(false); setAddError('') }} title="Add Client" width="lg">
        <form onSubmit={handleCreate} className="space-y-4">
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
                  onChange={(e) => setForm({ ...form, industry: e.target.value })}
                  className="w-full bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
                >
                  <option value="">Select industry...</option>
                  <option value="healthcare">Healthcare</option>
                  <option value="manufacturing">Manufacturing</option>
                  <option value="technology">Technology</option>
                  <option value="retail">Retail</option>
                  <option value="hospitality">Hospitality</option>
                  <option value="construction">Construction</option>
                  <option value="finance">Finance</option>
                  <option value="education">Education</option>
                  <option value="other">Other</option>
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
                  <option value="1-10">1-10</option>
                  <option value="11-50">11-50</option>
                  <option value="51-200">51-200</option>
                  <option value="201-500">201-500</option>
                  <option value="501-1000">501-1000</option>
                  <option value="1001+">1001+</option>
                </select>
              </div>
              <Input
                label="Headcount"
                type="number"
                value={form.headcount}
                onChange={(e) => setForm({ ...form, headcount: e.target.value })}
              />
            </div>
          </div>

          <div>
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium mb-2">Primary Contact</p>
            <div className="grid grid-cols-2 gap-3">
              <Input
                label="Contact Name"
                value={form.contact_name}
                onChange={(e) => setForm({ ...form, contact_name: e.target.value })}
              />
              <Input
                label="Contact Email"
                type="email"
                value={form.contact_email}
                onChange={(e) => setForm({ ...form, contact_email: e.target.value })}
              />
              <Input
                label="Phone (optional)"
                value={form.contact_phone}
                onChange={(e) => setForm({ ...form, contact_phone: e.target.value })}
              />
            </div>
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="invite-immediately"
              checked={form.invite_immediately}
              onChange={(e) => setForm({ ...form, invite_immediately: e.target.checked })}
              className="rounded border-zinc-600 bg-zinc-800 text-emerald-600 focus:ring-emerald-500"
            />
            <label htmlFor="invite-immediately" className="text-sm text-zinc-400">
              Send invitation email immediately
            </label>
          </div>

          {addError && <p className="text-sm text-red-400">{addError}</p>}

          <div className="flex items-center gap-2 pt-2 border-t border-zinc-800">
            <Button type="submit" size="sm" disabled={saving || !form.company_name.trim()}>
              {saving ? 'Creating...' : 'Create Client Setup'}
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
