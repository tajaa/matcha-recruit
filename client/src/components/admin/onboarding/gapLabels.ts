export function humanizeCategory(slug: string): string {
  return slug
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

export function jurisdictionLabel(m: { city?: string | null; county?: string | null; state?: string | null }): string {
  const parts = [m.city, m.county, m.state].filter(Boolean)
  return parts.length ? parts.join(', ') : 'Federal'
}
