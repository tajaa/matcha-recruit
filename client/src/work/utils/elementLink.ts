export function normalizeElementLink(raw: string): string | null {
  const candidate = /^https?:\/\//i.test(raw.trim()) ? raw.trim() : `https://${raw.trim()}`
  try {
    const url = new URL(candidate)
    return ['http:', 'https:'].includes(url.protocol) && url.hostname && !url.username && !url.password ? url.toString() : null
  } catch { return null }
}
