import { useState } from 'react'
import { BarChart2, AlertTriangle, Scale, ShieldCheck, BadgeCheck } from 'lucide-react'
import { Card, MetricStrip, PillTabs, Badge } from '../../../components/ui'
import { RegisterSpinner } from '../../../components/register/registerKit'
import { useAsync } from '../../../hooks/useAsync'
import {
  fetchOverview, fetchIncidentCorrelation, fetchFairWorkweek, fetchPretextShield,
  fetchQualifiedCoverage,
} from '../../../api/employees/scheduleIntelligence'
import type {
  IncidentCorrelation, FairWorkweek, PretextShield, QualifiedCoverage,
} from '../../../types/scheduleIntelligence'

type Tab = 'incidents' | 'fair_workweek' | 'pretext' | 'coverage'

const TABS: { value: Tab; label: string }[] = [
  { value: 'incidents', label: 'Incident Correlation' },
  { value: 'fair_workweek', label: 'Fair Workweek' },
  { value: 'pretext', label: 'Pretext Shield' },
  { value: 'coverage', label: 'Qualified Coverage' },
]

function money(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—'
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function Stat({ label, value, tone = 'text-zinc-200' }: { label: string; value: number | string; tone?: string }) {
  return (
    <div className="bg-zinc-900 px-4 py-4">
      <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">{label}</div>
      <div className={`text-2xl font-light font-mono mt-1.5 ${tone}`}>{value}</div>
    </div>
  )
}

function Disclaimer({ text }: { text: string }) {
  return (
    <p className="text-[11px] text-zinc-600 flex items-start gap-1.5 leading-relaxed">
      <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" /> {text}
    </p>
  )
}

export default function ScheduleIntelligence() {
  const [tab, setTab] = useState<Tab>('incidents')
  const { data: overview, loading: overviewLoading } = useAsync(() => fetchOverview(), [])

  if (overviewLoading) return <RegisterSpinner />

  if (overview && overview.available === false) {
    return (
      <Card className="p-6">
        <h1 className="text-lg font-semibold text-zinc-100 mb-2">Schedule Intelligence</h1>
        <p className="text-sm text-zinc-400 max-w-xl">
          Turn on Employee Scheduling to unlock these insights — Schedule Intelligence reads its
          shift and staffing data.
        </p>
      </Card>
    )
  }

  const m = overview?.modules

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight flex items-center gap-2">
          <BarChart2 className="h-5 w-5 text-zinc-400" /> Schedule Intelligence
        </h1>
        <p className="text-sm text-zinc-500 mt-1 max-w-2xl">
          Insights no other scheduling tool can show — because they cross your schedule with your
          own incident, discipline, credential, and training records.
        </p>
      </div>

      {m && (
        <MetricStrip cols="grid-cols-2 md:grid-cols-4">
          <Stat
            label="Understaffed incident rate"
            value={m.incidents.suppressed ? 'n/a' : (m.incidents.by_staffing?.understaffed.incident_rate ?? '—')}
            tone={m.incidents.suppressed ? 'text-zinc-600' : 'text-amber-400'}
          />
          <Stat
            label="Fair Workweek exposure"
            value={money(m.fair_workweek.total_exposure_estimate)}
            tone={m.fair_workweek.total_exposure_estimate ? 'text-red-400' : 'text-zinc-200'}
          />
          <Stat
            label="Pretext-flagged records"
            value={m.pretext.flagged_count}
            tone={m.pretext.flagged_count ? 'text-amber-400' : 'text-zinc-200'}
          />
          <Stat
            label="Shifts with coverage gaps"
            value={m.coverage.shifts_with_lapses}
            tone={m.coverage.shifts_with_lapses ? 'text-amber-400' : 'text-zinc-200'}
          />
        </MetricStrip>
      )}

      <PillTabs options={TABS} value={tab} onChange={setTab} />

      {tab === 'incidents' && <IncidentsPanel />}
      {tab === 'fair_workweek' && <FairWorkweekPanel />}
      {tab === 'pretext' && <PretextPanel />}
      {tab === 'coverage' && <CoveragePanel />}

      {overview && <Disclaimer text={overview.disclaimer} />}
    </div>
  )
}

