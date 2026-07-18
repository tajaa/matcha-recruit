import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, MapPin, Plus, Star, Trash2, Pencil, X, Check } from 'lucide-react'
import { cappeApi } from '../../api'
import SurfaceShell from '../../components/SurfaceShell'
import { CAPPE_TIMEZONES } from '../../data/timezones'
import type { CappeLocation, CappeLocationHours, CappeLocationInput } from '../../types'

const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const inputCls =
  'w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-lime-500'

type EditState = {
  name: string
  address: string
  phone: string
  email: string
  timezone: string
  lat: string
  lng: string
  hours: CappeLocationHours[]
  is_default: boolean
}

function defaultHours(existing: CappeLocationHours[] = []): CappeLocationHours[] {
  return DAY_LABELS.map((_, day) => {
    const ex = existing.find((h) => h.day === day)
    return ex
      ? { day, open: ex.open ?? '09:00', close: ex.close ?? '17:00', closed: !!ex.closed }
      : { day, open: '09:00', close: '17:00', closed: day >= 5 } // Sat/Sun closed by default
  })
}

function blankEdit(): EditState {
  return { name: '', address: '', phone: '', email: '', timezone: '', lat: '', lng: '', hours: defaultHours(), is_default: false }
}

function editFrom(l: CappeLocation): EditState {
  return {
    name: l.name,
    address: l.address || '',
    phone: l.contact_phone || '',
    email: l.contact_email || '',
    timezone: l.timezone || '',
    lat: l.lat != null ? String(l.lat) : '',
    lng: l.lng != null ? String(l.lng) : '',
    hours: defaultHours(l.hours),
    is_default: l.is_default,
  }
}

function hoursSummary(hours: CappeLocationHours[]): string {
  const open = (hours || []).filter((h) => !h.closed)
  if (!open.length) return 'Hours not set'
  return `${open.length} day${open.length === 1 ? '' : 's'} open`
}

