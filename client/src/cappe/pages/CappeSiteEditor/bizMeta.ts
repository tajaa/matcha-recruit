// ── business info + SEO, stored as meta_config keys ──────────────────────────
export type Social = { instagram: string; x: string; tiktok: string; youtube: string; facebook: string; linkedin: string; website: string }
export type DayHours = { day: number; open: string; close: string; closed: boolean }
export type BizMeta = {
  contact_email: string; contact_phone: string; contact_address: string; business_hours: string
  favicon_url: string; social: Social; seo: { title: string; description: string; og_image: string }
  hours: DayHours[]; lat: string; lng: string
}
export const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const defaultHours = (): DayHours[] =>
  DAY_LABELS.map((_, day) => ({ day, open: '09:00', close: '17:00', closed: day >= 5 }))
export const SOCIAL_FIELDS: { key: keyof Social; label: string; ph: string }[] = [
  { key: 'instagram', label: 'Instagram', ph: 'https://instagram.com/you' },
  { key: 'x', label: 'X', ph: 'https://x.com/you' },
  { key: 'tiktok', label: 'TikTok', ph: 'https://tiktok.com/@you' },
  { key: 'youtube', label: 'YouTube', ph: 'https://youtube.com/@you' },
  { key: 'facebook', label: 'Facebook', ph: 'https://facebook.com/you' },
  { key: 'linkedin', label: 'LinkedIn', ph: 'https://linkedin.com/in/you' },
  { key: 'website', label: 'Other website', ph: 'https://yoursite.com' },
]
const gstr = (o: Record<string, unknown> | undefined, k: string): string =>
  (o && typeof o[k] === 'string' ? (o[k] as string) : '')
export function bizFromMeta(m: Record<string, unknown> | undefined): BizMeta {
  const s = (m?.social ?? {}) as Record<string, unknown>
  const seo = (m?.seo ?? {}) as Record<string, unknown>
  const geo = (m?.geo ?? {}) as Record<string, unknown>
  const rawHours = Array.isArray(m?.hours) ? (m!.hours as DayHours[]) : []
  const hours = defaultHours().map((d) => {
    const found = rawHours.find((h) => Number(h?.day) === d.day)
    return found ? { day: d.day, open: found.open || '09:00', close: found.close || '17:00', closed: !!found.closed } : d
  })
  const numStr = (v: unknown) => (typeof v === 'number' ? String(v) : typeof v === 'string' ? v : '')
  return {
    contact_email: gstr(m, 'contact_email'), contact_phone: gstr(m, 'contact_phone'),
    contact_address: gstr(m, 'contact_address'), business_hours: gstr(m, 'business_hours'),
    favicon_url: gstr(m, 'favicon_url'),
    social: {
      instagram: gstr(s, 'instagram'), x: gstr(s, 'x'), tiktok: gstr(s, 'tiktok'), youtube: gstr(s, 'youtube'),
      facebook: gstr(s, 'facebook'), linkedin: gstr(s, 'linkedin'), website: gstr(s, 'website'),
    },
    seo: { title: gstr(seo, 'title'), description: gstr(seo, 'description'), og_image: gstr(seo, 'og_image') },
    hours, lat: numStr(geo.lat), lng: numStr(geo.lng),
  }
}
const orNull = (v: string) => v.trim() || null
export function bizToMeta(b: BizMeta): Record<string, unknown> {
  const social: Record<string, string> = {}
  SOCIAL_FIELDS.forEach(({ key }) => { if (b.social[key].trim()) social[key] = b.social[key].trim() })
  // Persist hours only if at least one day is open; geo only if both numbers parse.
  const anyOpen = b.hours.some((h) => !h.closed)
  const lat = parseFloat(b.lat), lng = parseFloat(b.lng)
  const geo = !Number.isNaN(lat) && !Number.isNaN(lng) ? { lat, lng } : null
  return {
    contact_email: orNull(b.contact_email), contact_phone: orNull(b.contact_phone),
    contact_address: orNull(b.contact_address), business_hours: orNull(b.business_hours),
    favicon_url: orNull(b.favicon_url), social,
    seo: { title: orNull(b.seo.title), description: orNull(b.seo.description), og_image: orNull(b.seo.og_image) },
    hours: anyOpen ? b.hours.map((h) => ({ day: h.day, open: h.open, close: h.close, closed: h.closed })) : [],
    geo,
  }
}
