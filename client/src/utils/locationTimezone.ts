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

/** Every US civil time zone a store can sit in, for a manual choice. Shared by
 *  the compliance location form and the scheduling store forms so a store gets
 *  the same list whichever screen creates it. */
export const TIMEZONE_OPTIONS = [
  { value: '', label: 'Select a time zone' },
  { value: 'America/New_York', label: 'US Eastern (New York)' },
  { value: 'America/Detroit', label: 'US Eastern (Detroit)' },
  { value: 'America/Indiana/Indianapolis', label: 'US Eastern (Indianapolis)' },
  { value: 'America/Indiana/Marengo', label: 'US Eastern (Indiana — Marengo)' },
  { value: 'America/Indiana/Petersburg', label: 'US Eastern (Indiana — Petersburg)' },
  { value: 'America/Indiana/Vevay', label: 'US Eastern (Indiana — Vevay)' },
  { value: 'America/Indiana/Vincennes', label: 'US Eastern (Indiana — Vincennes)' },
  { value: 'America/Indiana/Winamac', label: 'US Eastern (Indiana — Winamac)' },
  { value: 'America/Kentucky/Louisville', label: 'US Eastern (Louisville)' },
  { value: 'America/Kentucky/Monticello', label: 'US Eastern (Kentucky — Monticello)' },
  { value: 'America/Chicago', label: 'US Central (Chicago)' },
  { value: 'America/Indiana/Knox', label: 'US Central (Indiana)' },
  { value: 'America/Indiana/Tell_City', label: 'US Central (Indiana — Tell City)' },
  { value: 'America/Menominee', label: 'US Central (Michigan)' },
  { value: 'America/North_Dakota/Center', label: 'US Central (North Dakota)' },
  { value: 'America/North_Dakota/New_Salem', label: 'US Central (North Dakota — New Salem)' },
  { value: 'America/North_Dakota/Beulah', label: 'US Central (North Dakota — Beulah)' },
  { value: 'America/Denver', label: 'US Mountain (Denver)' },
  { value: 'America/Boise', label: 'US Mountain (Boise)' },
  { value: 'America/Phoenix', label: 'US Mountain, no DST (Phoenix)' },
  { value: 'America/Los_Angeles', label: 'US Pacific (Los Angeles)' },
  { value: 'America/Anchorage', label: 'US Alaska (Anchorage)' },
  { value: 'America/Adak', label: 'US Hawaii-Aleutian (Adak)' },
  { value: 'Pacific/Honolulu', label: 'Hawaii (Honolulu)' },
  { value: 'America/Puerto_Rico', label: 'Atlantic (Puerto Rico)' },
  { value: 'America/St_Thomas', label: 'Atlantic (U.S. Virgin Islands)' },
  { value: 'Pacific/Guam', label: 'Chamorro (Guam)' },
  { value: 'Pacific/Saipan', label: 'Chamorro (Northern Mariana Islands)' },
  { value: 'Pacific/Pago_Pago', label: 'Samoa (Pago Pago)' },
]
