import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, Plus, Trash2, Calendar, Save, Check, X, Lock, Clock, ShieldCheck } from 'lucide-react'
import { cappeApi } from '../../../api/cappeClient'
import { useCappeMe } from '../../../hooks/useCappeMe'
import SurfaceShell, { WEEKDAYS } from '../../../components/cappe/SurfaceShell'
import type {
  CappeBooking, CappeBookingType, CappeAvailabilitySlot,
  CappeRateRule, CappeRiderItem, CappePricingMode,
} from '../../../types/cappe'

const hhmm = (t: string) => t.slice(0, 5)
const money = (cents: number | null | undefined) =>
  cents == null ? '—' : `$${(cents / 100).toFixed(2)}`

const statusStyle: Record<string, string> = {
  pending: 'bg-amber-500/15 text-amber-400',
  confirmed: 'bg-emerald-500/15 text-emerald-400',
  declined: 'bg-red-500/15 text-red-400',
  cancelled: 'bg-zinc-800 text-zinc-500',
  completed: 'bg-sky-500/15 text-sky-400',
}

export default function Bookings() {
  const { siteId } = useParams<{ siteId: string }>()
  const { account } = useCappeMe()
  const [types, setTypes] = useState<CappeBookingType[]>([])
  const [slots, setSlots] = useState<CappeAvailabilitySlot[]>([])
  const [bookings, setBookings] = useState<CappeBooking[]>([])
  const [rules, setRules] = useState<CappeRateRule[]>([])
  const [rider, setRider] = useState<CappeRiderItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [typeForm, setTypeForm] = useState({
    name: '', duration_minutes: '30', pricing_mode: 'flat' as CappePricingMode,
    price: '', requires_approval: false,
  })
  const [savingAvail, setSavingAvail] = useState(false)
  const [savingRules, setSavingRules] = useState(false)
  const [savingRider, setSavingRider] = useState(false)

  const isCreator = account?.account_type === 'personal'
  const riderUnlocked = isCreator && account?.plan === 'pro'

  useEffect(() => {
    Promise.all([
      cappeApi.get<CappeBookingType[]>(`/sites/${siteId}/booking-types`),
      cappeApi.get<CappeAvailabilitySlot[]>(`/sites/${siteId}/availability`),
      cappeApi.get<CappeBooking[]>(`/sites/${siteId}/bookings`),
      cappeApi.get<CappeRateRule[]>(`/sites/${siteId}/rate-rules`).catch(() => []),
      cappeApi.get<CappeRiderItem[]>(`/sites/${siteId}/rider`).catch(() => []),
    ])
      .then(([t, a, b, r, rd]) => { setTypes(t); setSlots(a); setBookings(b); setRules(r); setRider(rd) })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setLoading(false))
  }, [siteId])

  async function addType(e: React.FormEvent) {
    e.preventDefault()
    if (!typeForm.name.trim()) return
    const created = await cappeApi.post<CappeBookingType>(`/sites/${siteId}/booking-types`, {
      name: typeForm.name.trim(),
      duration_minutes: parseInt(typeForm.duration_minutes, 10) || 30,
      pricing_mode: typeForm.pricing_mode,
      price_cents: Math.round((parseFloat(typeForm.price) || 0) * 100),
      requires_approval: typeForm.requires_approval,
    })
    setTypes((t) => [...t, created])
    setTypeForm({ name: '', duration_minutes: '30', pricing_mode: 'flat', price: '', requires_approval: false })
  }

  async function patchType(id: string, patch: Partial<CappeBookingType>) {
    const updated = await cappeApi.put<CappeBookingType>(`/sites/${siteId}/booking-types/${id}`, patch)
    setTypes((t) => t.map((x) => (x.id === id ? updated : x)))
  }

  async function removeType(id: string) {
    await cappeApi.delete(`/sites/${siteId}/booking-types/${id}`)
    setTypes((t) => t.filter((x) => x.id !== id))
  }

  function addSlot() {
    setSlots((s) => [...s, { weekday: 0, start_time: '09:00', end_time: '17:00', booking_type_id: null }])
  }
  function setSlot(i: number, patch: Partial<CappeAvailabilitySlot>) {
    setSlots((s) => s.map((x, idx) => (idx === i ? { ...x, ...patch } : x)))
  }

  async function saveAvailability() {
    setSavingAvail(true)
    setError(null)
    try {
      const payload = { slots: slots.map((s) => ({ ...s, start_time: hhmm(s.start_time), end_time: hhmm(s.end_time) })) }
      const saved = await cappeApi.put<CappeAvailabilitySlot[]>(`/sites/${siteId}/availability`, payload)
      setSlots(saved)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save availability')
    } finally {
      setSavingAvail(false)
    }
  }

  // --- Rate rules ---
  function addRule() {
    setRules((r) => [...r, {
      id: `tmp-${r.length}`, site_id: siteId!, booking_type_id: null, label: '',
      weekday: null, start_time: '20:00', end_time: '23:00', multiplier: 2, created_at: '',
    }])
  }
  function setRule(i: number, patch: Partial<CappeRateRule>) {
    setRules((r) => r.map((x, idx) => (idx === i ? { ...x, ...patch } : x)))
  }
  async function saveRules() {
    setSavingRules(true)
    setError(null)
    try {
      const payload = {
        rules: rules.map((r) => ({
          label: r.label || 'Rate', booking_type_id: r.booking_type_id, weekday: r.weekday,
          start_time: hhmm(r.start_time), end_time: hhmm(r.end_time), multiplier: r.multiplier,
        })),
      }
      const saved = await cappeApi.put<CappeRateRule[]>(`/sites/${siteId}/rate-rules`, payload)
      setRules(saved)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save rate rules')
    } finally {
      setSavingRules(false)
    }
  }

  // --- Rider ---
  function addRiderItem() {
    setRider((r) => [...r, {
      id: `tmp-${r.length}`, site_id: siteId!, label: '', detail: null,
      is_required: true, sort_order: r.length, created_at: '',
    }])
  }
  function setRiderItem(i: number, patch: Partial<CappeRiderItem>) {
    setRider((r) => r.map((x, idx) => (idx === i ? { ...x, ...patch } : x)))
  }
  async function saveRider() {
    setSavingRider(true)
    setError(null)
    try {
      const payload = {
        items: rider.map((r, i) => ({
          label: r.label || 'Requirement', detail: r.detail || null,
          is_required: r.is_required, sort_order: i,
        })),
      }
      const saved = await cappeApi.put<CappeRiderItem[]>(`/sites/${siteId}/rider`, payload)
      setRider(saved)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save rider')
    } finally {
      setSavingRider(false)
    }
  }

  // --- Booking actions ---
  async function acceptBooking(b: CappeBooking) {
    const updated = await cappeApi.post<CappeBooking>(`/sites/${siteId}/bookings/${b.id}/accept`)
    setBookings((list) => list.map((x) => (x.id === b.id ? updated : x)))
  }
  async function declineBooking(b: CappeBooking) {
    const reason = window.prompt('Reason for declining (optional, shown to the customer):') ?? undefined
    const updated = await cappeApi.post<CappeBooking>(`/sites/${siteId}/bookings/${b.id}/decline`, { reason })
    setBookings((list) => list.map((x) => (x.id === b.id ? updated : x)))
  }
  async function setBookingStatus(b: CappeBooking, status: string) {
    const updated = await cappeApi.patch<CappeBooking>(`/sites/${siteId}/bookings/${b.id}`, { status })
    setBookings((list) => list.map((x) => (x.id === b.id ? updated : x)))
  }

  const pending = bookings.filter((b) => b.status === 'pending' && b.requires_approval)
  const hasHourly = types.some((t) => t.pricing_mode === 'hourly')

  if (loading) {
    return <SurfaceShell title="Bookings"><div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div></SurfaceShell>
  }

  const inputCls = 'rounded-lg border border-zinc-700 bg-zinc-950 text-zinc-100 placeholder:text-zinc-500 px-3 py-2 text-sm outline-none focus:border-emerald-500'

  return (
    <SurfaceShell title="Bookings" subtitle="Appointment types, availability, pricing, and requests.">
      {error && <p className="mb-4 text-sm text-red-400">{error}</p>}

      {/* Requests needing approval — the creator's queue */}
      {pending.length > 0 && (
        <section className="mb-6 rounded-2xl border border-amber-500/30 bg-amber-500/[0.05] p-5">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-amber-200">
            <Clock className="h-4 w-4" /> {pending.length} request{pending.length === 1 ? '' : 's'} awaiting your approval
          </h2>
          <ul className="space-y-2">
            {pending.map((b) => (
              <li key={b.id} className="flex flex-wrap items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900 p-3 text-sm">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-zinc-100">{b.customer_name || b.customer_email || 'Customer'}</div>
                  <div className="text-xs text-zinc-400">
                    {new Date(b.starts_at).toLocaleString()} – {new Date(b.ends_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    {' · '}<span className="text-emerald-400">{money(b.quoted_price_cents)}</span>
                    {b.rider_acknowledged && <span className="ml-2 inline-flex items-center gap-1 text-zinc-500"><ShieldCheck className="h-3 w-3" /> agreed to rider</span>}
                  </div>
                  {b.note && <div className="mt-1 truncate text-xs text-zinc-500">“{b.note}”</div>}
                </div>
                <button onClick={() => acceptBooking(b)} className="flex items-center gap-1 rounded-lg bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-zinc-950 hover:bg-emerald-400"><Check className="h-3.5 w-3.5" /> Accept</button>
                <button onClick={() => declineBooking(b)} className="flex items-center gap-1 rounded-lg border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800"><X className="h-3.5 w-3.5" /> Decline</button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Booking types */}
      <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-5 shadow-sm">
        <h2 className="mb-3 text-sm font-semibold text-zinc-100">Appointment types</h2>
        <form onSubmit={addType} className="mb-4 grid gap-2 sm:grid-cols-2">
          <input value={typeForm.name} onChange={(e) => setTypeForm({ ...typeForm, name: e.target.value })} placeholder="e.g. Wedding shoot" className={inputCls} />
          <div className="flex gap-2">
            <input value={typeForm.duration_minutes} onChange={(e) => setTypeForm({ ...typeForm, duration_minutes: e.target.value })} type="number" min="1" placeholder="min" className={`w-24 ${inputCls}`} />
            <select value={typeForm.pricing_mode} onChange={(e) => setTypeForm({ ...typeForm, pricing_mode: e.target.value as CappePricingMode })} className={inputCls}>
              <option value="flat">Flat price</option>
              <option value="hourly">Per hour</option>
            </select>
            <input value={typeForm.price} onChange={(e) => setTypeForm({ ...typeForm, price: e.target.value })} type="number" min="0" step="0.01" placeholder={typeForm.pricing_mode === 'hourly' ? '$/hr' : '$'} className={`w-24 ${inputCls}`} />
          </div>
          <label className="flex items-center gap-2 text-sm text-zinc-300">
            <input type="checkbox" checked={typeForm.requires_approval} onChange={(e) => setTypeForm({ ...typeForm, requires_approval: e.target.checked })} className="h-4 w-4 rounded border-zinc-600 bg-zinc-950 text-emerald-500" />
            Require my approval before it books
          </label>
          <button type="submit" className="flex items-center justify-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400"><Plus className="h-4 w-4" /> Add type</button>
        </form>
        {types.length === 0 ? (
          <p className="text-sm text-zinc-400">No appointment types yet.</p>
        ) : (
          <ul className="divide-y divide-zinc-800">
            {types.map((t) => (
              <li key={t.id} className="flex flex-wrap items-center gap-3 py-2.5 text-sm">
                <div className="min-w-0 flex-1">
                  <span className="text-zinc-200">{t.name}</span>
                  <span className="text-zinc-400"> · {t.duration_minutes} min · {t.pricing_mode === 'hourly' ? `${money(t.price_cents)}/hr` : money(t.price_cents)}</span>
                </div>
                <label className="flex items-center gap-1.5 text-xs text-zinc-400">
                  <input type="checkbox" checked={t.requires_approval} onChange={(e) => patchType(t.id, { requires_approval: e.target.checked })} className="h-3.5 w-3.5 rounded border-zinc-600 bg-zinc-950 text-emerald-500" />
                  Needs approval
                </label>
                <button onClick={() => removeType(t.id)} className="text-zinc-400 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Availability */}
      <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-5 shadow-sm">
        <h2 className="mb-3 text-sm font-semibold text-zinc-100">Weekly availability</h2>
        <div className="space-y-2">
          {slots.map((s, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2">
              <select value={s.weekday} onChange={(e) => setSlot(i, { weekday: parseInt(e.target.value, 10) })} className={inputCls}>
                {WEEKDAYS.map((d, idx) => <option key={idx} value={idx}>{d}</option>)}
              </select>
              <input type="time" value={hhmm(s.start_time)} onChange={(e) => setSlot(i, { start_time: e.target.value })} className={inputCls} />
              <span className="text-zinc-400">to</span>
              <input type="time" value={hhmm(s.end_time)} onChange={(e) => setSlot(i, { end_time: e.target.value })} className={inputCls} />
              <select value={s.booking_type_id ?? ''} onChange={(e) => setSlot(i, { booking_type_id: e.target.value || null })} className={inputCls}>
                <option value="">All types</option>
                {types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
              <button type="button" onClick={() => setSlots((sl) => sl.filter((_, idx) => idx !== i))} className="text-zinc-400 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
            </div>
          ))}
        </div>
        <div className="mt-3 flex gap-2">
          <button onClick={addSlot} className="text-xs font-medium text-emerald-400 hover:underline">+ Add window</button>
          <button onClick={saveAvailability} disabled={savingAvail} className="ml-auto flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-60">
            {savingAvail ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Save availability
          </button>
        </div>
      </section>

      {/* Rate rules — dynamic time pricing (for hourly types) */}
      <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-zinc-100">Time-based pricing</h2>
        <p className="mb-3 mt-1 text-xs text-zinc-500">
          Charge more for certain hours or days on <span className="text-zinc-300">per-hour</span> types — e.g. after 8pm at 2×.
          {!hasHourly && ' Add a per-hour appointment type above to use these.'}
        </p>
        <div className="space-y-2">
          {rules.map((r, i) => (
            <div key={r.id} className="flex flex-wrap items-center gap-2">
              <input value={r.label} onChange={(e) => setRule(i, { label: e.target.value })} placeholder="Label (e.g. After hours)" className={`w-40 ${inputCls}`} />
              <select value={r.weekday ?? ''} onChange={(e) => setRule(i, { weekday: e.target.value === '' ? null : parseInt(e.target.value, 10) })} className={inputCls}>
                <option value="">Every day</option>
                {WEEKDAYS.map((d, idx) => <option key={idx} value={idx}>{d}</option>)}
              </select>
              <input type="time" value={hhmm(r.start_time)} onChange={(e) => setRule(i, { start_time: e.target.value })} className={inputCls} />
              <span className="text-zinc-400">to</span>
              <input type="time" value={hhmm(r.end_time)} onChange={(e) => setRule(i, { end_time: e.target.value })} className={inputCls} />
              <div className="flex items-center gap-1">
                <input type="number" min="0" step="0.1" value={r.multiplier} onChange={(e) => setRule(i, { multiplier: parseFloat(e.target.value) || 0 })} className={`w-16 ${inputCls}`} />
                <span className="text-sm text-zinc-400">×</span>
              </div>
              <select value={r.booking_type_id ?? ''} onChange={(e) => setRule(i, { booking_type_id: e.target.value || null })} className={inputCls}>
                <option value="">All types</option>
                {types.filter((t) => t.pricing_mode === 'hourly').map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
              <button type="button" onClick={() => setRules((rl) => rl.filter((_, idx) => idx !== i))} className="text-zinc-400 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
            </div>
          ))}
        </div>
        <div className="mt-3 flex gap-2">
          <button onClick={addRule} className="text-xs font-medium text-emerald-400 hover:underline">+ Add rule</button>
          <button onClick={saveRules} disabled={savingRules} className="ml-auto flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-60">
            {savingRules ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Save rules
          </button>
        </div>
      </section>

      {/* Rider — Pro creators only */}
      {isCreator && (
        <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-zinc-100">Your rider</h2>
            {!riderUnlocked && <span className="inline-flex items-center gap-1 rounded-full bg-zinc-800 px-2 py-0.5 text-[11px] font-medium text-zinc-400"><Lock className="h-3 w-3" /> Pro</span>}
          </div>
          <p className="mb-3 mt-1 text-xs text-zinc-500">
            Requirements a client agrees to when booking you — point of contact, water/snacks, shade, travel covered, …
          </p>
          {!riderUnlocked ? (
            <p className="rounded-lg border border-dashed border-zinc-700 p-4 text-sm text-zinc-400">
              Riders are a <span className="text-zinc-200">Pro</span> creator feature. Upgrade to set the conditions you need met for every booking.
            </p>
          ) : (
            <>
              <div className="space-y-2">
                {rider.map((r, i) => (
                  <div key={r.id} className="flex flex-wrap items-center gap-2">
                    <input value={r.label} onChange={(e) => setRiderItem(i, { label: e.target.value })} placeholder="Requirement (e.g. Point of contact on site all day)" className={`flex-1 ${inputCls}`} />
                    <label className="flex items-center gap-1.5 text-xs text-zinc-400">
                      <input type="checkbox" checked={r.is_required} onChange={(e) => setRiderItem(i, { is_required: e.target.checked })} className="h-3.5 w-3.5 rounded border-zinc-600 bg-zinc-950 text-emerald-500" />
                      Required
                    </label>
                    <button type="button" onClick={() => setRider((rl) => rl.filter((_, idx) => idx !== i))} className="text-zinc-400 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
                  </div>
                ))}
              </div>
              <div className="mt-3 flex gap-2">
                <button onClick={addRiderItem} className="text-xs font-medium text-emerald-400 hover:underline">+ Add requirement</button>
                <button onClick={saveRider} disabled={savingRider} className="ml-auto flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-60">
                  {savingRider ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Save rider
                </button>
              </div>
            </>
          )}
        </section>
      )}

      {/* All bookings */}
      <section className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5 shadow-sm">
        <h2 className="mb-3 text-sm font-semibold text-zinc-100">All bookings</h2>
        {bookings.length === 0 ? (
          <p className="flex items-center gap-2 text-sm text-zinc-400"><Calendar className="h-4 w-4" /> No bookings yet.</p>
        ) : (
          <ul className="divide-y divide-zinc-800">
            {bookings.map((b) => (
              <li key={b.id} className="flex items-center gap-3 py-2 text-sm">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-zinc-200">{b.customer_email || 'No email'} <span className="text-zinc-500">{money(b.quoted_price_cents)}</span></div>
                  <div className="text-xs text-zinc-400">{new Date(b.starts_at).toLocaleString()}</div>
                </div>
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${statusStyle[b.status]}`}>{b.status}</span>
                <select value={b.status} onChange={(e) => setBookingStatus(b, e.target.value)} className="rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-100">
                  {['pending', 'confirmed', 'cancelled', 'completed'].map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </li>
            ))}
          </ul>
        )}
      </section>
    </SurfaceShell>
  )
}
