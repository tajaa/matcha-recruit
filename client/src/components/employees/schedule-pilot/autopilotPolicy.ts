import type { LocationScheduleProfile, LocationScheduleProfileUpdate } from '../../../types/employeeSchedule'

export type AutopilotPolicyDraft = {
  weatherSensitivity: 'none' | 'rain_hurts' | 'rain_helps'
  minFloorStaff: string
  targetLaborPct: string
  shiftMinHours: string
  shiftMaxHours: string
}

export const DEFAULT_MIN_SHIFT_HOURS = 4
export const DEFAULT_MAX_SHIFT_HOURS = 9

export function policyDraftFromProfile(profile: LocationScheduleProfile): AutopilotPolicyDraft {
  return {
    weatherSensitivity: profile.weather_sensitivity ?? 'none',
    minFloorStaff: String(profile.min_floor_staff ?? 1),
    targetLaborPct: profile.target_labor_pct == null ? '' : String(profile.target_labor_pct),
    shiftMinHours: profile.autopilot_shift_min_minutes == null ? '' : String(profile.autopilot_shift_min_minutes / 60),
    shiftMaxHours: profile.autopilot_shift_max_minutes == null ? '' : String(profile.autopilot_shift_max_minutes / 60),
  }
}

export function policyPayload(draft: AutopilotPolicyDraft): LocationScheduleProfileUpdate {
  const floor = Number(draft.minFloorStaff)
  if (!Number.isInteger(floor) || floor < 0 || floor > 20 || !draft.minFloorStaff.trim()) {
    throw new Error('Minimum floor staff must be a whole number from 0 to 20.')
  }
  const optional = (raw: string, label: string, min: number, max: number): number | null => {
    if (!raw.trim()) return null
    const value = Number(raw)
    if (!Number.isFinite(value) || value < min || value > max) {
      throw new Error(`${label} must be between ${min} and ${max}.`)
    }
    return value
  }
  const target = optional(draft.targetLaborPct, 'Target labor %', 1, 90)
  const minHours = optional(draft.shiftMinHours, 'Minimum shift hours', 2, 12)
  const maxHours = optional(draft.shiftMaxHours, 'Maximum shift hours', 2, 12)
  if ((minHours ?? DEFAULT_MIN_SHIFT_HOURS) > (maxHours ?? DEFAULT_MAX_SHIFT_HOURS)) {
    throw new Error('Minimum shift hours cannot exceed maximum shift hours (defaults: 4–9 hours).')
  }
  return {
    weather_sensitivity: draft.weatherSensitivity,
    min_floor_staff: floor,
    target_labor_pct: target,
    autopilot_shift_min_minutes: minHours == null ? null : Math.round(minHours * 60),
    autopilot_shift_max_minutes: maxHours == null ? null : Math.round(maxHours * 60),
  }
}
