import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Card, Badge, Button, Input } from '../../components/ui'
import { api } from '../../api/client'

// --- Types ---

type Template = {
  id: string
  title: string
  description: string | null
  category: string
  is_employee_task: boolean
  due_days: number
  is_active: boolean
  sort_order: number
}

type Funnel = {
  invited: number
  accepted: number
  started: number
  completed: number
  ready_for_day1: number
}

type Analytics = {
  funnel: Funnel
  kpis: {
    time_to_ready_p50_days: number | null
    completion_before_start_rate: number | null
  }
  bottlenecks: { task_title: string; overdue_count: number; avg_days_overdue: number }[]
}

// --- Helpers ---

const CATEGORIES = ['documents', 'equipment', 'training', 'admin', 'return_to_work', 'priority'] as const

const categoryLabel: Record<string, string> = {
  documents: 'Documents',
  equipment: 'Equipment',
  training: 'Training',
  admin: 'Admin',
  return_to_work: 'Return to Work',
  priority: 'Priority',
}

const EMPTY_FORM = { title: '', description: '', category: 'admin', due_days: '7', is_employee_task: false }

// --- Component ---

export default function Onboarding() {
  const [templates, setTemplates] = useState<Template[]>([])
  const [analytics, setAnalytics] = useState<Analytics | null>(null)
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    Promise.all([
      api.get<Template[]>('/onboarding/templates'),
      api.get<Analytics>('/onboarding/analytics').catch(() => null),
    ])
      .then(([t, a]) => { setTemplates(t); setAnalytics(a) })
      .catch(() => setTemplates([]))
      .finally(() => setLoading(false))
  }, [])

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      const created = await api.post<Template>('/onboarding/templates', {
        title: form.title,
        description: form.description || null,
        category: form.category,
        due_days: Number(form.due_days),
        is_employee_task: form.is_employee_task,
      })
      setTemplates((prev) => [...prev, created])
      setForm(EMPTY_FORM)
      setShowForm(false)
    } finally {
      setSaving(false)
    }
  }

  async function toggleActive(t: Template) {
    const updated = await api.put<Template>(`/onboarding/templates/${t.id}`, {
      is_active: !t.is_active,
    })
    setTemplates((prev) => prev.map((x) => (x.id === t.id ? updated : x)))
  }

  async function deleteTemplate(id: string) {
    await api.delete(`/onboarding/templates/${id}`)
    setTemplates((prev) => prev.filter((x) => x.id !== id))
  }

  const grouped = CATEGORIES.reduce<Record<string, Template[]>>((acc, cat) => {
    const items = templates.filter((t) => t.category === cat)
    if (items.length > 0) acc[cat] = items
    return acc
  }, {})

  if (loading) return <p className="text-sm text-zinc-500">Loading...</p>

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 font-[Space_Grotesk]">
            Onboarding
          </h1>
          <p className="mt-2 text-sm text-zinc-500">
            Task templates and onboarding analytics.
          </p>
        </div>
        <Button onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancel' : 'Add Task'}
        </Button>
      </div>

      {/* Analytics funnel */}
      {analytics && (
        <div className="mt-6 grid gap-4 sm:grid-cols-5">
          {Object.entries(analytics.funnel).map(([key, val]) => (
            <Card key={key} className="p-4 text-center">
              <p className="text-2xl font-semibold text-zinc-100">{val}</p>
              <p className="text-xs text-zinc-500 mt-1">
                {key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
              </p>
            </Card>
          ))}
        </div>
      )}

      {/* KPIs */}
      {analytics?.kpis.time_to_ready_p50_days != null && (
        <div className="mt-4 flex gap-4">
          <Card className="flex-1 p-4">
            <p className="text-sm text-zinc-400">Median time to ready</p>
            <p className="text-lg font-semibold text-zinc-100 mt-1">
              {analytics.kpis.time_to_ready_p50_days.toFixed(1)} days
            </p>
          </Card>
          {analytics.kpis.completion_before_start_rate != null && (
            <Card className="flex-1 p-4">
              <p className="text-sm text-zinc-400">Completed before start date</p>
              <p className="text-lg font-semibold text-zinc-100 mt-1">
                {analytics.kpis.completion_before_start_rate.toFixed(0)}%
              </p>
            </Card>
          )}
        </div>
      )}

      {/* Bottlenecks */}
      {analytics && analytics.bottlenecks.length > 0 && (
        <div className="mt-4">
          <h2 className="text-sm font-medium text-zinc-300 mb-2">Bottlenecks</h2>
          <Card className="p-0 divide-y divide-zinc-800">
            {analytics.bottlenecks.map((b) => (
              <div key={b.task_title} className="flex items-center justify-between px-5 py-3">
                <p className="text-sm text-zinc-200">{b.task_title}</p>
                <Badge variant="warning">
                  {b.overdue_count} overdue · {b.avg_days_overdue.toFixed(0)}d avg
                </Badge>
              </div>
            ))}
          </Card>
        </div>
      )}

      {/* Create form */}
      {showForm && (
        <Card className="mt-6">
          <form onSubmit={handleCreate} className="grid gap-4 sm:grid-cols-2">
            <Input
              id="title"
              label="Task title"
              required
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="e.g. Complete I-9 Form"
            />
            <Input
              id="description"
              label="Description"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="Optional details"
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
            <Input
              id="due_days"
              label="Due (days after start)"
              type="number"
              required
              value={form.due_days}
              onChange={(e) => setForm({ ...form, due_days: e.target.value })}
            />
            <div className="flex items-center gap-2 sm:col-span-2">
              <input
                id="is_employee"
                type="checkbox"
                checked={form.is_employee_task}
                onChange={(e) => setForm({ ...form, is_employee_task: e.target.checked })}
                className="rounded border-zinc-700 bg-zinc-900 text-emerald-600 focus:ring-emerald-500"
              />
              <label htmlFor="is_employee" className="text-sm text-zinc-300">
                Employee is responsible (vs. HR/admin)
              </label>
            </div>
            <div className="sm:col-span-2">
              <Button type="submit" disabled={saving}>
                {saving ? 'Creating...' : 'Create Task'}
              </Button>
            </div>
          </form>
        </Card>
      )}

      {/* Task templates by category */}
      <div className="mt-6 space-y-6">
        {Object.entries(grouped).map(([cat, items]) => (
          <div key={cat}>
            <h2 className="text-sm font-medium text-zinc-300 mb-2">{categoryLabel[cat]}</h2>
            <Card className="p-0 divide-y divide-zinc-800">
              {items.map((t) => (
                <div key={t.id} className="flex items-center gap-4 px-5 py-3">
                  <div className="flex-1 min-w-0">
                    <p className={`text-sm font-medium ${t.is_active ? 'text-zinc-100' : 'text-zinc-500 line-through'}`}>
                      {t.title}
                    </p>
                    {t.description && (
                      <p className="text-xs text-zinc-500 truncate">{t.description}</p>
                    )}
                  </div>
                  <Badge variant={t.is_employee_task ? 'success' : 'neutral'}>
                    {t.is_employee_task ? 'Employee' : 'HR'}
                  </Badge>
                  <span className="text-xs text-zinc-500 w-16 text-right">
                    {t.due_days}d
                  </span>
                  <div className="flex gap-1">
                    <Button size="sm" variant="ghost" onClick={() => toggleActive(t)}>
                      {t.is_active ? 'Disable' : 'Enable'}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => deleteTemplate(t.id)}>
                      Delete
                    </Button>
                  </div>
                </div>
              ))}
            </Card>
          </div>
        ))}
      </div>
    </div>
  )
}
