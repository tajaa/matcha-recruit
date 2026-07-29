import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Badge, Button, Card, Input, Select, Textarea, Toggle, useToast } from '../../../components/ui'
import { ArrowLeft, Loader2, Save, Plus, Trash2 } from 'lucide-react'
import { useDisciplinePolicies, useDisciplineTemplates, useDisciplineApprovers } from '../../../hooks/discipline/useDiscipline'
import {
  DISCIPLINE_TEMPLATE_PLACEHOLDERS,
  type DisciplinePolicy,
  type DisciplineSeverity,
  type DisciplineLevel,
  type DisciplineTemplate,
  type DisciplineTemplateUpsertInput,
} from '../../../api/discipline/discipline'
import { ApiError } from '../../../api/client'

const SEVERITIES: { value: DisciplineSeverity; label: string }[] = [
  { value: 'minor', label: 'Minor' },
  { value: 'moderate', label: 'Moderate' },
  { value: 'severe', label: 'Severe' },
  { value: 'immediate_written', label: 'Immediate Written' },
]

const LEVELS: { value: DisciplineLevel; label: string }[] = [
  { value: 'verbal_warning', label: 'Verbal Warning' },
  { value: 'written_warning', label: 'Written Warning' },
  { value: 'pip', label: 'PIP' },
  { value: 'final_warning', label: 'Final Warning' },
  { value: 'suspension', label: 'Suspension' },
]

const EMPTY_TEMPLATE_DRAFT: DisciplineTemplateUpsertInput = {
  name: '', infraction_type: null, discipline_type: null, body: '', is_default: false, is_active: true,
}

export default function DisciplineSettings() {
  const navigate = useNavigate()
  const { policies, loading, error, refetch, upsert } = useDisciplinePolicies()
  const [drafts, setDrafts] = useState<Record<string, DisciplinePolicy>>({})
  const [savingKey, setSavingKey] = useState<string | null>(null)

  function getDraft(p: DisciplinePolicy): DisciplinePolicy {
    return drafts[p.infraction_type] || p
  }

  function update(p: DisciplinePolicy, patch: Partial<DisciplinePolicy>) {
    setDrafts((prev) => ({ ...prev, [p.infraction_type]: { ...getDraft(p), ...patch } }))
  }

  async function save(p: DisciplinePolicy) {
    const d = getDraft(p)
    setSavingKey(p.infraction_type)
    try {
      await upsert(p.infraction_type, {
        label: d.label,
        default_severity: d.default_severity,
        lookback_months_minor: d.lookback_months_minor,
        lookback_months_moderate: d.lookback_months_moderate,
        lookback_months_severe: d.lookback_months_severe,
        auto_to_written: d.auto_to_written,
        notify_grandparent_manager: d.notify_grandparent_manager,
      })
      setDrafts((prev) => {
        const next = { ...prev }
        delete next[p.infraction_type]
        return next
      })
      await refetch()
    } finally {
      setSavingKey(null)
    }
  }

  return (
    <div className="space-y-6">
      <Button variant="ghost" onClick={() => navigate('/app/discipline')}>
        <ArrowLeft className="w-4 h-4" />
        <span className="ml-2">Back to performance action</span>
      </Button>

      <div>
        <h1 className="text-2xl font-semibold text-zinc-100">Performance action policy mapping</h1>
        <p className="text-sm text-zinc-500 mt-1">
          Per-company config that powers the escalation engine. Lookback values control how
          long an active warning remains in effect before auto-expiring.
        </p>
      </div>

      {error && <div className="text-sm text-red-400">{error}</div>}

      {loading ? (
        <div className="p-12 flex items-center justify-center">
          <Loader2 className="w-5 h-5 animate-spin text-zinc-400" />
        </div>
      ) : (
        <div className="space-y-3">
          {policies.map((p) => {
            const d = getDraft(p)
            const dirty = !!drafts[p.infraction_type]
            return (
              <Card key={p.infraction_type} className="p-5">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-zinc-100 font-medium">{d.label}</div>
                    <div className="text-xs text-zinc-500 mt-0.5">
                      <code>{p.infraction_type}</code>
                    </div>
                  </div>
                  <Button
                    onClick={() => save(p)}
                    disabled={!dirty || savingKey === p.infraction_type}
                  >
                    {savingKey === p.infraction_type
                      ? <Loader2 className="w-4 h-4 animate-spin" />
                      : <Save className="w-4 h-4" />}
                    <span className="ml-2">Save</span>
                  </Button>
                </div>

                <div className="grid md:grid-cols-3 gap-3 mt-4">
                  <Input
                    label="Label"
                    value={d.label}
                    onChange={(e) => update(p, { label: e.target.value })}
                  />
                  <Select
                    label="Default severity"
                    options={SEVERITIES}
                    value={d.default_severity}
                    onChange={(e) =>
                      update(p, { default_severity: e.target.value as DisciplineSeverity })
                    }
                  />
                  <Input
                    label="Lookback minor (months)"
                    type="number"
                    min={1}
                    max={120}
                    value={d.lookback_months_minor}
                    onChange={(e) =>
                      update(p, { lookback_months_minor: parseInt(e.target.value, 10) || 0 })
                    }
                  />
                  <Input
                    label="Lookback moderate (months)"
                    type="number"
                    min={1}
                    max={120}
                    value={d.lookback_months_moderate}
                    onChange={(e) =>
                      update(p, { lookback_months_moderate: parseInt(e.target.value, 10) || 0 })
                    }
                  />
                  <Input
                    label="Lookback severe (months)"
                    type="number"
                    min={1}
                    max={120}
                    value={d.lookback_months_severe}
                    onChange={(e) =>
                      update(p, { lookback_months_severe: parseInt(e.target.value, 10) || 0 })
                    }
                  />
                </div>

                <div className="flex items-center gap-6 mt-4 text-sm">
                  <label className="flex items-center gap-2 text-zinc-300">
                    <input
                      type="checkbox"
                      checked={d.auto_to_written}
                      onChange={(e) => update(p, { auto_to_written: e.target.checked })}
                    />
                    Auto-jump to written warning (skip ladder climb)
                  </label>
                  <label className="flex items-center gap-2 text-zinc-300">
                    <input
                      type="checkbox"
                      checked={d.notify_grandparent_manager}
                      onChange={(e) =>
                        update(p, { notify_grandparent_manager: e.target.checked })
                      }
                    />
                    Notify grandparent manager
                  </label>
                </div>
              </Card>
            )
          })}
        </div>
      )}

      <TemplatesSection />
      <ApproversSection />
    </div>
  )
}

