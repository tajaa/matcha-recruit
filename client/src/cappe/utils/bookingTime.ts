const UTC = 'UTC'

function validTimezone(timezone: string | null | undefined): string {
  if (!timezone) return UTC
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: timezone }).format()
    return timezone
  } catch {
    return UTC
  }
}

export function formatBookingDateTime(
  timestamp: string,
  timezone: string | null | undefined,
  locales?: string | string[],
): string {
  return new Intl.DateTimeFormat(locales, {
    timeZone: validTimezone(timezone),
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(timestamp))
}

export function formatBookingTime(
  timestamp: string,
  timezone: string | null | undefined,
  locales?: string | string[],
): string {
  return new Intl.DateTimeFormat(locales, {
    timeZone: validTimezone(timezone),
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(timestamp))
}

export function bookingDateKey(timestamp: string, timezone: string | null | undefined): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: validTimezone(timezone),
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date(timestamp))
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]))
  return `${values.year}-${values.month}-${values.day}`
}
