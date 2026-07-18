export const BASE = (import.meta.env.VITE_API_URL ?? '/api').replace(/\/$/, '')

export function fmtWhen(iso: string): string {
  const d = new Date(iso)
  const t = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  return d.toDateString() === new Date().toDateString() ? t
    : `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })} ${t}`
}
