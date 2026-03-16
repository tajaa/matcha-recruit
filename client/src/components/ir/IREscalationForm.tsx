import { useState } from 'react'
import { api } from '../../api/client'
import { Button, Card, Input, Select } from '../ui'
import type { IRIncident } from '../../types/ir'
import { IR_TYPE_TO_ER_CATEGORY } from '../../types/ir'

const ER_CATEGORY_OPTIONS = [
  { value: 'harassment', label: 'Harassment' },
  { value: 'discrimination', label: 'Discrimination' },
  { value: 'safety', label: 'Safety' },
  { value: 'retaliation', label: 'Retaliation' },
  { value: 'policy_violation', label: 'Policy Violation' },
  { value: 'misconduct', label: 'Misconduct' },
  { value: 'wage_hour', label: 'Wage & Hour' },
  { value: 'other', label: 'Other' },
]

type Props = {
  incidentId: string
  incident: IRIncident
  onEscalated: (erCaseId: string) => void
}

export function IREscalationForm({ incidentId, incident, onEscalated }: Props) {
  const [show, setShow] = useState(false)
  const [form, setForm] = useState({
    title: `ER Escalation: ${incident.title}`,
    description: incident.description || '',
    category: IR_TYPE_TO_ER_CATEGORY[incident.incident_type] || 'other',
  })
  const [escalating, setEscalating] = useState(false)

  if (incident.er_case_id) {
    return (
      <a href={`/app/er-copilot/${incident.er_case_id}`}>
        <Button variant="ghost" size="sm" className="w-full">View ER Case</Button>
      </a>
    )
  }

  if (!show) {
    return (
      <Button variant="secondary" size="sm" className="w-full" onClick={() => {
        setForm({
          title: `ER Escalation: ${incident.title}`,
          description: incident.description || '',
          category: IR_TYPE_TO_ER_CATEGORY[incident.incident_type] || 'other',
        })
        setShow(true)
      }}>
        Escalate to ER Case
      </Button>
    )
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setEscalating(true)
    try {
      const res = await api.post<{ id: string }>('/er/cases', {
        title: form.title,
        description: form.description || null,
        category: form.category,
      })
      await api.put(`/ir/incidents/${incidentId}`, { er_case_id: res.id })
      onEscalated(res.id)
    } finally { setEscalating(false) }
  }

  return (
    <Card className="p-4">
      <form onSubmit={handleSubmit} className="space-y-3">
        <p className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Create ER Case</p>
        <Input label="Title" required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        <textarea
          className="w-full bg-zinc-900 border border-zinc-800 rounded-lg text-sm text-zinc-200 px-3 py-2 min-h-[60px] focus:outline-none focus:border-zinc-600"
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
          placeholder="Description..."
        />
        <Select label="Category" options={ER_CATEGORY_OPTIONS} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />
        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" type="button" onClick={() => setShow(false)}>Cancel</Button>
          <Button size="sm" type="submit" disabled={escalating}>{escalating ? 'Creating...' : 'Create ER Case'}</Button>
        </div>
      </form>
    </Card>
  )
}