export default function Locations() {
  const { siteId } = useParams<{ siteId: string }>()
  const [locations, setLocations] = useState<CappeLocation[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editId, setEditId] = useState<string | 'new' | null>(null)
  const [draft, setDraft] = useState<EditState>(blankEdit())
  const [saving, setSaving] = useState(false)

  function load() {
    cappeApi.get<CappeLocation[]>(`/sites/${siteId}/locations`)
      .then(setLocations)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load locations'))
  }
  useEffect(load, [siteId]) // eslint-disable-line react-hooks/exhaustive-deps

  function startNew() { setDraft(blankEdit()); setEditId('new'); setError(null) }
  function startEdit(l: CappeLocation) { setDraft(editFrom(l)); setEditId(l.id); setError(null) }
  function cancel() { setEditId(null) }

  function setHour(i: number, patch: Partial<CappeLocationHours>) {
    setDraft((d) => ({ ...d, hours: d.hours.map((h, j) => (j === i ? { ...h, ...patch } : h)) }))
  }

  async function save() {
    if (!draft.name.trim()) { setError('Branch name is required.'); return }
    setSaving(true)
    setError(null)
    const payload: CappeLocationInput = {
      name: draft.name.trim(),
      address: draft.address.trim() || null,
      contact_phone: draft.phone.trim() || null,
      contact_email: draft.email.trim() || null,
      timezone: draft.timezone || null,
      lat: draft.lat.trim() ? Number(draft.lat) : null,
      lng: draft.lng.trim() ? Number(draft.lng) : null,
      hours: draft.hours,
      is_default: draft.is_default,
    }
    try {
      if (editId === 'new') {
        await cappeApi.post<CappeLocation>(`/sites/${siteId}/locations`, payload)
      } else {
        await cappeApi.put<CappeLocation>(`/sites/${siteId}/locations/${editId}`, payload)
      }
      setEditId(null)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save location')
    } finally {
      setSaving(false)
    }
  }

  async function setDefault(id: string) {
    await cappeApi.put<CappeLocation>(`/sites/${siteId}/locations/${id}`, { is_default: true }).then(load)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to set default'))
  }

  async function deactivate(id: string) {
    if (!window.confirm('Deactivate this branch? Its booking & client history is kept.')) return
    await cappeApi.delete(`/sites/${siteId}/locations/${id}`).then(load)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to deactivate'))
  }

  async function move(index: number, dir: -1 | 1) {
    if (!locations) return
    const j = index + dir
    if (j < 0 || j >= locations.length) return
    const a = locations[index], b = locations[j]
    // Persist the swap by assigning each its new ordinal.
    await Promise.all([
      cappeApi.put(`/sites/${siteId}/locations/${a.id}`, { sort_order: j }),
      cappeApi.put(`/sites/${siteId}/locations/${b.id}`, { sort_order: index }),
    ]).then(load).catch((e) => setError(e instanceof Error ? e.message : 'Failed to reorder'))
  }

  const actions = editId === null && (locations?.length ?? 0) > 0 ? (
    <button onClick={startNew} className="flex items-center gap-1.5 rounded-lg bg-lime-500 px-3 py-2 text-sm font-semibold text-zinc-950 hover:bg-lime-400">
      <Plus className="h-4 w-4" /> Add branch
    </button>
  ) : undefined

  return (
    <SurfaceShell title="Locations" subtitle="Your branches — each drives its own map, hours, bookings & client mapping." actions={actions}>
      {error && <p className="mb-4 text-sm text-red-400">{error}</p>}

      {locations === null ? (
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>
      ) : (
        <>
          {/* editor */}
          {editId !== null && (
            <div className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-6">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-zinc-100">{editId === 'new' ? 'New branch' : 'Edit branch'}</h2>
                <button onClick={cancel} className="text-zinc-500 hover:text-zinc-200"><X className="h-5 w-5" /></button>
              </div>
              <div className="space-y-4">
                <div>
                  <label className="mb-1 block text-sm font-medium text-zinc-300">Branch name</label>
                  <input value={draft.name} onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} placeholder="Downtown" className={inputCls} />
                  <p className="mt-1 text-xs text-zinc-500">This is the name clients pick & that your CSV import maps to.</p>
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-zinc-300">Address</label>
                  <input value={draft.address} onChange={(e) => setDraft((d) => ({ ...d, address: e.target.value }))} placeholder="123 Main St, City, ST" className={inputCls} />
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-sm font-medium text-zinc-300">Contact phone</label>
                    <input value={draft.phone} onChange={(e) => setDraft((d) => ({ ...d, phone: e.target.value }))} placeholder="555-0100" className={inputCls} />
                  </div>
                  <div>
                    <label className="mb-1 block text-sm font-medium text-zinc-300">Contact email</label>
                    <input value={draft.email} onChange={(e) => setDraft((d) => ({ ...d, email: e.target.value }))} placeholder="branch@business.com" className={inputCls} />
                  </div>
                </div>
                <div className="grid gap-4 sm:grid-cols-3">
                  <div>
                    <label className="mb-1 block text-sm font-medium text-zinc-300">Timezone</label>
                    <select value={draft.timezone} onChange={(e) => setDraft((d) => ({ ...d, timezone: e.target.value }))} className={inputCls}>
                      <option value="">Site default</option>
                      {CAPPE_TIMEZONES.map((tz) => <option key={tz.value} value={tz.value}>{tz.label}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="mb-1 block text-sm font-medium text-zinc-300">Latitude <span className="text-zinc-500">(adds map)</span></label>
                    <input value={draft.lat} onChange={(e) => setDraft((d) => ({ ...d, lat: e.target.value }))} placeholder="37.7749" className={inputCls} />
                  </div>
                  <div>
                    <label className="mb-1 block text-sm font-medium text-zinc-300">Longitude</label>
                    <input value={draft.lng} onChange={(e) => setDraft((d) => ({ ...d, lng: e.target.value }))} placeholder="-122.4194" className={inputCls} />
                  </div>
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-zinc-300">Opening hours</label>
                  <div className="space-y-1.5">
                    {draft.hours.map((h, i) => (
                      <div key={h.day} className="flex items-center gap-2">
                        <span className="w-10 text-xs text-zinc-400">{DAY_LABELS[h.day]}</span>
                        <label className="flex w-16 items-center gap-1 text-xs text-zinc-500">
                          <input type="checkbox" checked={!h.closed} onChange={(e) => setHour(i, { closed: !e.target.checked })} className="h-3.5 w-3.5 rounded border-zinc-600 bg-zinc-900 text-lime-500" /> Open
                        </label>
                        {!h.closed ? (
                          <>
                            <input type="time" value={h.open || ''} onChange={(e) => setHour(i, { open: e.target.value })} className={`${inputCls} w-32`} />
                            <span className="text-zinc-500">–</span>
                            <input type="time" value={h.close || ''} onChange={(e) => setHour(i, { close: e.target.value })} className={`${inputCls} w-32`} />
                          </>
                        ) : <span className="text-xs text-zinc-600">Closed</span>}
                      </div>
                    ))}
                  </div>
                </div>
                <label className="flex items-center gap-2 text-sm text-zinc-300">
                  <input type="checkbox" checked={draft.is_default} onChange={(e) => setDraft((d) => ({ ...d, is_default: e.target.checked }))} className="h-4 w-4 rounded border-zinc-600 bg-zinc-900 text-lime-500" />
                  Make this the default branch
                </label>
                <div className="flex justify-end gap-2">
                  <button onClick={cancel} className="rounded-lg border border-zinc-700 px-4 py-2 text-sm font-medium text-zinc-300 hover:bg-zinc-800">Cancel</button>
                  <button onClick={save} disabled={saving} className="flex items-center gap-2 rounded-lg bg-lime-500 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-lime-400 disabled:opacity-60">
                    {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} Save branch
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* list / empty state */}
          {locations.length === 0 && editId === null ? (
            <div className="rounded-2xl border border-dashed border-zinc-700 py-12 text-center text-sm text-zinc-500">
              <MapPin className="mx-auto mb-2 h-7 w-7 text-zinc-300" /> No branches yet.
              <p className="mx-auto mt-1 max-w-sm text-xs text-zinc-500">Add a branch if you operate from more than one location. With none, your site runs as a single location.</p>
              <button onClick={startNew} className="mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-lime-400 hover:text-lime-300">
                <Plus className="h-4 w-4" /> Add your first branch
              </button>
            </div>
          ) : (
            <div className="space-y-2">
              {locations.map((l, i) => (
                <div key={l.id} className="flex items-center gap-4 rounded-2xl border border-zinc-800 bg-zinc-900 px-5 py-3.5">
                  <div className="flex flex-col text-zinc-600">
                    <button onClick={() => move(i, -1)} disabled={i === 0} className="hover:text-zinc-300 disabled:opacity-30">▲</button>
                    <button onClick={() => move(i, 1)} disabled={i === locations.length - 1} className="hover:text-zinc-300 disabled:opacity-30">▼</button>
                  </div>
                  <MapPin className="h-5 w-5 shrink-0 text-zinc-500" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-semibold text-zinc-100">{l.name}</span>
                      {l.is_default && <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase text-lime-400"><Star className="h-3 w-3" />Default</span>}
                    </div>
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-zinc-500">
                      {l.address && <span className="truncate">{l.address}</span>}
                      {l.contact_phone && <span>{l.contact_phone}</span>}
                      <span>{hoursSummary(l.hours)}</span>
                      {l.timezone && <span>{l.timezone}</span>}
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {!l.is_default && <button onClick={() => setDefault(l.id)} title="Set as default" className="rounded-md border border-zinc-700 px-2.5 py-1 text-xs font-medium text-zinc-300 hover:bg-zinc-800">Set default</button>}
                    <button onClick={() => startEdit(l)} className="inline-flex items-center gap-1 rounded-md border border-zinc-700 px-2.5 py-1 text-xs font-medium text-zinc-300 hover:bg-zinc-800"><Pencil className="h-3.5 w-3.5" /> Edit</button>
                    <button onClick={() => deactivate(l.id)} className="text-zinc-500 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </SurfaceShell>
  )
}