function TemplatesSection() {
  const { templates, loading, error, create, update, remove } = useDisciplineTemplates()
  const { toast } = useToast()
  const [editingId, setEditingId] = useState<string | 'new' | null>(null)
  const [draft, setDraft] = useState<DisciplineTemplateUpsertInput>(EMPTY_TEMPLATE_DRAFT)
  const [busy, setBusy] = useState(false)

  function startEdit(t: DisciplineTemplate) {
    setEditingId(t.id)
    setDraft({
      name: t.name, infraction_type: t.infraction_type, discipline_type: t.discipline_type,
      body: t.body, is_default: t.is_default, is_active: t.is_active,
    })
  }

  function startNew() {
    setEditingId('new')
    setDraft(EMPTY_TEMPLATE_DRAFT)
  }

  async function saveDraft() {
    setBusy(true)
    try {
      if (editingId === 'new') {
        await create(draft)
      } else if (editingId) {
        await update(editingId, draft)
      }
      setEditingId(null)
      toast('Template saved.', 'success')
    } catch (e) {
      toast(e instanceof ApiError ? e.message : 'Failed to save template', 'error')
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete(t: DisciplineTemplate) {
    setBusy(true)
    try {
      await remove(t.id)
      toast('Template removed.', 'success')
    } catch (e) {
      toast(e instanceof ApiError ? e.message : 'Failed to remove template', 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-zinc-100">Letter templates</h2>
          <p className="text-sm text-zinc-500 mt-1">
            Resolved automatically: exact infraction + level match, then infraction-only, then
            the company default, else drafted from scratch. Unrecognized placeholders are left
            in the letter verbatim rather than silently blanked.
          </p>
        </div>
        {editingId === null && (
          <Button size="sm" onClick={startNew}>
            <Plus className="w-4 h-4" />
            <span className="ml-1.5">New template</span>
          </Button>
        )}
      </div>

      {error && <div className="text-sm text-red-400">{error}</div>}
      {loading ? (
        <div className="p-8 flex items-center justify-center">
          <Loader2 className="w-5 h-5 animate-spin text-zinc-400" />
        </div>
      ) : (
        <div className="space-y-3">
          {templates.filter((t) => t.is_active || editingId === t.id).map((t) => (
            <Card key={t.id} className="p-4">
              {editingId === t.id ? (
                <TemplateForm draft={draft} setDraft={setDraft} busy={busy} onSave={saveDraft} onCancel={() => setEditingId(null)} />
              ) : (
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-zinc-100 font-medium flex items-center gap-2">
                      {t.name}
                      {t.is_default && <Badge variant="success">Default</Badge>}
                    </div>
                    <div className="text-xs text-zinc-500 mt-0.5">
                      {t.infraction_type || 'any infraction'} · {t.discipline_type || 'any level'}
                    </div>
                  </div>
                  <div className="flex gap-2 shrink-0">
                    <Button size="sm" variant="ghost" onClick={() => startEdit(t)}>Edit</Button>
                    <Button size="sm" variant="ghost" onClick={() => handleDelete(t)} disabled={busy}>
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              )}
            </Card>
          ))}
          {editingId === 'new' && (
            <Card className="p-4">
              <TemplateForm draft={draft} setDraft={setDraft} busy={busy} onSave={saveDraft} onCancel={() => setEditingId(null)} />
            </Card>
          )}
        </div>
      )}
    </div>
  )
}

function TemplateForm({
  draft, setDraft, busy, onSave, onCancel,
}: {
  draft: DisciplineTemplateUpsertInput
  setDraft: (d: DisciplineTemplateUpsertInput) => void
  busy: boolean
  onSave: () => void
  onCancel: () => void
}) {
  return (
    <div className="space-y-3">
      <div className="grid md:grid-cols-3 gap-3">
        <Input
          label="Name"
          value={draft.name}
          onChange={(e) => setDraft({ ...draft, name: e.target.value })}
        />
        <Select
          label="Infraction type (optional)"
          options={[
            { value: '', label: 'Any infraction' },
            { value: 'attendance', label: 'Attendance' },
            { value: 'performance', label: 'Performance' },
            { value: 'safety', label: 'Safety' },
            { value: 'harassment', label: 'Harassment' },
            { value: 'policy_violation', label: 'Policy Violation' },
            { value: 'gross_misconduct', label: 'Gross Misconduct' },
          ]}
          value={draft.infraction_type || ''}
          onChange={(e) => setDraft({ ...draft, infraction_type: e.target.value || null })}
        />
        <Select
          label="Level (optional)"
          options={[{ value: '', label: 'Any level' }, ...LEVELS]}
          value={draft.discipline_type || ''}
          onChange={(e) => setDraft({ ...draft, discipline_type: (e.target.value || null) as DisciplineLevel | null })}
        />
      </div>
      <Textarea
        label="Body"
        value={draft.body}
        onChange={(e) => setDraft({ ...draft, body: e.target.value })}
        rows={8}
      />
      <p className="text-xs text-zinc-500">
        Placeholders: {DISCIPLINE_TEMPLATE_PLACEHOLDERS.map((p) => `{{${p}}}`).join(', ')}
      </p>
      <label className="flex items-center gap-2 text-sm text-zinc-300">
        <input
          type="checkbox"
          checked={!!draft.is_default}
          onChange={(e) => setDraft({ ...draft, is_default: e.target.checked })}
        />
        Company default (used when no infraction/level-specific template matches)
      </label>
      <div className="flex gap-2">
        <Button
          size="sm"
          onClick={onSave}
          disabled={busy || !draft.name.trim() || draft.body.trim().length < 20}
        >
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          <span className="ml-1.5">Save</span>
        </Button>
        <Button size="sm" variant="ghost" onClick={onCancel} disabled={busy}>Cancel</Button>
      </div>
    </div>
  )
}

function ApproversSection() {
  const { approvers, loading, error, setApprover } = useDisciplineApprovers()
  const { toast } = useToast()
  const anyDesignated = approvers.some((a) => a.is_hr_approver)

  async function toggle(userId: string, next: boolean) {
    try {
      await setApprover(userId, next)
    } catch (e) {
      toast(e instanceof ApiError ? e.message : 'Failed to update approver', 'error')
    }
  }

  return (
    <div className="space-y-3">
      <div>
        <h2 className="text-lg font-semibold text-zinc-100">HR approvers</h2>
        <p className="text-sm text-zinc-500 mt-1">
          {anyDesignated
            ? 'Discipline drafted from an incident routes to whoever is toggled on below.'
            : 'No approvers designated — every business admin below is asked when a draft needs approval.'}
        </p>
      </div>
      {error && <div className="text-sm text-red-400">{error}</div>}
      {loading ? (
        <div className="p-8 flex items-center justify-center">
          <Loader2 className="w-5 h-5 animate-spin text-zinc-400" />
        </div>
      ) : (
        <Card className="divide-y divide-zinc-800">
          {approvers.map((a) => (
            <div key={a.user_id} className="flex items-center justify-between gap-3 p-4">
              <div>
                <div className="text-zinc-100 text-sm">{a.name || a.email}</div>
                <div className="text-xs text-zinc-500">{a.email}</div>
              </div>
              <Toggle checked={a.is_hr_approver} onChange={(v) => toggle(a.user_id, v)} />
            </div>
          ))}
          {approvers.length === 0 && (
            <div className="p-4 text-sm text-zinc-500">No business admins found.</div>
          )}
        </Card>
      )}
    </div>
  )
}
