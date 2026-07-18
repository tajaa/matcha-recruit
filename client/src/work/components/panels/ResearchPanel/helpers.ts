export function formatUrl(url: string): string {
  try { return new URL(url).hostname.replace('www.', '') } catch { return url }
}

export function formatKey(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

export function flattenValue(value: unknown): string {
  if (value == null) return '—'
  if (Array.isArray(value)) {
    if (value.length > 0 && typeof value[0] === 'object' && value[0] !== null) {
      return value.map((item) => {
        const obj = item as Record<string, unknown>
        const parts = Object.entries(obj).map(([k, v]) => {
          if (Array.isArray(v)) return `${formatKey(k)}: ${v.map(x => typeof x === 'object' && x !== null ? Object.values(x as Record<string, unknown>).join(' · ') : String(x)).join(', ')}`
          if (typeof v === 'object' && v !== null) return `${formatKey(k)}: ${Object.entries(v as Record<string, unknown>).map(([ck, cv]) => `${formatKey(ck)}: ${String(cv ?? '—')}`).join(', ')}`
          return `${formatKey(k)}: ${String(v ?? '—')}`
        })
        return parts.join(' | ')
      }).join('\n')
    }
    return value.map(v => String(v)).join(', ')
  }
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>).map(([k, v]) =>
      `${formatKey(k)}: ${String(v ?? '—')}`
    ).join('\n')
  }
  return String(value)
}
