import { useEffect, useState } from 'react'
import { Card, Badge, Button, Input } from '../../components/ui'
import { api } from '../../api/client'

// --- Types ---

type ERCase = {
  id: string
  case_number: string
  title: string
  description: string | null
  status: string
  category: string
  outcome: string | null
  document_count: number
  created_at: string
  updated_at: string
}

type ERNote = {
  id: string
  note_type: string
  content: string
  created_at: string
}

type CaseListResponse = {
  cases: ERCase[]
  total: number
}

// --- Helpers ---

const CATEGORIES = [
  'harassment', 'discrimination', 'safety', 'retaliation',
  'policy_violation', 'misconduct', 'wage_hour', 'other',
] as const

const categoryLabel: Record<string, string> = {
  harassment: 'Harassment',
  discrimination: 'Discrimination',
  safety: 'Safety',
  retaliation: 'Retaliation',
  policy_violation: 'Policy Violation',
  misconduct: 'Misconduct',
  wage_hour: 'Wage & Hour',
  other: 'Other',
}

const statusBadge = (status: string) => {
  switch (status) {
    case 'open': return <Badge variant="warning">Open</Badge>
    case 'in_review': return <Badge variant="neutral">In Review</Badge>
    case 'pending_determination': return <Badge variant="warning">Pending</Badge>
    case 'closed': return <Badge variant="success">Closed</Badge>
    default: return <Badge variant="neutral">{status}</Badge>
  }
}

const categoryBadge = (cat: string) => (
  <Badge variant="neutral">{categoryLabel[cat] ?? cat}</Badge>
)

const EMPTY_FORM = { title: '', description: '', category: 'other' }

// --- Component ---

export default function ERCopilot() {
  const [cases, setCases] = useState<ERCase[]>([])
  const [filter, setFilter] = useState<'all' | 'open' | 'in_review' | 'closed'>('all')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)

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
      setCases((prev) => [created, ...prev])
      setForm(EMPTY_FORM)
      setShowForm(false)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 font-[Space_Grotesk]">
            ER Copilot
          </h1>
          <p className="mt-2 text-sm text-zinc-500">
            Employee relations case management.
          </p>
        </div>
        <Button onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancel' : 'New Case'}
        </Button>
      </div>

      {/* Create form */}
      {showForm && (
        <Card className="mt-6">
          <form onSubmit={handleCreate} className="grid gap-4 sm:grid-cols-2">
            <Input
              id="title"
              label="Case title"
              required
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="Brief description of the matter"
            />
            <div>
              <label htmlFor="category" className="block text-sm font-medium text-zinc-300 mb-1.5">
                Category
              </label>
              <select
                id="category"
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3.5 py-2.5 text-sm text-zinc-100 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-colors"
              >
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>{categoryLabel[c]}</option>
                ))}
              </select>
            </div>
            <div className="sm:col-span-2">
              <Input
                id="description"
                label="Description"
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder="Optional details about the case"
              />
            </div>
            <div className="sm:col-span-2">
              <Button type="submit" disabled={saving}>
                {saving ? 'Creating...' : 'Create Case'}
              </Button>
            </div>
          </form>
        </Card>
      )}

      {/* Filters */}
      <div className="mt-6 flex items-center gap-3">
        <Input
          label=""
          placeholder="Search cases..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <div className="flex gap-1 ml-auto">
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
              <div key={c.id}>
                <Card
                  className={`p-5 cursor-pointer transition-colors hover:border-zinc-700 ${
                    selectedId === c.id ? 'border-zinc-600' : ''
                  }`}
                  onClick={() => setSelectedId(selectedId === c.id ? null : c.id)}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs text-zinc-500 font-mono">{c.case_number}</span>
                        {statusBadge(c.status)}
                        {categoryBadge(c.category)}
                      </div>
                      <p className="text-sm font-medium text-zinc-100 truncate">{c.title}</p>
                      {c.description && (
                        <p className="text-xs text-zinc-500 mt-1 line-clamp-2">{c.description}</p>
                      )}
                    </div>
                    <div className="text-right shrink-0">
                      <p className="text-xs text-zinc-500">
                        {new Date(c.created_at).toLocaleDateString()}
                      </p>
                      {c.document_count > 0 && (
                        <p className="text-xs text-zinc-600 mt-1">{c.document_count} doc{c.document_count > 1 ? 's' : ''}</p>
                      )}
                    </div>
                  </div>
                </Card>

                {/* Expanded detail */}
                {selectedId === c.id && <CaseDetail caseId={c.id} />}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// --- Case Detail (notes + actions) ---

function CaseDetail({ caseId }: { caseId: string }) {
  const [notes, setNotes] = useState<ERNote[]>([])
  const [loading, setLoading] = useState(true)
  const [newNote, setNewNote] = useState('')
  const [posting, setPosting] = useState(false)

  useEffect(() => {
    api.get<ERNote[]>(`/er/cases/${caseId}/notes`)
      .then(setNotes)
      .catch(() => setNotes([]))
      .finally(() => setLoading(false))
  }, [caseId])

  async function addNote(e: React.FormEvent) {
    e.preventDefault()
    if (!newNote.trim()) return
    setPosting(true)
    try {
      const note = await api.post<ERNote>(`/er/cases/${caseId}/notes`, {
        note_type: 'general',
        content: newNote,
      })
      setNotes((prev) => [...prev, note])
      setNewNote('')
    } finally {
      setPosting(false)
    }
  }

  const noteTypeBadge = (type: string) => {
    switch (type) {
      case 'guidance': return <Badge variant="success">Guidance</Badge>
      case 'question': return <Badge variant="warning">Question</Badge>
      case 'system': return <Badge variant="neutral">System</Badge>
      default: return null
    }
  }

  return (
    <Card className="mt-1 p-5 border-zinc-700">
      <h3 className="text-sm font-medium text-zinc-300 mb-3">Case Notes</h3>

      {loading ? (
        <p className="text-xs text-zinc-500">Loading notes...</p>
      ) : notes.length === 0 ? (
        <p className="text-xs text-zinc-500 mb-4">No notes yet.</p>
      ) : (
        <div className="space-y-3 mb-4 max-h-64 overflow-y-auto">
          {notes.map((n) => (
            <div key={n.id} className="rounded-lg bg-zinc-900/50 border border-zinc-800 px-4 py-3">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-[10px] text-zinc-500">
                  {new Date(n.created_at).toLocaleString()}
                </span>
                {noteTypeBadge(n.note_type)}
              </div>
              <p className="text-sm text-zinc-300 whitespace-pre-wrap">{n.content}</p>
            </div>
          ))}
        </div>
      )}

      <form onSubmit={addNote} className="flex gap-2">
        <Input
          id={`note-${caseId}`}
          label=""
          value={newNote}
          onChange={(e) => setNewNote(e.target.value)}
          placeholder="Add a note..."
          className="flex-1"
        />
        <Button type="submit" size="sm" disabled={posting || !newNote.trim()}>
          {posting ? 'Posting...' : 'Add'}
        </Button>
      </form>
    </Card>
  )
}