function IncidentsPanel() {
  const { data, loading } = useAsync(() => fetchIncidentCorrelation(180), [])
  if (loading) return <RegisterSpinner />
  if (!data || data.available === false) return null
  const d = data as IncidentCorrelation

  return (
    <Card className="p-5 space-y-4">
      <h3 className="text-sm font-medium text-zinc-200 tracking-wide">
        Do incidents cluster on understaffed shifts?
      </h3>
      {d.suppressed ? (
        <p className="text-sm text-zinc-500">
          {d.suppressed_reason} — {d.n_incidents} incident(s) across {d.n_shifts} shift(s) in the
          last {d.days} days.
        </p>
      ) : (
        <div className="grid grid-cols-2 gap-4 max-w-lg">
          <div className="bg-zinc-900 rounded-lg p-4">
            <div className="text-[10px] text-zinc-600 uppercase tracking-widest font-bold">Understaffed</div>
            <div className="text-xl font-mono text-amber-400 mt-1">
              {d.by_staffing?.understaffed.incident_rate ?? '—'}
            </div>
            <div className="text-xs text-zinc-500 mt-1">
              {d.by_staffing?.understaffed.incidents} incidents / {d.by_staffing?.understaffed.shifts} shifts
            </div>
          </div>
          <div className="bg-zinc-900 rounded-lg p-4">
            <div className="text-[10px] text-zinc-600 uppercase tracking-widest font-bold">Adequately staffed</div>
            <div className="text-xl font-mono text-zinc-200 mt-1">
              {d.by_staffing?.adequate.incident_rate ?? '—'}
            </div>
            <div className="text-xs text-zinc-500 mt-1">
              {d.by_staffing?.adequate.incidents} incidents / {d.by_staffing?.adequate.shifts} shifts
            </div>
          </div>
        </div>
      )}

      {d.fatigue_flags.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-zinc-400 uppercase tracking-widest mb-2">Fatigue flags</h4>
          <div className="space-y-1">
            {d.fatigue_flags.map((f) => (
              <div key={f.incident_id + f.employee_id} className="text-xs text-zinc-400 flex items-center gap-2">
                <Badge variant="warning">
                  {f.short_rest ? `${f.rest_gap_hours}h rest` : `${f.consecutive_scheduled_days}-day streak`}
                </Badge>
                incident on a shift with a fatigue signal
              </div>
            ))}
          </div>
        </div>
      )}

      {Object.keys(d.by_location).length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-zinc-400 uppercase tracking-widest mb-2">By location</h4>
          <div className="space-y-1 text-xs text-zinc-400">
            {Object.entries(d.by_location).map(([id, loc]) => (
              <div key={id} className="flex justify-between max-w-md">
                <span>{loc.location_name}</span>
                <span className="font-mono">{loc.incidents} incidents / {loc.shifts} shifts</span>
              </div>
            ))}
          </div>
        </div>
      )}
      {d.unmatched_count > 0 && (
        <p className="text-xs text-zinc-600">{d.unmatched_count} incident(s) could not be matched to a shift.</p>
      )}
    </Card>
  )
}

