import { Link } from 'react-router-dom'
import { Button, Select } from '../../ui'
import { IRPersonMultiSelect } from '../IRPersonMultiSelect'
import { EmployeeMultiSelect } from '../../employees/EmployeeMultiSelect'
import { FIELD, LABEL, locationLabel, type IncidentForm, type LocationRow } from './shared'
import type { WizardStepConfig } from './steps'

type Props = {
  step: WizardStepConfig
  form: IncidentForm
  setForm: (updater: (f: IncidentForm) => IncidentForm) => void
  locations: LocationRow[] | null
  hasRoster: boolean
  stepIndex: number
  stepCount: number
  onBack: () => void
  onNext: () => void
  canGoNext: boolean
  isFirstStep: boolean
}

export function WizardStep({
  step, form, setForm, locations, hasRoster, stepIndex, stepCount, onBack, onNext, canGoNext, isFirstStep,
}: Props) {
  return (
    <div className="space-y-5">
      <div className="flex items-center gap-1.5">
        {Array.from({ length: stepCount }).map((_, i) => (
          <div
            key={i}
            className={`h-1 flex-1 rounded-full transition-colors ${i <= stepIndex ? 'bg-emerald-500/70' : 'bg-white/[0.08]'}`}
          />
        ))}
      </div>

      <div>
        <label className={LABEL}>
          {step.question}
          {step.required && <span className="text-red-400 ml-1">*</span>}
        </label>
        {step.key === 'description' && (
          <textarea
            autoFocus
            className={`${FIELD} min-h-[120px] resize-y`}
            value={form.description}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            placeholder="What happened? Include relevant details — Intelligent Theme Analysis will categorize from this."
          />
        )}
        {step.key === 'date_text' && (
          <input
            autoFocus
            className={FIELD}
            value={form.date_text}
            onChange={(e) => setForm((f) => ({ ...f, date_text: e.target.value }))}
            placeholder="e.g. yesterday around 3pm, May 1 at 9am"
          />
        )}
        {step.key === 'location_id' && (
          locations === null ? (
            <input className={`${FIELD} opacity-50`} value="Loading…" disabled />
          ) : locations.length === 0 ? (
            <div className="rounded-lg border border-white/[0.08] bg-zinc-900 px-3 py-2.5 text-sm text-zinc-300">
              No locations yet.{' '}
              <Link to="/app/locations" className="text-emerald-400 hover:text-emerald-300 underline">Add one</Link>{' '}
              before submitting an incident.
            </div>
          ) : (
            <Select
              options={[
                { value: '', label: 'Select location…' },
                ...locations.map((l) => ({ value: l.id, label: locationLabel(l) })),
              ]}
              value={form.location_id}
              onChange={(e) => setForm((f) => ({ ...f, location_id: e.target.value }))}
            />
          )
        )}
        {step.key === 'reported_by_name' && (
          <input
            autoFocus
            className={FIELD}
            value={form.reported_by_name}
            onChange={(e) => setForm((f) => ({ ...f, reported_by_name: e.target.value }))}
            placeholder="Who is reporting?"
          />
        )}
        {step.key === 'involved' && (
          <div className="space-y-4">
            {hasRoster && (
              <EmployeeMultiSelect
                label="Involved employees (roster)"
                value={form.involved_employee_ids}
                onChange={(involved_employee_ids) => setForm((f) => ({ ...f, involved_employee_ids }))}
                placeholder="Search employees…"
              />
            )}
            {/* These names persist to the witnesses column (role=witness in the
                per-person index). Label says "witnesses / others involved" so the
                form matches the role taxonomy shown on a person's history. */}
            <IRPersonMultiSelect
              label="Witnesses / others involved"
              value={form.involved}
              onChange={(involved) => setForm((f) => ({ ...f, involved }))}
              placeholder="Type a name, Enter to add"
            />
          </div>
        )}
      </div>

      <div className="flex items-center justify-between border-t border-white/[0.06] pt-4">
        <Button variant="ghost" type="button" onClick={onBack} disabled={isFirstStep}>Back</Button>
        <Button type="button" onClick={onNext} disabled={!canGoNext}>
          {step.required || form.involved.length > 0 ? 'Next' : 'Skip'}
        </Button>
      </div>
    </div>
  )
}
