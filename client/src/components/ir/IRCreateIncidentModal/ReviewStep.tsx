import { Pencil } from 'lucide-react'
import { Button } from '../../ui'
import { locationLabel, type IncidentForm, type LocationRow } from './shared'
import type { WizardFieldKey } from './steps'

type Props = {
  form: IncidentForm
  locations: LocationRow[] | null
  saving: boolean
  submitError: string | null
  onEditStep: (key: WizardFieldKey) => void
  onSubmit: (e: React.FormEvent) => void
}

function ReviewRow({ label, value, onEdit }: { label: string; value: string; onEdit: () => void }) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-lg border border-white/[0.06] bg-zinc-900/60 px-3.5 py-3">
      <div className="min-w-0">
        <div className="text-[11px] font-medium uppercase tracking-wide text-zinc-500">{label}</div>
        <div className={`mt-0.5 text-sm ${value ? 'text-zinc-100' : 'text-zinc-600 italic'} whitespace-pre-wrap break-words`}>
          {value || 'Not set'}
        </div>
      </div>
      <button type="button" onClick={onEdit} className="shrink-0 flex items-center gap-1 text-[11px] text-zinc-500 hover:text-emerald-400 transition-colors">
        <Pencil className="h-3 w-3" /> Edit
      </button>
    </div>
  )
}

export function ReviewStep({ form, locations, saving, submitError, onEditStep, onSubmit }: Props) {
  const selectedLocation = (locations || []).find((l) => l.id === form.location_id)
  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <p className="text-[13px] text-zinc-400">Review before submitting — everything here stays editable.</p>

      <ReviewRow label="What happened" value={form.description} onEdit={() => onEditStep('description')} />
      <ReviewRow label="When" value={form.date_text} onEdit={() => onEditStep('date_text')} />
      <ReviewRow
        label="Where"
        value={selectedLocation ? locationLabel(selectedLocation) : ''}
        onEdit={() => onEditStep('location_id')}
      />
      <ReviewRow label="Reported by" value={form.reported_by_name || 'Unknown'} onEdit={() => onEditStep('reported_by_name')} />
      <ReviewRow
        label="Witnesses / others involved"
        value={form.involved.join(', ')}
        onEdit={() => onEditStep('involved')}
      />

      {submitError && <p className="text-sm text-red-400">{submitError}</p>}
      <div className="flex justify-end gap-2 border-t border-white/[0.06] pt-4">
        <Button type="submit" disabled={saving || !form.location_id || !form.date_text.trim() || !form.description.trim()}>
          {saving ? 'Submitting…' : 'Submit report'}
        </Button>
      </div>
    </form>
  )
}
