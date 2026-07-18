import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { cappeApi } from '../../../api'
import { useCappeMe } from '../../../hooks/useCappeMe'
import type {
  CappeBooking, CappeBookingType, CappeAvailabilitySlot,
  CappeRateRule, CappeRiderItem, CappeDiscount, CappeProduct,
  CappeStaff, CappeLocation, CappeSite,
  CappePricingMode,
} from '../../../types'
import { hhmm } from './constants'
import type { TypeForm, StaffForm, LocForm } from './types'

export function useBookings() {
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
  const [locForm, setLocForm] = useState<LocForm>({ name: '', timezone: '', address: '', phone: '' })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<'calendar' | 'list'>('calendar')
  const [typeForm, setTypeForm] = useState<TypeForm>({
    name: '', description: '', duration_minutes: '30', pricing_mode: 'flat' as CappePricingMode,
    price: '', requires_approval: false, category: '', buffer: '0', staffIds: [] as string[],
  })
  const [staffForm, setStaffForm] = useState<StaffForm>({ name: '', bio: '', image_url: '' })
  const [showStaffImport, setShowStaffImport] = useState(false)
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

  return {
    siteId, account,
    types, setTypes, slots, setSlots, bookings, rules, setRules, rider, setRider,
    products, discounts, setDiscounts, staff, locations,
    multiLoc, selLoc, showLocMgr, setShowLocMgr, locForm, setLocForm,
    loading, error, view, setView,
    typeForm, setTypeForm, staffForm, setStaffForm,
    showStaffImport, setShowStaffImport,
    savingAvail, savingRules, savingRider, savingDiscounts,
    isCreator, riderUnlocked,
    loadConfig, switchLocation,
    addLocation, setLocationDefault, deactivateLocation,
    addType, addStaff, removeStaff, toggleTypeStaff, patchType, removeType,
    addSlot, setSlot, saveAvailability,
    addRule, setRule, saveRules,
    addRiderItem, setRiderItem, saveRider,
    addDiscount, setDiscount, saveDiscounts,
    acceptBooking, declineBooking, setBookingStatus,
    pending, hasHourly,
  }
}
