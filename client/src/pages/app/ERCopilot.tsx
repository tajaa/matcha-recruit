import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Input, Modal, Select, Textarea } from '../../components/ui'
import { ERCaseCard } from '../../components/er/ERCaseCard'
import { api } from '../../api/client'
import type { ERCase, CaseListResponse } from '../../types/er'
import { CATEGORIES, categoryLabel } from '../../types/er'

const CATEGORY_OPTIONS = CATEGORIES.map((c) => ({ value: c, label: categoryLabel[c] }))

const EMPTY_FORM = { title: '', description: '', category: 'other' }

export default function ERCopilot() {
  const navigate = useNavigate()
  const [cases, setCases] = useState<ERCase[]>([])
  const [filter, setFilter] = useState<'all' | 'open' | 'in_review' | 'closed'>('all')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setLoading(true)
    const params = filter !== 'all' ? `?status=${filter}` : ''
    api.get<CaseListResponse>(`/er/cases${params}`)
      .then((res) => setCases(res.cases))
      .catch(() => setCases([]))
      .finally(() => setLoading(false))
  }, [filter])

  const filtered = cases.filter((c) =>
    c.title.toLowerCase().includes(search.toLowerCase()) ||
    c.case_number.toLowerCase().includes(search.toLowerCase())
  )

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      const created = await api.post<ERCase>('/er/cases', {
        title: form.title,
        description: form.description || null,
        category: form.category,
      })
      navigate(`/app/er-copilot/${created.id}`)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 sm:gap-0">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">
            ER Copilot
          </h1>
          <p className="mt-2 text-sm text-zinc-500">
            Employee relations case management.
          </p>
        </div>
        <Button onClick={() => setShowForm(true)}>New Case</Button>
      </div>

      <Modal open={showForm} onClose={() => setShowForm(false)} title="New Case">
        <form onSubmit={handleCreate} className="space-y-4">
          <Input
            label="Case title"
            required
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            placeholder="Brief description of the matter"
          />
          <Select
            label="Category"
            options={CATEGORY_OPTIONS}
            value={form.category}
            onChange={(e) => setForm({ ...form, category: e.target.value })}
          />
          <Textarea
            label="Description"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="Optional details about the case"
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" type="button" onClick={() => setShowForm(false)}>Cancel</Button>
            <Button type="submit" disabled={saving}>
              {saving ? 'Creating...' : 'Create Case'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Filters */}
      <div className="mt-6 flex flex-col sm:flex-row items-start sm:items-center gap-3 sm:gap-4 flex-wrap">
        <Input
          label=""
          placeholder="Search cases..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <div className="flex gap-1 w-full sm:w-auto sm:ml-auto overflow-x-auto pb-2 sm:pb-0">
          {(['all', 'open', 'in_review', 'closed'] as const).map((s) => (
            <Button
              key={s}
              variant={filter === s ? 'primary' : 'ghost'}
              size="sm"
              onClick={() => setFilter(s)}
            >
              {s === 'in_review' ? 'In Review' : s.charAt(0).toUpperCase() + s.slice(1)}
            </Button>
          ))}
        </div>
      </div>

      {/* Case list */}
      <div className="mt-6">
        {loading ? (
          <p className="text-sm text-zinc-500">Loading...</p>
        ) : filtered.length === 0 ? (
          <p className="text-sm text-zinc-500">No cases found.</p>
        ) : (
          <div className="space-y-3">
            {filtered.map((c) => (
              <ERCaseCard
                key={c.id}
                case_={c}
                onClick={() => navigate(`/app/er-copilot/${c.id}`)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
