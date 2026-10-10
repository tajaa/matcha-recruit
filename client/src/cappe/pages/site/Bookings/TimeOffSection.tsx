import { useEffect, useState } from 'react'
import { CalendarOff, Loader2, Trash2 } from 'lucide-react'
import { cappeApi } from '../../../api'
import type { CappeLocation, CappeStaff, CappeTimeOff } from '../../../types'
import { formatBookingDateTime } from '../../../utils/bookingTime'
import { inputCls } from './constants'

// Closed periods: holidays, a staff member's day off, a location closed for
// a refit. Customers can't book into one and the widget doesn't offer it.
// Bookings already inside one are left alone. Times are the store's local time.
export function TimeOffSection({ siteId, staff, locations, timezone }: {
  siteId: string
  staff: CappeStaff[]
  locations: CappeLocation[]
  timezone: string
}) {
  const [rows, setRows] = useState<CappeTimeOff[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [who, setWho] = useState('')
  const [where, setWhere] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const active = locations.filter((l) => l.active)

  useEffect(() => {
    cappeApi.get<CappeTimeOff[]>(`/sites/${siteId}/time-off`)
      .then((r) => { setRows(r); setLoadError(null) })
      .catch((e) => setLoadError(e instanceof Error ? e.message : 'Could not load time off'))
  }, [siteId, attempt])

  async function add(e: React.FormEvent) {
    e.preventDefault()
    if (!from || !to) { setError('Choose when it starts and ends'); return }
    if (to <= from) { setError('The end must be after the start'); return }
    setSaving(true); setError(null)
    try {
      const row = await cappeApi.post<CappeTimeOff>(`/sites/${siteId}/time-off`, {
        starts_at: from, ends_at: to, staff_id: who || null, location_id: where || null, reason: reason.trim() || null,
      })
      setRows((rs) => [...(rs ?? []), row].sort((a, b) => a.starts_at.localeCompare(b.starts_at)))
      setFrom(''); setTo(''); setReason('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add it')
    } finally {
      setSaving(false)
    }
  }

  async function remove(t: CappeTimeOff) {
    if (!window.confirm('Remove this time off? Customers can book these times again.')) return
    setError(null)
    try {
      await cappeApi.delete(`/sites/${siteId}/time-off/${t.id}`)
      setRows((rs) => (rs ?? []).filter((x) => x.id !== t.id))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not remove it')
    }
  }

  return (
    <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-5 shadow-sm">
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-zinc-100"><CalendarOff className="h-4 w-4" /> Time off</h2>
      {loadError ? (
        <div role="alert" className="flex flex-wrap items-center gap-3 text-sm text-red-300">
          Couldn’t load time off. {loadError}
          <button onClick={() => setAttempt((n) => n + 1)} className="rounded-lg border border-red-500/40 px-2.5 py-1 text-xs font-medium hover:bg-red-500/10">Try again</button>
        </div>
      ) : rows === null ? (
        <Loader2 className="h-4 w-4 animate-spin text-zinc-400" />
      ) : rows.length === 0 ? (
        <p className="text-sm text-zinc-400">No time off coming up.</p>
      ) : (
        <ul className="divide-y divide-zinc-800">
          {rows.map((t) => (
            <li key={t.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-sm">
              <span className="min-w-0 flex-1 text-zinc-200">
                {formatBookingDateTime(t.starts_at, timezone)} – {formatBookingDateTime(t.ends_at, timezone)}
                <span className="block text-xs text-zinc-400">
                  {t.staff_name ?? 'Everyone'}{t.location_name ? ` · ${t.location_name}` : ''}{t.reason ? ` · ${t.reason}` : ''}
                </span>
              </span>
              <button onClick={() => remove(t)} aria-label="Remove time off" className="rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-red-300">
                <Trash2 className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={add} aria-label="Add time off" className="mt-3 grid gap-2 sm:grid-cols-2">
        <label className="text-xs text-zinc-400">Who
          <select value={who} onChange={(e) => setWho(e.target.value)} className={`mt-1 w-full ${inputCls}`}>
            <option value="">Everyone</option>
            {staff.filter((s) => s.active).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </label>
        {active.length > 0 ? (
          <label className="text-xs text-zinc-400">Where
            <select value={where} onChange={(e) => setWhere(e.target.value)} className={`mt-1 w-full ${inputCls}`}>
              <option value="">All locations</option>
              {active.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
          </label>
        ) : <div />}
        <label className="text-xs text-zinc-400">From
          <input type="datetime-local" value={from} onChange={(e) => setFrom(e.target.value)} className={`mt-1 w-full ${inputCls}`} />
        </label>
        <label className="text-xs text-zinc-400">To
          <input type="datetime-local" value={to} onChange={(e) => setTo(e.target.value)} className={`mt-1 w-full ${inputCls}`} />
        </label>
        <label className="text-xs text-zinc-400 sm:col-span-2">Reason (optional, for you)
          <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={200} placeholder="e.g. Holiday" className={`mt-1 w-full ${inputCls}`} />
        </label>
        {error && <p role="alert" className="text-xs text-red-400 sm:col-span-2">{error}</p>}
        <div className="sm:col-span-2">
          <button type="submit" disabled={saving} className="flex items-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-1.5 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60">
            {saving && <Loader2 className="h-4 w-4 animate-spin" />} Add time off
          </button>
        </div>
      </form>
    </section>
  )
}
