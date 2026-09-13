export type LocationTimezoneSource = 'auto' | 'manual'

// State-only mapping is limited to places with a single unambiguous civil
// timezone. Split-zone states and local exceptions deliberately fall back to
// manual selection rather than guessing.
const SINGLE_ZONE_US_TIMEZONES: Record<string, string> = {
  AL: 'America/Chicago', AR: 'America/Chicago', CA: 'America/Los_Angeles',
  CO: 'America/Denver', CT: 'America/New_York', DC: 'America/New_York',
  DE: 'America/New_York', GA: 'America/New_York', GU: 'Pacific/Guam',
  HI: 'Pacific/Honolulu', IA: 'America/Chicago', IL: 'America/Chicago',
  LA: 'America/Chicago', MA: 'America/New_York', MD: 'America/New_York',
  ME: 'America/New_York', MN: 'America/Chicago', MO: 'America/Chicago',
  MP: 'Pacific/Saipan', MS: 'America/Chicago', MT: 'America/Denver',
  NC: 'America/New_York', NH: 'America/New_York', NJ: 'America/New_York',
  NM: 'America/Denver', NY: 'America/New_York', OH: 'America/New_York',
  OK: 'America/Chicago', PA: 'America/New_York', PR: 'America/Puerto_Rico',
  RI: 'America/New_York', SC: 'America/New_York', UT: 'America/Denver',
  VA: 'America/New_York', VI: 'America/St_Thomas', VT: 'America/New_York',
  WA: 'America/Los_Angeles', WI: 'America/Chicago', WV: 'America/New_York',
  WY: 'America/Denver', AS: 'Pacific/Pago_Pago',
}

export function inferLocationTimezone(state: string): string | null {
  return SINGLE_ZONE_US_TIMEZONES[state.trim().toUpperCase()] ?? null
}
