import { useState } from 'react'
import { Button, Input } from '../../components/ui'
import { api } from '../../api/client'
import { useAsync } from '../../hooks/useAsync'
import {
  EMPTY_FORM,
  type Broker,
  type BrokerListResponse,
  type CompanyOption,
  type CreateForm,
  type CreateResult,
  type EditForm,
} from './Brokers/types'
import { BrokerTable } from './Brokers/BrokerTable'
import { AddBrokerModal } from './Brokers/AddBrokerModal'
import { EditBrokerModal } from './Brokers/EditBrokerModal'
import { BookOfBusinessModal } from './Brokers/BookOfBusinessModal'
import { LinkCompanyModal } from './Brokers/LinkCompanyModal'
import { BrokerCreatedModal } from './Brokers/BrokerCreatedModal'

export default function Brokers() {
  const [search, setSearch] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState<CreateForm>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [addError, setAddError] = useState('')
  const [result, setResult] = useState<CreateResult | null>(null)

  // Edit state
  const [editBroker, setEditBroker] = useState<Broker | null>(null)
  const [editForm, setEditForm] = useState<EditForm>({ status: '', support_routing: '', allocated_seats: '', plan: 'standard' })
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

  const {
    data: brokers,
    loading,
    error,
    reload: fetchBrokers,
  } = useAsync(
    () => api.get<BrokerListResponse>('/admin/brokers').then((res) => res.brokers),
    [],
    [],
  )

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
          allocated_seats: parseInt(form.allocated_seats, 10) || 0,
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
    setEditForm({ status: b.status, support_routing: b.support_routing, allocated_seats: String(b.allocated_seats ?? 0), plan: b.plan ?? 'standard' })
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
        allocated_seats: parseInt(editForm.allocated_seats, 10) || 0,
        plan: editForm.plan,
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
          <h1 className="text-2xl font-semibold text-zinc-100">
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
        <BrokerTable
          loading={loading}
          error={error}
          filtered={filtered}
          onViewBook={viewBook}
          onLinkCompany={openLinkCompany}
          onEdit={openEdit}
        />
      </div>

      <AddBrokerModal
        open={showAdd}
        form={form}
        setForm={setForm}
        saving={saving}
        addError={addError}
        onClose={closeAdd}
        onSubmit={handleCreate}
      />

      <EditBrokerModal
        editBroker={editBroker}
        editForm={editForm}
        setEditForm={setEditForm}
        editSaving={editSaving}
        editError={editError}
        onClose={() => setEditBroker(null)}
        onSubmit={handleEdit}
      />

      <BookOfBusinessModal
        bookBroker={bookBroker}
        bookSetups={bookSetups}
        bookLoading={bookLoading}
        onClose={() => setBookBroker(null)}
      />

      <LinkCompanyModal
        linkBroker={linkBroker}
        companies={companies}
        companiesLoading={companiesLoading}
        selectedCompanyId={selectedCompanyId}
        setSelectedCompanyId={setSelectedCompanyId}
        linkSaving={linkSaving}
        linkError={linkError}
        linkSuccess={linkSuccess}
        onClose={() => setLinkBroker(null)}
        onLink={handleLinkCompany}
      />

      <BrokerCreatedModal result={result} onClose={closeResult} />
    </div>
  )
}
