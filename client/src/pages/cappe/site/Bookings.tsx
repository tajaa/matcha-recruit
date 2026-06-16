import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, Plus, Trash2, Calendar, Save, Check, X, Lock, Clock, ShieldCheck, List, Percent, Users, MapPin } from 'lucide-react'
import { cappeApi } from '../../../api/cappeClient'
import { useCappeMe } from '../../../hooks/useCappeMe'
import SurfaceShell, { WEEKDAYS } from '../../../components/cappe/SurfaceShell'
import BookingsCalendar from '../../../components/cappe/BookingsCalendar'
import ImageUpload from '../../../components/cappe/ImageUpload'
import { CAPPE_TIMEZONES } from '../../../data/timezones'
import type {
  CappeBooking, CappeBookingType, CappeAvailabilitySlot,
  CappeRateRule, CappeRiderItem, CappePricingMode,
  CappeDiscount, CappeProduct, CappeStaff, CappeLocation, CappeSite,
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
  const [products, setProducts] = useState<CappeProduct[]>([])
  const [discounts, setDiscounts] = useState<CappeDiscount[]>([])
  const [staff, setStaff] = useState<CappeStaff[]>([])
  const [locations, setLocations] = useState<CappeLocation[]>([])
  const [multiLoc, setMultiLoc] = useState(false)  // site.is_multi_location — gates the branch UI
  const [selLoc, setSelLoc] = useState<string>('')  // '' = Shared / all locations
  const [showLocMgr, setShowLocMgr] = useState(false)
  const [locForm, setLocForm] = useState({ name: '', timezone: '', address: '', phone: '' })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<'calendar' | 'list'>('calendar')
  const [typeForm, setTypeForm] = useState({
    name: '', description: '', duration_minutes: '30', pricing_mode: 'flat' as CappePricingMode,
    price: '', requires_approval: false, category: '', buffer: '0', staffIds: [] as string[],
  })
  const [staffForm, setStaffForm] = useState({ name: '', bio: '', image_url: '' })
  const [savingAvail, setSavingAvail] = useState(false)
  const [savingRules, setSavingRules] = useState(false)
  const [savingRider, setSavingRider] = useState(false)
  const [savingDiscounts, setSavingDiscounts] = useState(false)

  const isCreator = account?.account_type === 'personal'
  const riderUnlocked = isCreator && account?.plan === 'pro'

  // Config (types/availability/staff/rates/discounts) is scoped to the selected
  // location: a concrete location → its rows + shared (NULL); '' with locations
  // present → only shared; no locations → everything (today's behavior). The
  // bookings LIST filters to the location (or all when '').
  async function loadConfig(locs: CappeLocation[], loc: string) {
    const cfg = locs.length === 0 ? '' : (loc ? `?location_id=${loc}` : '?shared=true')
    const bq = loc ? `?location_id=${loc}` : ''
    const [t, a, b, r, rd, p, d, st] = await Promise.all([
      cappeApi.get<CappeBookingType[]>(`/sites/${siteId}/booking-types${cfg}`),
      cappeApi.get<CappeAvailabilitySlot[]>(`/sites/${siteId}/availability${cfg}`),
      cappeApi.get<CappeBooking[]>(`/sites/${siteId}/bookings${bq}`),
      cappeApi.get<CappeRateRule[]>(`/sites/${siteId}/rate-rules${cfg}`).catch(() => []),
      cappeApi.get<CappeRiderItem[]>(`/sites/${siteId}/rider`).catch(() => []),
      cappeApi.get<CappeProduct[]>(`/sites/${siteId}/products`).catch(() => []),
      cappeApi.get<CappeDiscount[]>(`/sites/${siteId}/discounts${cfg}`).catch(() => []),
      cappeApi.get<CappeStaff[]>(`/sites/${siteId}/staff${cfg}`).catch(() => []),
    ])
    setTypes(t); setSlots(a); setBookings(b); setRules(r); setRider(rd); setProducts(p); setDiscounts(d); setStaff(st)
  }

  function switchLocation(loc: string) {
    setSelLoc(loc)
    loadConfig(locations, loc).catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
  }

  useEffect(() => {
    cappeApi.get<CappeSite>(`/sites/${siteId}`).then((s) => setMultiLoc(!!s.is_multi_location)).catch(() => {})
    cappeApi.get<CappeLocation[]>(`/sites/${siteId}/locations`).catch(() => [] as CappeLocation[])
      .then((locs) => {
        setLocations(locs)
        const def = locs.find((l) => l.is_default && l.active) || locs.find((l) => l.active)
        const init = def ? def.id : ''
        setSelLoc(init)
        return loadConfig(locs, init)
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setLoading(false))
  }, [siteId])

  // --- Locations ---
  async function addLocation(e: React.FormEvent) {
    e.preventDefault()
    if (!locForm.name.trim()) return
    const created = await cappeApi.post<CappeLocation>(`/sites/${siteId}/locations`, {
      name: locForm.name.trim(),
      timezone: locForm.timezone || null,
      address: locForm.address.trim() || null,
      contact_phone: locForm.phone.trim() || null,
    })
    setLocations((ls) => [...ls, created])
    setLocForm({ name: '', timezone: '', address: '', phone: '' })
    switchLocation(created.id)
  }
  async function setLocationDefault(id: string) {
    const updated = await cappeApi.put<CappeLocation>(`/sites/${siteId}/locations/${id}`, { is_default: true })
    setLocations((ls) => ls.map((l) => ({ ...l, is_default: l.id === id })).map((l) => (l.id === id ? updated : l)))
  }
  async function deactivateLocation(id: string) {
    if (!window.confirm('Deactivate this location? Its appointment history is kept.')) return
    await cappeApi.delete(`/sites/${siteId}/locations/${id}`)
    const next = locations.filter((l) => l.id !== id)
    setLocations(next)
    if (selLoc === id) switchLocation(next.find((l) => l.active)?.id || '')
  }

  async function addType(e: React.FormEvent) {
    e.preventDefault()
    if (!typeForm.name.trim()) return
    const created = await cappeApi.post<CappeBookingType>(`/sites/${siteId}/booking-types`, {
      name: typeForm.name.trim(),
      description: typeForm.description.trim() || null,
      duration_minutes: parseInt(typeForm.duration_minutes, 10) || 30,
      pricing_mode: typeForm.pricing_mode,
      price_cents: Math.round((parseFloat(typeForm.price) || 0) * 100),
      requires_approval: typeForm.requires_approval,
      category: typeForm.category.trim() || null,
      buffer_minutes: parseInt(typeForm.buffer, 10) || 0,
      staff_ids: typeForm.staffIds,
      location_id: selLoc || null,
    })
    setTypes((t) => [...t, created])
    setTypeForm({ name: '', description: '', duration_minutes: '30', pricing_mode: 'flat', price: '', requires_approval: false, category: '', buffer: '0', staffIds: [] })
  }

  // --- Staff ---
  async function addStaff(e: React.FormEvent) {
    e.preventDefault()
    if (!staffForm.name.trim()) return
    const created = await cappeApi.post<CappeStaff>(`/sites/${siteId}/staff`, {
      name: staffForm.name.trim(), bio: staffForm.bio.trim() || null, image_url: staffForm.image_url.trim() || null,
      location_id: selLoc || null,
    })
    setStaff((s) => [...s, created])
    setStaffForm({ name: '', bio: '', image_url: '' })
  }
  async function removeStaff(id: string) {
    await cappeApi.delete(`/sites/${siteId}/staff/${id}`)
    setStaff((s) => s.filter((x) => x.id !== id))
    // Drop the removed staff from any service mapping in local state.
    setTypes((ts) => ts.map((t) => ({ ...t, staff_ids: (t.staff_ids || []).filter((sid) => sid !== id) })))
  }
  function toggleTypeStaff(t: CappeBookingType, staffId: string) {
    const has = (t.staff_ids || []).includes(staffId)
    const next = has ? t.staff_ids.filter((s) => s !== staffId) : [...(t.staff_ids || []), staffId]
    patchType(t.id, { staff_ids: next })
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
      const q = selLoc ? `?location_id=${selLoc}` : ''
      const saved = await cappeApi.put<CappeAvailabilitySlot[]>(`/sites/${siteId}/availability${q}`, payload)
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
      const q = selLoc ? `?location_id=${selLoc}` : ''
      const saved = await cappeApi.put<CappeRateRule[]>(`/sites/${siteId}/rate-rules${q}`, payload)
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

  // --- Discounts ---
  function addDiscount() {
    setDiscounts((d) => [...d, {
      id: `tmp-${d.length}`, site_id: siteId!, label: 'Slow-week special',
      percent_off: 15, scope: 'all', target_id: null, active: true,
      starts_on: null, ends_on: null, created_at: '',
    }])
  }
  function setDiscount(i: number, patch: Partial<CappeDiscount>) {
    setDiscounts((d) => d.map((x, idx) => (idx === i ? { ...x, ...patch } : x)))
  }
  async function saveDiscounts() {
    setSavingDiscounts(true)
    setError(null)
    try {
      const payload = {
        discounts: discounts.map((d) => ({
          label: d.label || 'Discount',
          percent_off: Math.max(1, Math.min(90, Math.round(d.percent_off) || 1)),
          scope: d.scope,
          target_id: d.scope === 'all' ? null : d.target_id,
          active: d.active,
          starts_on: d.starts_on || null,
          ends_on: d.ends_on || null,
        })),
      }
      const q = selLoc ? `?location_id=${selLoc}` : ''
      const saved = await cappeApi.put<CappeDiscount[]>(`/sites/${siteId}/discounts${q}`, payload)
      setDiscounts(saved)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save discounts')
    } finally {
      setSavingDiscounts(false)
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

      {/* Location switcher — manage each location's appts/staff/hours separately.
          Multi-location sites only; single-location sites keep a simpler page. */}
      {multiLoc && (
      <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <MapPin className="h-4 w-4 text-emerald-400" />
            {locations.filter((l) => l.active).length > 0 ? (
              <>
                <span className="text-xs text-zinc-500">Managing</span>
                <select value={selLoc} onChange={(e) => switchLocation(e.target.value)} className={inputCls}>
                  {locations.filter((l) => l.active).map((l) => (
                    <option key={l.id} value={l.id}>{l.name}{l.is_default ? ' · default' : ''}</option>
                  ))}
                  <option value="">Shared · all locations</option>
                </select>
              </>
            ) : (
              <span className="text-sm text-zinc-400">One location. Add another to manage (e.g.) LA and San Diego separately.</span>
            )}
          </div>
          <button onClick={() => setShowLocMgr((o) => !o)} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800">
            {showLocMgr ? 'Done' : 'Manage locations'}
          </button>
        </div>
        {selLoc === '' && locations.filter((l) => l.active).length > 0 && (
          <p className="mt-2 text-xs text-zinc-500">Editing the <span className="text-zinc-300">shared</span> set — applies to every location. Pick a location to edit just its appointments.</p>
        )}
        {showLocMgr && (
          <div className="mt-4 space-y-2 border-t border-zinc-800 pt-4">
            {locations.filter((l) => l.active).map((l) => (
              <div key={l.id} className="flex items-center gap-2 text-sm">
                <span className="flex-1 text-zinc-200">
                  {l.name}
                  {l.is_default && <span className="ml-2 rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-400">DEFAULT</span>}
                  {l.timezone && <span className="ml-2 text-xs text-zinc-500">{l.timezone}</span>}
                </span>
                {!l.is_default && <button onClick={() => setLocationDefault(l.id)} className="text-xs text-zinc-400 hover:text-emerald-400">Make default</button>}
                <button onClick={() => deactivateLocation(l.id)} className="text-zinc-500 hover:text-red-400" title="Deactivate"><Trash2 className="h-4 w-4" /></button>
              </div>
            ))}
            <form onSubmit={addLocation} className="grid grid-cols-2 gap-2 pt-1 sm:grid-cols-4">
              <input value={locForm.name} onChange={(e) => setLocForm((f) => ({ ...f, name: e.target.value }))} placeholder="Name (e.g. LA)" className={inputCls} />
              <select value={locForm.timezone} onChange={(e) => setLocForm((f) => ({ ...f, timezone: e.target.value }))} className={inputCls}>
                <option value="">Timezone…</option>
                {CAPPE_TIMEZONES.map((tz) => <option key={tz.value} value={tz.value}>{tz.label}</option>)}
              </select>
              <input value={locForm.address} onChange={(e) => setLocForm((f) => ({ ...f, address: e.target.value }))} placeholder="Address" className={inputCls} />
              <input value={locForm.phone} onChange={(e) => setLocForm((f) => ({ ...f, phone: e.target.value }))} placeholder="Phone" className={inputCls} />
              <button type="submit" className="col-span-2 inline-flex items-center justify-center gap-1 rounded-lg border border-dashed border-zinc-700 py-2 text-sm font-medium text-zinc-300 hover:border-emerald-500 hover:text-emerald-400 sm:col-span-4">
                <Plus className="h-4 w-4" /> Add location
              </button>
            </form>
          </div>
        )}
      </section>
      )}

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

      {/* Schedule — calendar / list of all bookings */}
      <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-5 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-zinc-100">Your schedule</h2>
          <div className="flex items-center gap-0.5 rounded-lg border border-zinc-700 p-0.5">
            <button onClick={() => setView('calendar')} className={`flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium ${view === 'calendar' ? 'bg-emerald-500 text-zinc-950' : 'text-zinc-400 hover:text-zinc-200'}`}><Calendar className="h-3.5 w-3.5" /> Calendar</button>
            <button onClick={() => setView('list')} className={`flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium ${view === 'list' ? 'bg-emerald-500 text-zinc-950' : 'text-zinc-400 hover:text-zinc-200'}`}><List className="h-3.5 w-3.5" /> List</button>
          </div>
        </div>
        {view === 'calendar' ? (
          <BookingsCalendar bookings={bookings} availability={slots} types={types} onAccept={acceptBooking} onDecline={declineBooking} onStatus={setBookingStatus} />
        ) : bookings.length === 0 ? (
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

      {/* Staff / stylists */}
      <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-5 shadow-sm">
        <h2 className="flex items-center gap-1.5 text-sm font-semibold text-zinc-100"><Users className="h-4 w-4 text-emerald-400" /> Staff</h2>
        <p className="mb-3 mt-1 text-xs text-zinc-500">Add the people customers book with. Then choose who performs each service below — customers can pick a specific person or “any available”. Leave a service with no staff to keep one shared calendar.</p>
        <form onSubmit={addStaff} className="mb-4 flex flex-wrap items-end gap-2">
          <input value={staffForm.name} onChange={(e) => setStaffForm({ ...staffForm, name: e.target.value })} placeholder="Name — e.g. Maria" className={`w-44 ${inputCls}`} />
          <input value={staffForm.bio} onChange={(e) => setStaffForm({ ...staffForm, bio: e.target.value })} placeholder="Title / bio (optional)" className={`flex-1 ${inputCls}`} />
          <div className="w-56"><ImageUpload siteId={siteId || ''} value={staffForm.image_url} onChange={(url) => setStaffForm({ ...staffForm, image_url: url })} placeholder="Photo (optional)" /></div>
          <button type="submit" className="flex items-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400"><Plus className="h-4 w-4" /> Add</button>
        </form>
        {staff.length === 0 ? (
          <p className="text-sm text-zinc-400">No staff yet — your bookings use one shared calendar.</p>
        ) : (
          <ul className="flex flex-wrap gap-2">
            {staff.map((s) => (
              <li key={s.id} className="flex items-center gap-2 rounded-full border border-zinc-700 bg-zinc-950 py-1 pl-1 pr-3 text-sm">
                <span className="flex h-7 w-7 items-center justify-center overflow-hidden rounded-full bg-zinc-800 text-xs font-semibold uppercase text-zinc-300">
                  {s.image_url ? <img src={s.image_url} alt="" className="h-full w-full object-cover" /> : (s.name || '?').slice(0, 1)}
                </span>
                <span className="text-zinc-200">{s.name}</span>
                <button onClick={() => removeStaff(s.id)} className="text-zinc-500 hover:text-red-400"><Trash2 className="h-3.5 w-3.5" /></button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Booking types */}
      <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-5 shadow-sm">
        <h2 className="mb-3 text-sm font-semibold text-zinc-100">Appointment types</h2>
        <form onSubmit={addType} className="mb-4 grid gap-2 sm:grid-cols-2">
          <input value={typeForm.name} onChange={(e) => setTypeForm({ ...typeForm, name: e.target.value })} placeholder="Name — e.g. Wedding shoot" className={inputCls} />
          <input value={typeForm.description} onChange={(e) => setTypeForm({ ...typeForm, description: e.target.value })} placeholder="Short description (optional)" className={`sm:col-span-2 ${inputCls}`} />
          <div className="flex gap-2">
            <input value={typeForm.duration_minutes} onChange={(e) => setTypeForm({ ...typeForm, duration_minutes: e.target.value })} type="number" min="1" placeholder="min" className={`w-24 ${inputCls}`} />
            <select value={typeForm.pricing_mode} onChange={(e) => setTypeForm({ ...typeForm, pricing_mode: e.target.value as CappePricingMode })} className={inputCls}>
              <option value="flat">Flat price</option>
              <option value="hourly">Per hour</option>
            </select>
            <input value={typeForm.price} onChange={(e) => setTypeForm({ ...typeForm, price: e.target.value })} type="number" min="0" step="0.01" placeholder={typeForm.pricing_mode === 'hourly' ? '$/hr' : '$'} className={`w-24 ${inputCls}`} />
          </div>
          <div className="flex gap-2">
            <input value={typeForm.category} onChange={(e) => setTypeForm({ ...typeForm, category: e.target.value })} placeholder="Category — e.g. Color (optional)" className={`flex-1 ${inputCls}`} />
            <input value={typeForm.buffer} onChange={(e) => setTypeForm({ ...typeForm, buffer: e.target.value })} type="number" min="0" step="5" title="Buffer minutes between appointments" placeholder="buffer min" className={`w-28 ${inputCls}`} />
          </div>
          {staff.length > 0 && (
            <div className="sm:col-span-2">
              <div className="mb-1 text-xs text-zinc-400">Who performs it (none = shared calendar)</div>
              <div className="flex flex-wrap gap-1.5">
                {staff.map((s) => {
                  const on = typeForm.staffIds.includes(s.id)
                  return (
                    <button key={s.id} type="button" onClick={() => setTypeForm((f) => ({ ...f, staffIds: on ? f.staffIds.filter((x) => x !== s.id) : [...f.staffIds, s.id] }))}
                      className={`rounded-full border px-2.5 py-1 text-xs ${on ? 'border-emerald-500 bg-emerald-500/15 text-emerald-300' : 'border-zinc-700 text-zinc-400 hover:bg-zinc-800'}`}>
                      {s.name}
                    </button>
                  )
                })}
              </div>
            </div>
          )}
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
                  {t.category && <span className="ml-1.5 rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-400">{t.category}</span>}
                  <span className="text-zinc-400"> · {t.duration_minutes} min · {t.pricing_mode === 'hourly' ? `${money(t.price_cents)}/hr` : money(t.price_cents)}{t.buffer_minutes ? ` · ${t.buffer_minutes}m buffer` : ''}</span>
                  {t.description && <div className="truncate text-xs text-zinc-500">{t.description}</div>}
                  {staff.length > 0 && (
                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                      <span className="text-[11px] text-zinc-500">Staff:</span>
                      {staff.map((s) => {
                        const on = (t.staff_ids || []).includes(s.id)
                        return (
                          <button key={s.id} type="button" onClick={() => toggleTypeStaff(t, s.id)}
                            className={`rounded-full border px-2 py-0.5 text-[11px] ${on ? 'border-emerald-500 bg-emerald-500/15 text-emerald-300' : 'border-zinc-700 text-zinc-500 hover:bg-zinc-800'}`}>
                            {s.name}
                          </button>
                        )
                      })}
                      {(t.staff_ids || []).length === 0 && <span className="text-[11px] text-zinc-600">shared calendar</span>}
                    </div>
                  )}
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
              {staff.length > 0 && (
                <select value={s.staff_id ?? ''} onChange={(e) => setSlot(i, { staff_id: e.target.value || null })} className={inputCls}>
                  <option value="">Any staff</option>
                  {staff.map((st) => <option key={st.id} value={st.id}>{st.name}</option>)}
                </select>
              )}
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

      {/* Discounts — promotional markdowns */}
      <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-5 shadow-sm">
        <h2 className="flex items-center gap-1.5 text-sm font-semibold text-zinc-100"><Percent className="h-4 w-4 text-emerald-400" /> Discounts</h2>
        <p className="mb-3 mt-1 text-xs text-zinc-500">
          Quiet week? Drop a discount across <span className="text-zinc-300">all offerings</span> or a single service/product.
          Leave dates blank to run until you turn it off. The best single discount applies — they don't stack.
        </p>
        <div className="space-y-2">
          {discounts.map((d, i) => {
            const targetValue = d.scope === 'all' ? 'all' : `${d.scope === 'booking_type' ? 'bt' : 'pr'}:${d.target_id ?? ''}`
            return (
              <div key={d.id} className="flex flex-wrap items-center gap-2">
                <input value={d.label} onChange={(e) => setDiscount(i, { label: e.target.value })} placeholder="Label (e.g. Slow-week special)" className={`w-44 ${inputCls}`} />
                <div className="flex items-center gap-1">
                  <input type="number" min="1" max="90" value={d.percent_off} onChange={(e) => setDiscount(i, { percent_off: parseInt(e.target.value, 10) || 0 })} className={`w-16 ${inputCls}`} />
                  <span className="text-sm text-zinc-400">% off</span>
                </div>
                <select
                  value={targetValue}
                  onChange={(e) => {
                    const v = e.target.value
                    if (v === 'all') setDiscount(i, { scope: 'all', target_id: null })
                    else if (v.startsWith('bt:')) setDiscount(i, { scope: 'booking_type', target_id: v.slice(3) })
                    else setDiscount(i, { scope: 'product', target_id: v.slice(3) })
                  }}
                  className={inputCls}
                >
                  <option value="all">All offerings</option>
                  {types.length > 0 && (
                    <optgroup label="Services">
                      {types.map((t) => <option key={t.id} value={`bt:${t.id}`}>{t.name}</option>)}
                    </optgroup>
                  )}
                  {products.length > 0 && (
                    <optgroup label="Products">
                      {products.map((p) => <option key={p.id} value={`pr:${p.id}`}>{p.name}</option>)}
                    </optgroup>
                  )}
                </select>
                <label className="flex items-center gap-1 text-xs text-zinc-400" title="Start date (optional)">
                  <span className="text-zinc-500">from</span>
                  <input type="date" value={d.starts_on ?? ''} onChange={(e) => setDiscount(i, { starts_on: e.target.value || null })} className={inputCls} />
                </label>
                <label className="flex items-center gap-1 text-xs text-zinc-400" title="End date (optional)">
                  <span className="text-zinc-500">to</span>
                  <input type="date" value={d.ends_on ?? ''} onChange={(e) => setDiscount(i, { ends_on: e.target.value || null })} className={inputCls} />
                </label>
                <label className="flex items-center gap-1.5 text-xs text-zinc-400">
                  <input type="checkbox" checked={d.active} onChange={(e) => setDiscount(i, { active: e.target.checked })} className="h-3.5 w-3.5 rounded border-zinc-600 bg-zinc-950 text-emerald-500" />
                  Active
                </label>
                <button type="button" onClick={() => setDiscounts((ds) => ds.filter((_, idx) => idx !== i))} className="text-zinc-400 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
              </div>
            )
          })}
          {discounts.length === 0 && <p className="text-sm text-zinc-400">No discounts running.</p>}
        </div>
        <div className="mt-3 flex gap-2">
          <button onClick={addDiscount} className="text-xs font-medium text-emerald-400 hover:underline">+ Add discount</button>
          <button onClick={saveDiscounts} disabled={savingDiscounts} className="ml-auto flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-60">
            {savingDiscounts ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Save discounts
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

    </SurfaceShell>
  )
}
