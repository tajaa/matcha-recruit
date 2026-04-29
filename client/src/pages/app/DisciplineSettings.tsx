import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, Input, Select } from '../../components/ui'
import { ArrowLeft, Loader2, Save } from 'lucide-react'
import { useDisciplinePolicies } from '../../hooks/discipline/useDiscipline'
import type {
  DisciplinePolicy,
  DisciplineSeverity,
} from '../../api/discipline'

const SEVERITIES: { value: DisciplineSeverity; label: string }[] = [
  { value: 'minor', label: 'Minor' },
  { value: 'moderate', label: 'Moderate' },
  { value: 'severe', label: 'Severe' },
  { value: 'immediate_written', label: 'Immediate Written' },
]

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
    <div className="space-y-6 p-6">
      <Button variant="ghost" onClick={() => navigate('/app/discipline')}>
        <ArrowLeft className="w-4 h-4" />
        <span className="ml-2">Back to discipline</span>
      </Button>

      <div>
        <h1 className="text-2xl font-semibold text-zinc-100">Discipline policy mapping</h1>
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
    </div>
  )
}
