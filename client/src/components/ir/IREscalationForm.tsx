import { useState } from 'react'
import { api } from '../../api/client'
import { Button, Card, Input, Select, LABEL } from '../ui'
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
  const [error, setError] = useState('')
  // Set once the ER case POST succeeds — from then on the "Escalate" button
  // must never reappear, or a failed link-back lets the user create a SECOND
  // ER case for the same incident with the first orphaned.
  const [createdErCaseId, setCreatedErCaseId] = useState<string | null>(null)
  const [linking, setLinking] = useState(false)
  const [linkError, setLinkError] = useState('')

  if (incident.er_case_id) {
    return (
      <a href={`/app/er-copilot/${incident.er_case_id}`}>
        <Button variant="ghost" size="sm" className="w-full">View ER Case</Button>
      </a>
    )
  }

  // ER case exists (POST succeeded) but the link-back to this incident
  // hasn't landed yet. Never fall through to the "Escalate" button here —
  // that reappearing is exactly what let a failed link-back create a
  // duplicate ER case for the same incident.
  if (createdErCaseId) {
    return (
      <Card className="p-4 space-y-2">
        <p className="text-xs text-red-400">
          {linkError || 'Linking this incident to the ER case…'}
        </p>
        <div className="flex justify-end gap-2">
          <a href={`/app/er-copilot/${createdErCaseId}`}>
            <Button variant="ghost" size="sm">Open ER case anyway</Button>
          </a>
          <Button size="sm" disabled={linking} onClick={() => linkBack(createdErCaseId)}>
            {linking ? 'Retrying…' : 'Retry linking'}
          </Button>
        </div>
      </Card>
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

  async function linkBack(erCaseId: string) {
    setLinking(true)
    setLinkError('')
    try {
      await api.put(`/ir/incidents/${incidentId}`, { er_case_id: erCaseId })
      onEscalated(erCaseId)
    } catch (err) {
      // incident.er_case_id is still null server-side, so the "Escalate"
      // button would otherwise reappear next time this incident loads —
      // offer retry/skip instead of silently letting that happen.
      setLinkError(err instanceof Error ? err.message : 'Failed to link this incident to the ER case')
    } finally {
      setLinking(false)
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setEscalating(true)
    setError('')
    try {
      const res = await api.post<{ id: string }>('/er/cases', {
        title: form.title,
        description: form.description || null,
        category: form.category,
      })
      setCreatedErCaseId(res.id)
      await linkBack(res.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create ER case')
    } finally {
      setEscalating(false)
    }
  }

  return (
    <Card className="p-4">
      <form onSubmit={handleSubmit} className="space-y-3">
        <p className={LABEL}>Create ER Case</p>
        <Input label="Title" required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        <textarea
          className="w-full bg-zinc-900 border border-white/[0.08] rounded-lg text-sm text-zinc-200 px-3 py-2 min-h-[60px] focus:outline-none focus:border-emerald-500/50"
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
          placeholder="Description..."
        />
        <Select label="Category" options={ER_CATEGORY_OPTIONS} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />
        {error && <p className="text-xs text-red-400">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" type="button" onClick={() => setShow(false)}>Cancel</Button>
          <Button size="sm" type="submit" disabled={escalating}>{escalating ? 'Creating...' : 'Create ER Case'}</Button>
        </div>
      </form>
    </Card>
  )
}
