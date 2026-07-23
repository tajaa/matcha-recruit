import { useState } from 'react'
import { Scale } from 'lucide-react'
import { Modal, Select, Badge } from '../ui'
import { useAsync } from '../../hooks/useAsync'
import { fetchLocations } from '../../api/compliance/compliance/locations'
import { fetchLocationCompliance } from '../../api/employees/employeeSchedule'

const RULE_LABELS: Record<string, { label: string; unit: string }> = {
  meal_break_after_hours: { label: 'Meal break required after', unit: 'h shift' },
  meal_break_minutes: { label: 'Meal break duration', unit: 'min' },
  second_meal_after_hours: { label: 'Second meal break after', unit: 'h shift' },
  daily_ot_hours: { label: 'Daily overtime after', unit: 'h' },
  daily_doubletime_hours: { label: 'Daily double-time after', unit: 'h' },
  weekly_ot_hours: { label: 'Weekly overtime after', unit: 'h' },
  min_rest_between_shifts_hours: { label: 'Minimum rest between shifts', unit: 'h' },
  minor_u16_day_hours: { label: 'Under-16 daily cap', unit: 'h' },
  minor_u16_week_hours: { label: 'Under-16 weekly cap', unit: 'h' },
  minor_16_17_day_hours: { label: '16-17yo daily cap', unit: 'h' },
  minor_16_17_week_hours: { label: '16-17yo weekly cap', unit: 'h' },
}

const SOURCE_LABEL: Record<string, string> = {
  curated: 'Hand-curated',
  catalog_extraction: 'Catalog-extracted',
  unmapped: 'Not yet researched',
}

function RuleRow({ ruleKey, value }: { ruleKey: string; value: unknown }) {
  const meta = RULE_LABELS[ruleKey]
  if (!meta) return null
  const display = value === 'no_cap' ? 'no limit under law' : `${value}${meta.unit}`
  return (
    <div className="flex items-center justify-between text-sm py-1 border-b border-zinc-900 last:border-0">
      <span className="text-zinc-400">{meta.label}</span>
      <span className="text-zinc-100 font-mono">{display}</span>
    </div>
  )
}

function PanelBody({ locationId }: { locationId: string }) {
  const { data, loading } = useAsync(() => fetchLocationCompliance(locationId), [locationId])

  if (loading) return <p className="text-sm text-zinc-500">Loading…</p>
  if (!data) return <p className="text-sm text-zinc-500">Could not load scheduling law for this location.</p>

  const ruleEntries = Object.entries(data.rules).filter(([k]) => k !== 'source' && k in RULE_LABELS)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-xs text-zinc-500">{data.state ?? 'No state on file'}</span>
        <Badge variant={data.rules.source === 'unmapped' ? 'warning' : 'neutral'}>
          {SOURCE_LABEL[data.rules.source] ?? data.rules.source}
        </Badge>
      </div>

      {ruleEntries.length === 0 ? (
        <p className="text-sm text-zinc-500">
          No scheduling-law thresholds are researched for this location's state yet — advisories will
          say so rather than assume it's clear.
        </p>
      ) : (
        <div>{ruleEntries.map(([k, v]) => <RuleRow key={k} ruleKey={k} value={v} />)}</div>
      )}

      {data.statutes.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-zinc-400 uppercase tracking-widest mb-1.5">Citations</h4>
          <div className="space-y-1">
            {data.statutes.map((s) => (
              <a
                key={s.requirement_id}
                href={s.source_url ?? undefined}
                target="_blank"
                rel="noreferrer"
                className={`block text-xs ${s.source_url ? 'text-zinc-400 hover:text-zinc-200' : 'text-zinc-500'}`}
              >
                {s.title}{s.statute_citation ? ` — ${s.statute_citation}` : ''}
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default function ScheduleLawPanel() {
  const [open, setOpen] = useState(false)
  const [locationId, setLocationId] = useState('')
  const { data: locations } = useAsync(() => fetchLocations(), [], [])

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1 text-sm text-zinc-300 hover:text-zinc-100 px-3 py-2 rounded-lg border border-zinc-700"
      >
        <Scale className="h-4 w-4" /> Scheduling law
      </button>
      <Modal open={open} onClose={() => setOpen(false)} title="Scheduling law by location" width="md">
        <div className="space-y-4">
          <Select
            options={(locations ?? []).map((l) => ({ value: l.id, label: l.name ?? `${l.city}, ${l.state}` }))}
            value={locationId}
            onChange={(e) => setLocationId(e.target.value)}
            placeholder="Choose a location…"
          />
          {locationId && <PanelBody locationId={locationId} />}
        </div>
      </Modal>
    </>
  )
}
