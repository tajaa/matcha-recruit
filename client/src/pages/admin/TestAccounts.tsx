import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Building2, Copy, ExternalLink, Plus, ShieldCheck } from 'lucide-react'
import { api } from '../../api/client'
import { Badge, Button, DataTable, Input, Modal } from '../../components/ui'
import { useAsync } from '../../hooks/useAsync'

type TestAccount = {
  id: string
  company_name: string
  industry: string | null
  company_size: string | null
  status: string
  created_at: string | null
  signup_source: string | null
  owner_email: string | null
  owner_name: string | null
}

type ProvisionedAccount = {
  company_id: string
  company_name: string
  email: string
  password: string
  generated_password: boolean
  seeded_manager_email: string | null
  seeded_employee_email: string | null
  seeded_portal_password: string | null
}

type NewTestAccount = {
  company_name: string
  industry: string
  company_size: string
  name: string
  email: string
  password: string
}

const EMPTY_FORM: NewTestAccount = {
  company_name: '',
  industry: '',
  company_size: '',
  name: '',
  email: '',
  password: '',
}

function dateLabel(value: string | null) {
  return value ? new Date(value).toLocaleDateString() : '—'
}

export default function TestAccounts() {
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState<NewTestAccount>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [created, setCreated] = useState<ProvisionedAccount | null>(null)

  const { data: accounts, loading, error: loadError, reload } = useAsync(
    () => api.get<{ test_accounts: TestAccount[] }>('/admin/test-accounts').then((result) => result.test_accounts),
    [],
    [],
  )

  async function createAccount(event: React.FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      const result = await api.post<ProvisionedAccount>('/auth/register/test-account', {
        ...form,
        password: form.password || undefined,
        industry: form.industry || undefined,
        company_size: form.company_size || undefined,
      })
      setCreated(result)
      setShowCreate(false)
      setForm(EMPTY_FORM)
      await reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the test account')
    } finally {
      setSaving(false)
    }
  }

  async function removeTestStatus(account: TestAccount) {
    if (!window.confirm(
      `Remove ${account.company_name} from test accounts?\n\nIt will no longer sync between dev and production, and future dev refreshes will anonymize it.`,
    )) return
    await api.patch(`/admin/companies/${account.id}`, { is_test: false })
    await reload()
  }

  async function copy(text: string) {
    await navigator.clipboard.writeText(text)
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-amber-300" />
            <h1 className="text-2xl font-semibold text-zinc-100">Test Accounts</h1>
          </div>
          <p className="mt-1 max-w-3xl text-sm text-zinc-400">
            Demo tenants may use beta features, sync between dev and production, and are preserved during a dev refresh. Never mark a live customer as a test account.
          </p>
        </div>
        <Button onClick={() => { setError(''); setShowCreate(true) }}>
          <Plus className="mr-1.5 h-4 w-4" /> Create test account
        </Button>
      </div>

      {loadError && <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{loadError}</p>}

      <DataTable
        rows={accounts}
        rowKey={(account) => account.id}
        loading={loading}
        error={loadError}
        emptyText="No test accounts yet."
        columns={[
          {
            key: 'company_name', header: 'Company', render: (account) => (
              <div>
                <Link to={`/admin/companies/${account.id}`} className="font-medium text-zinc-100 hover:text-emerald-400">
                  {account.company_name}
                </Link>
                <p className="text-xs text-zinc-500">{account.industry || 'No industry'} · {account.company_size || 'No size'}</p>
              </div>
            ),
          },
          {
            key: 'owner_email', header: 'Owner', render: (account) => (
              <div className="text-sm text-zinc-300">
                <div>{account.owner_name || '—'}</div>
                <div className="text-xs text-zinc-500">{account.owner_email || 'No client login'}</div>
              </div>
            ),
          },
          { key: 'created_at', header: 'Created', render: (account) => dateLabel(account.created_at) },
          { key: 'status', header: 'Status', render: () => <Badge variant="warning">Test</Badge> },
          {
            key: 'actions', header: '', align: 'right', render: (account) => (
              <div className="flex justify-end gap-2">
                <Link to={`/admin/companies/${account.id}`} className="inline-flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300">
                  Manage <ExternalLink className="h-3.5 w-3.5" />
                </Link>
                <Button size="sm" variant="ghost" onClick={() => removeTestStatus(account)}>Remove test</Button>
              </div>
            ),
          },
        ]}
      />

      <Modal open={showCreate} onClose={() => !saving && setShowCreate(false)} title="Create seeded test account" width="lg">
        <form onSubmit={createAccount} className="space-y-4">
          <p className="text-sm text-zinc-400">Creates an approved test tenant with the standard seeded demo data and enabled test-account features.</p>
          <div className="grid grid-cols-2 gap-3">
            <Input label="Company name" value={form.company_name} onChange={(event) => setForm({ ...form, company_name: event.target.value })} required />
            <Input label="Owner name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required />
            <Input label="Owner email" type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required />
            <Input label="Password (optional)" type="text" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} placeholder="Generated if blank" />
            <Input label="Industry (optional)" value={form.industry} onChange={(event) => setForm({ ...form, industry: event.target.value })} />
            <Input label="Company size (optional)" value={form.company_size} onChange={(event) => setForm({ ...form, company_size: event.target.value })} />
          </div>
          {error && <p className="text-sm text-red-300">{error}</p>}
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={() => setShowCreate(false)} disabled={saving}>Cancel</Button>
            <Button type="submit" disabled={saving}>{saving ? 'Creating…' : 'Create test account'}</Button>
          </div>
        </form>
      </Modal>

      <Modal open={Boolean(created)} onClose={() => setCreated(null)} title="Test account created" width="md">
        {created && (
          <div className="space-y-4">
            <p className="text-sm text-amber-200">Save these credentials now. A generated password is only shown once.</p>
            <Credential label="Login email" value={created.email} onCopy={copy} />
            <Credential label="Password" value={created.password} onCopy={copy} />
            {created.seeded_manager_email && <Credential label="Seeded manager login" value={created.seeded_manager_email} onCopy={copy} />}
            {created.seeded_employee_email && <Credential label="Seeded employee login" value={created.seeded_employee_email} onCopy={copy} />}
            {created.seeded_portal_password && <Credential label="Seeded portal password" value={created.seeded_portal_password} onCopy={copy} />}
            <div className="flex justify-end gap-2 pt-2">
              <Link to={`/admin/companies/${created.company_id}`} className="inline-flex items-center gap-1 rounded-lg bg-zinc-800 px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-700">
                <Building2 className="h-4 w-4" /> Manage company
              </Link>
              <Button onClick={() => setCreated(null)}>Done</Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}

function Credential({ label, value, onCopy }: { label: string; value: string; onCopy: (value: string) => Promise<void> }) {
  return (
    <div>
      <p className="mb-1 text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</p>
      <div className="flex items-center gap-2 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 font-mono text-sm text-zinc-100">
        <span className="min-w-0 flex-1 break-all">{value}</span>
        <button type="button" onClick={() => onCopy(value)} className="text-zinc-400 hover:text-zinc-100" title={`Copy ${label}`}>
          <Copy className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
