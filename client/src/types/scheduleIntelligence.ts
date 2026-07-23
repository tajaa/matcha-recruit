// Schedule Intelligence — analytics over the employee-schedule data.
// Mirrors server/app/matcha/routes/schedule_intelligence.py response shapes.

export type Unavailable = { available: false; reason: 'employee_schedule_required' }

export type StaffingBucket = {
  shifts: number
  incidents: number
  incident_rate: number | null
}

export type FatigueFlag = {
  incident_id: string
  shift_id: string
  employee_id: string
  rest_gap_hours: number | null
  consecutive_scheduled_days: number
  short_rest: boolean
  long_streak: boolean
}

export type IncidentCorrelation = {
  available: true
  days: number
  n_incidents: number
  n_shifts: number
  unmatched_count: number
  suppressed: boolean
  suppressed_reason: string | null
  by_staffing: { understaffed: StaffingBucket; adequate: StaffingBucket } | null
  by_window: { night: StaffingBucket; day: StaffingBucket } | null
  by_location: Record<string, { location_name: string; shifts: number; incidents: number }>
  fatigue_flags: FatigueFlag[]
  disclaimer: string
}

export type FwEvent = {
  action: string
  shift_id: string | null
  kind: string
  notice_hours: number | null
  notice_days: number | null
  costable: boolean
  estimate: number | null
  uncostable_reason: string | null
  created_at: string
}

export type FwLocation = {
  location_id: string
  name: string
  ordinance: { name: string; citation: string; authority_url: string }
  applicability: 'covered' | 'review_industry' | 'unmapped'
  event_count: number
  costed_event_count: number
  uncostable_event_count: number
  exposure_estimate: number | null
  events: FwEvent[]
}

export type FairWorkweek = {
  available: true
  days: number
  locations: FwLocation[]
  unmapped_locations: { location_id: string; name: string }[]
  skipped_no_location_events: number
  disclaimer: string
}

export type PretextMetrics = {
  employer_changes: number
  short_notice_changes: number
  weekly_hours_sigma: number | null
  uncostable_legacy: number
}

export type PretextFlag = {
  discipline_record_id: string
  employee_id: string
  infraction_type: string | null
  issued_date: string
  metrics: PretextMetrics
  signals: string[]
  rationale: string
}

export type PretextShield = {
  available: true
  months: number
  records_reviewed: number
  flagged: PretextFlag[]
  data_note: string
  disclaimer: string
}

export type CoverageLapse = { source: string; item: string; expired_or_due: string }

export type CoverageShift = {
  shift_id: string
  starts_at: string
  location_id: string | null
  required_staff: number
  assigned: number
  qualified: number
  lapsed_employee_ids: string[]
  lapses: Record<string, CoverageLapse[]>
}

export type QualifiedCoverage = {
  available: true
  days: number
  shifts: CoverageShift[]
  sources: { credentials: unknown[] | null; training: unknown[] | null }
  disclaimer: string
}

export type ScheduleIntelOverview = {
  available: true
  modules: {
    incidents: {
      suppressed: boolean
      n_incidents: number
      n_shifts: number
      by_staffing: { understaffed: StaffingBucket; adequate: StaffingBucket } | null
    }
    fair_workweek: {
      total_exposure_estimate: number | null
      location_count: number
      unmapped_location_count: number
    }
    pretext: { records_reviewed: number; flagged_count: number }
    coverage: {
      shifts_checked: number
      shifts_with_lapses: number
      sources: { credentials: unknown[] | null; training: unknown[] | null }
    }
  }
  disclaimer: string
}