function FairWorkweekPanel() {
  const { data, loading } = useAsync(() => fetchFairWorkweek(90), [])
  if (loading) return <RegisterSpinner />
  if (!data || data.available === false) return null
  const d = data as FairWorkweek

  return (
    <Card className="p-5 space-y-4">
      <h3 className="text-sm font-medium text-zinc-200 tracking-wide flex items-center gap-2">
        <Scale className="h-4 w-4 text-zinc-500" /> Fair Workweek / predictive-scheduling exposure
      </h3>
      {d.locations.length === 0 && d.unmapped_locations.length === 0 && (
        <p className="text-sm text-zinc-500">No locations on file yet.</p>
      )}
      <div className="space-y-3">
        {d.locations.map((loc) => (
          <div key={loc.location_id} className="bg-zinc-900 rounded-lg p-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm text-zinc-200">{loc.name}</div>
                <div className="text-xs text-zinc-500 mt-0.5">{loc.ordinance.name} — {loc.ordinance.citation}</div>
              </div>
              <div className="text-right">
                <div className="text-lg font-mono text-red-400">{money(loc.exposure_estimate)}</div>
                {loc.applicability !== 'covered' && (
                  <Badge variant="warning">{loc.applicability === 'review_industry' ? 'verify industry' : 'unmapped'}</Badge>
                )}
              </div>
            </div>
            <div className="text-xs text-zinc-500 mt-2">
              {loc.event_count} change event(s) — {loc.costed_event_count} priced, {loc.uncostable_event_count} count-only
            </div>
          </div>
        ))}
        {d.unmapped_locations.map((loc) => (
          <div key={loc.location_id} className="bg-zinc-900/50 rounded-lg p-4 text-sm text-zinc-500">
            {loc.name} — no Fair Workweek ordinance is curated for this location's jurisdiction yet.
          </div>
        ))}
      </div>
    </Card>
  )
}

function PretextPanel() {
  const { data, loading } = useAsync(() => fetchPretextShield(6), [])
  if (loading) return <RegisterSpinner />
  if (!data || data.available === false) return null
  const d = data as PretextShield

  return (
    <Card className="p-5 space-y-4">
      <h3 className="text-sm font-medium text-zinc-200 tracking-wide flex items-center gap-2">
        <ShieldCheck className="h-4 w-4 text-zinc-500" /> Discipline pretext shield
      </h3>
      <p className="text-xs text-zinc-500">{d.data_note}</p>
      {d.flagged.length === 0 ? (
        <p className="text-sm text-zinc-500">
          No flagged records in the last {d.months} months ({d.records_reviewed} attendance record(s) reviewed).
        </p>
      ) : (
        <div className="space-y-2">
          {d.flagged.map((f) => (
            <div key={f.discipline_record_id} className="bg-zinc-900 rounded-lg p-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-zinc-200">{f.infraction_type} — {f.issued_date}</span>
                <Badge variant="warning">{f.signals.length} signal(s)</Badge>
              </div>
              <p className="text-xs text-zinc-500 mt-2 leading-relaxed">{f.rationale}</p>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

function CoveragePanel() {
  const { data, loading } = useAsync(() => fetchQualifiedCoverage(14), [])
  if (loading) return <RegisterSpinner />
  if (!data || data.available === false) return null
  const d = data as QualifiedCoverage

  if (!d.sources.credentials && !d.sources.training) {
    return (
      <Card className="p-5">
        <p className="text-sm text-zinc-500">
          Turn on Credentialing or Training to see per-shift qualified-coverage gaps.
        </p>
      </Card>
    )
  }

  const gapShifts = d.shifts.filter((s) => s.qualified < s.assigned)

  return (
    <Card className="p-5 space-y-4">
      <h3 className="text-sm font-medium text-zinc-200 tracking-wide flex items-center gap-2">
        <BadgeCheck className="h-4 w-4 text-zinc-500" /> Qualified coverage — next {d.days} days
      </h3>
      {gapShifts.length === 0 ? (
        <p className="text-sm text-zinc-500">Every assigned employee is currently qualified for their upcoming shifts.</p>
      ) : (
        <div className="space-y-2">
          {gapShifts.map((s) => (
            <div key={s.shift_id} className="bg-zinc-900 rounded-lg p-4">
              <div className="flex items-center justify-between text-sm">
                <span className="text-zinc-200">{new Date(s.starts_at).toLocaleString()}</span>
                <span className="font-mono text-amber-400">{s.qualified}/{s.assigned} qualified (needs {s.required_staff})</span>
              </div>
              {Object.entries(s.lapses).map(([empId, items]) => (
                <div key={empId} className="text-xs text-zinc-500 mt-1">
                  {items.map((it) => `${it.item} — due/expired ${it.expired_or_due}`).join('; ')}
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}
