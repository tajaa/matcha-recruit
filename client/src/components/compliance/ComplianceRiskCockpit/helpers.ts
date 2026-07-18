export function money(v: number) {
  return `$${Math.round(v).toLocaleString()}`
}

export function ageLabel(iso?: string | null): string | null {
  if (!iso) return null
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000)
  if (days <= 0) return 'flagged today'
  return `open ${days} day${days === 1 ? '' : 's'}`
}

export function humanize(s?: string | null): string {
  if (!s) return ''
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}
