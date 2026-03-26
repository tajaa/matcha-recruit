import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import { Badge, Button, Input, Modal } from '../../components/ui'
import { Plus, Loader2, Accessibility } from 'lucide-react'

type AccommodationCase = {
  id: string
  case_number: string
  employee_id: string
  title: string
  description: string | null
  disability_category: string | null
  status: string
  requested_accommodation: string | null
  approved_accommodation: string | null
  document_count: number
  created_at: string
  updated_at: string
}

type EmployeeOption = { id: string; name: string; department: string | null }

type CreateForm = {
  employee_id: string
  title: string
  description: string
  disability_category: string
  requested_accommodation: string
}

const EMPTY_FORM: CreateForm = {
  employee_id: '',
  title: '',
  description: '',
  disability_category: '',
  requested_accommodation: '',
}

const STATUS_BADGE: Record<string, 'success' | 'warning' | 'danger' | 'neutral'> = {
  requested: 'warning',
  interactive_process: 'warning',
  medical_review: 'warning',
  approved: 'success',
  implemented: 'success',
  review: 'neutral',
  denied: 'danger',
  closed: 'neutral',
}

const STATUS_LABEL: Record<string, string> = {
  requested: 'Requested',
  interactive_process: 'Interactive Process',
  medical_review: 'Medical Review',
  approved: 'Approved',
  implemented: 'Implemented',
  review: 'Under Review',
  denied: 'Denied',
  closed: 'Closed',
}

const CATEGORY_LABEL: Record<string, string> = {
  physical: 'Physical',
  cognitive: 'Cognitive',
  sensory: 'Sensory',
  mental_health: 'Mental Health',
  chronic_illness: 'Chronic Illness',
  pregnancy: 'Pregnancy',
  other: 'Other',
}

export default function Accommodations() {
  const navigate = useNavigate()
  const [cases, setCases] = useState<AccommodationCase[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState<CreateForm>(EMPTY_FORM)
  const [employees, setEmployees] = useState<EmployeeOption[]>([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')

  useEffect(() => {
    setLoading(true)
    const params = statusFilter !== 'all' ? `?status=${statusFilter}` : ''
    api.get<{ cases: AccommodationCase[]; total: number }>(`/accommodations${params}`)
      .then((res) => setCases(res.cases))
      .catch(() => setCases([]))
      .finally(() => setLoading(false))
  }, [statusFilter])

  function openCreate() {
    setShowCreate(true)
    setForm(EMPTY_FORM)
    setError('')
    api.get<EmployeeOption[]>('/accommodations/employees')
      .then(setEmployees)
      .catch(() => setEmployees([]))
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      const res = await api.post<AccommodationCase>('/accommodations', {
        employee_id: form.employee_id,
        title: form.title.trim(),
        description: form.description.trim() || undefined,
        disability_category: form.disability_category || undefined,
        requested_accommodation: form.requested_accommodation.trim() || undefined,
      })
      setShowCreate(false)
      navigate(`/app/accommodations/${res.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">
            ADA Accommodations
          </h1>
          <p className="mt-2 text-sm text-zinc-500">
            Manage accommodation requests — confidential, separate from employee files.
          </p>
        </div>
        <Button size="sm" onClick={openCreate}>
          <Plus size={14} className="mr-1" />
          New Request
        </Button>
      </div>

      <div className="flex items-center gap-3 mt-5 mb-4">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="w-48 bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
        >
          <option value="all">All Statuses</option>
          <option value="requested">Requested</option>
          <option value="interactive_process">Interactive Process</option>
          <option value="medical_review">Medical Review</option>
          <option value="approved">Approved</option>
          <option value="implemented">Implemented</option>
          <option value="denied">Denied</option>
          <option value="closed">Closed</option>
        </select>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="animate-spin text-zinc-500" size={20} />
        </div>
      ) : cases.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-zinc-500 border border-zinc-800 rounded-xl border-dashed">
          <Accessibility className="h-10 w-10 mb-3 text-zinc-600" />
          <p className="text-sm font-medium text-zinc-400">No accommodation cases</p>
          <p className="text-xs mt-1">Create a new request to start the interactive process.</p>
          <Button size="sm" className="mt-4" onClick={openCreate}>
            New Request
          </Button>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-zinc-800">
          <table className="w-full text-sm text-left">
            <thead className="bg-zinc-900/50 text-zinc-400">
              <tr>
                <th className="px-4 py-3 font-medium">Case</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Category</th>
                <th className="px-4 py-3 font-medium">Docs</th>
                <th className="px-4 py-3 font-medium">Updated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {cases.map((c) => (
                <tr
                  key={c.id}
                  className="text-zinc-300 hover:bg-zinc-900/30 cursor-pointer transition-colors"
                  onClick={() => navigate(`/app/accommodations/${c.id}`)}
                >
                  <td className="px-4 py-3">
                    <p className="font-medium text-zinc-100">{c.title}</p>
                    <p className="text-xs text-zinc-500">{c.case_number}</p>
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={STATUS_BADGE[c.status] ?? 'neutral'}>
                      {STATUS_LABEL[c.status] ?? c.status}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-xs text-zinc-500">
                    {CATEGORY_LABEL[c.disability_category ?? ''] ?? '—'}
                  </td>
                  <td className="px-4 py-3 text-xs text-zinc-500">{c.document_count}</td>
                  <td className="px-4 py-3 text-xs text-zinc-500">
                    {new Date(c.updated_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create Modal */}
      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="New Accommodation Request" width="lg">
        <form onSubmit={handleCreate} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-zinc-300 mb-1">Employee</label>
            <select
              value={form.employee_id}
              onChange={(e) => setForm({ ...form, employee_id: e.target.value })}
              className="w-full bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
              required
            >
              <option value="">Select employee...</option>
              {employees.map((emp) => (
                <option key={emp.id} value={emp.id}>
                  {emp.name}{emp.department ? ` (${emp.department})` : ''}
                </option>
              ))}
            </select>
          </div>
          <Input
            label="Title"
            placeholder="e.g., Schedule modification for medical appointments"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            required
          />
          <div>
            <label className="block text-sm font-medium text-zinc-300 mb-1">Disability Category</label>
            <select
              value={form.disability_category}
              onChange={(e) => setForm({ ...form, disability_category: e.target.value })}
              className="w-full bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
            >
              <option value="">Select category...</option>
              {Object.entries(CATEGORY_LABEL).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-zinc-300 mb-1">Description</label>
            <textarea
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="Describe the accommodation need..."
              rows={3}
              className="w-full bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500 resize-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-zinc-300 mb-1">Requested Accommodation</label>
            <textarea
              value={form.requested_accommodation}
              onChange={(e) => setForm({ ...form, requested_accommodation: e.target.value })}
              placeholder="What accommodation is being requested?"
              rows={2}
              className="w-full bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500 resize-none"
            />
          </div>

          {error && <p className="text-sm text-red-400">{error}</p>}

          <div className="flex items-center gap-2 pt-2 border-t border-zinc-800">
            <Button type="submit" size="sm" disabled={saving || !form.employee_id || !form.title.trim()}>
              {saving ? 'Creating...' : 'Create Request'}
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => setShowCreate(false)}>
              Cancel
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
