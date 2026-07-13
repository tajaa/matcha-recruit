import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Check, FileText, Loader2, MapPin, Plus, Search, ShieldAlert, Trash2, X,
} from 'lucide-react'
import SurfaceShell from '../../../components/cappe/SurfaceShell'
import { useCappeMe } from '../../../hooks/useCappeMe'
import {
  CAPPE_IR_INCIDENT_TYPES,
  CAPPE_IR_SEVERITIES,
  CAPPE_IR_STATUSES,
  cappeIr,
  isIrFeatureDisabledError,
} from '../../../api/cappeIr'
import type {
  CappeIrIncident,
  CappeIrIncidentCreate,
  CappeIrIncidentType,
  CappeIrLocation,
  CappeIrSeverity,
  CappeIrStatus,
  CappeIrWitness,
} from '../../../api/cappeIr'
import {
  FeatureOffPanel, formatLocation, inputCls, severityStyle, statusStyle, typeStyle,
  labelFor,
} from './shared'

const PAGE_SIZE = 50

type WitnessDraft = { name: string; contact: string }

type CreateDraft = {
  title: string
  description: string
  incident_type: '' | CappeIrIncidentType
  severity: CappeIrSeverity
  occurred_at: string // datetime-local value
  location_id: string
  reported_by_name: string
  reported_by_email: string
  corrective_actions: string
  witnesses: WitnessDraft[]
}

function nowLocalInput(): string {
  const d = new Date()
  d.setSeconds(0, 0)
  return new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
}

function blankDraft(defaultLocationId: string): CreateDraft {
  return {
    title: '', description: '', incident_type: '', severity: 'medium',
    occurred_at: nowLocalInput(), location_id: defaultLocationId,
    reported_by_name: '', reported_by_email: '', corrective_actions: '', witnesses: [],
  }
}

type LocationDraft = { name: string; address: string; city: string; state: string; zipcode: string }

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full border px-2.5 py-1 text-xs font-medium transition-colors ${
        active
          ? 'border-lime-400/40 bg-lime-400/10 text-lime-300'
          : 'border-zinc-700 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'
      }`}
    >
      {children}
    </button>
  )
}

export default function Incidents() {
  const { account, loading: meLoading } = useCappeMe()
  const featureOn = account?.matcha_features?.incidents === true

  const [incidents, setIncidents] = useState<CappeIrIncident[] | null>(null)
  const [total, setTotal] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [featureOff, setFeatureOff] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)

  // Filters
  const [status, setStatus] = useState<'' | CappeIrStatus>('')
  const [severity, setSeverity] = useState<'' | CappeIrSeverity>('')
  const [type, setType] = useState<'' | CappeIrIncidentType>('')
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')

  // Locations + create form
  const [locations, setLocations] = useState<CappeIrLocation[] | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [draft, setDraft] = useState<CreateDraft>(blankDraft(''))
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [showAddLocation, setShowAddLocation] = useState(false)
  const [locDraft, setLocDraft] = useState<LocationDraft>({ name: '', address: '', city: '', state: '', zipcode: '' })
  const [savingLocation, setSavingLocation] = useState(false)

  // Debounce the search box into the applied filter.
  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput.trim()), 400)
    return () => clearTimeout(t)
  }, [searchInput])

  const filters = useMemo(
    () => ({
      status: status || undefined,
      severity: severity || undefined,
      incident_type: type || undefined,
      search: search || undefined,
    }),
    [status, severity, type, search],
  )

  useEffect(() => {
    if (meLoading || !featureOn) return
    let cancelled = false
    setIncidents(null)
    cappeIr.listIncidents({ ...filters, limit: PAGE_SIZE, offset: 0 })
      .then((res) => {
        if (cancelled) return
        setIncidents(res.incidents)
        setTotal(res.total)
      })
      .catch((e) => {
        if (cancelled) return
        if (isIrFeatureDisabledError(e)) setFeatureOff(true)
        else setError(e instanceof Error ? e.message : 'Failed to load incidents')
      })
    return () => { cancelled = true }
  }, [meLoading, featureOn, filters])

  useEffect(() => {
    if (meLoading || !featureOn) return
    cappeIr.listLocations()
      .then(setLocations)
      .catch((e) => {
        if (isIrFeatureDisabledError(e)) setFeatureOff(true)
      })
  }, [meLoading, featureOn])

  async function loadMore() {
    if (!incidents) return
    setLoadingMore(true)
    try {
      const res = await cappeIr.listIncidents({ ...filters, limit: PAGE_SIZE, offset: incidents.length })
      setIncidents([...incidents, ...res.incidents])
      setTotal(res.total)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load more')
    } finally {
      setLoadingMore(false)
    }
  }

  function openCreate() {
    setDraft(blankDraft(locations?.[0]?.id ?? ''))
    setFormError(null)
    setShowAddLocation(false)
    setShowCreate(true)
  }

  async function saveLocation() {
    if (!locDraft.city.trim() || !locDraft.zipcode.trim() || locDraft.state.trim().length !== 2) {
      setFormError('Location needs a city, a 2-letter state, and a zip code.')
      return
    }
    setSavingLocation(true)
    setFormError(null)
    try {
      const created = await cappeIr.createLocation({
        name: locDraft.name.trim() || null,
        address: locDraft.address.trim() || null,
        city: locDraft.city.trim(),
        state: locDraft.state.trim().toUpperCase(),
        zipcode: locDraft.zipcode.trim(),
      })
      setLocations((ls) => [...(ls ?? []), created])
      setDraft((d) => ({ ...d, location_id: created.id }))
      setLocDraft({ name: '', address: '', city: '', state: '', zipcode: '' })
      setShowAddLocation(false)
    } catch (e) {
      setFormError(e instanceof Error ? e.message : 'Failed to add location')
    } finally {
      setSavingLocation(false)
    }
  }

  async function removeLocation(id: string) {
    if (!window.confirm('Remove this location? Existing incidents keep their location.')) return
    try {
      await cappeIr.deleteLocation(id)
      setLocations((ls) => (ls ?? []).filter((l) => l.id !== id))
      setDraft((d) => (d.location_id === id ? { ...d, location_id: '' } : d))
    } catch (e) {
      setFormError(e instanceof Error ? e.message : 'Failed to remove location')
    }
  }

  async function submitIncident() {
    if (!draft.description.trim()) { setFormError('A description is required.'); return }
    if (!draft.reported_by_name.trim()) { setFormError('Reporter name is required.'); return }
    if (!draft.location_id) { setFormError('Pick a location (add one first if the list is empty).'); return }
    if (!draft.occurred_at) { setFormError('When did this occur?'); return }
    setSaving(true)
    setFormError(null)
    const witnesses: CappeIrWitness[] = draft.witnesses
      .filter((w) => w.name.trim())
      .map((w) => ({ name: w.name.trim(), contact: w.contact.trim() || null }))
    const payload: CappeIrIncidentCreate = {
      description: draft.description.trim(),
      occurred_at: new Date(draft.occurred_at).toISOString(),
      reported_by_name: draft.reported_by_name.trim(),
      location_id: draft.location_id,
      severity: draft.severity,
      ...(draft.title.trim() ? { title: draft.title.trim() } : {}),
      ...(draft.incident_type ? { incident_type: draft.incident_type } : {}),
      ...(draft.reported_by_email.trim() ? { reported_by_email: draft.reported_by_email.trim() } : {}),
      ...(witnesses.length ? { witnesses } : {}),
      ...(draft.corrective_actions.trim() ? { corrective_actions: draft.corrective_actions.trim() } : {}),
    }
    try {
      const created = await cappeIr.createIncident(payload)
      setShowCreate(false)
      setIncidents((xs) => [created, ...(xs ?? [])])
      setTotal((t) => t + 1)
    } catch (e) {
      setFormError(e instanceof Error ? e.message : 'Failed to report incident')
    } finally {
      setSaving(false)
    }
  }

  if (meLoading) {
    return (
      <SurfaceShell title="Incidents">
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>
      </SurfaceShell>
    )
  }

  if (!featureOn || featureOff) {
    return (
      <SurfaceShell title="Incidents" subtitle="Safety & workplace incident reporting.">
        <FeatureOffPanel />
      </SurfaceShell>
    )
  }

  const noLocations = locations !== null && locations.length === 0

  const actions = !showCreate ? (
    <button onClick={openCreate} className="flex items-center gap-1.5 rounded-lg bg-lime-500 px-3 py-2 text-sm font-semibold text-zinc-950 hover:bg-lime-400">
      <Plus className="h-4 w-4" /> Report incident
    </button>
  ) : undefined

  return (
    <SurfaceShell title="Incidents" subtitle="Report and track safety & workplace incidents across your locations." actions={actions}>
      {error && <p className="mb-4 text-sm text-red-400">{error}</p>}

      {/* Create form */}
      {showCreate && (
        <div className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-zinc-100">Report an incident</h2>
            <button onClick={() => setShowCreate(false)} className="text-zinc-500 hover:text-zinc-200"><X className="h-5 w-5" /></button>
          </div>

          {formError && <p className="mb-3 text-sm text-red-400">{formError}</p>}

          {/* First-run: no locations yet — incidents must reference one. */}
          {noLocations && !showAddLocation && (
            <div className="mb-4 rounded-xl border border-dashed border-zinc-700 p-4 text-center text-sm text-zinc-400">
              <MapPin className="mx-auto mb-1.5 h-6 w-6 text-zinc-500" />
              Incidents are tied to a location, and you don't have one yet.
              <div>
                <button onClick={() => setShowAddLocation(true)} className="mt-2 inline-flex items-center gap-1.5 text-sm font-semibold text-lime-400 hover:text-lime-300">
                  <Plus className="h-4 w-4" /> Add your first location
                </button>
              </div>
            </div>
          )}

          {showAddLocation && (
            <div className="mb-4 rounded-xl border border-zinc-800 bg-zinc-950 p-4">
              <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-zinc-400">New location</div>
              <div className="grid gap-3 sm:grid-cols-2">
                <input value={locDraft.name} onChange={(e) => setLocDraft((d) => ({ ...d, name: e.target.value }))} placeholder="Name (optional)" className={inputCls} />
                <input value={locDraft.address} onChange={(e) => setLocDraft((d) => ({ ...d, address: e.target.value }))} placeholder="Street address (optional)" className={inputCls} />
              </div>
              <div className="mt-3 grid gap-3 sm:grid-cols-3">
                <input value={locDraft.city} onChange={(e) => setLocDraft((d) => ({ ...d, city: e.target.value }))} placeholder="City" className={inputCls} />
                <input value={locDraft.state} onChange={(e) => setLocDraft((d) => ({ ...d, state: e.target.value }))} placeholder="State (e.g. CA)" maxLength={2} className={inputCls} />
                <input value={locDraft.zipcode} onChange={(e) => setLocDraft((d) => ({ ...d, zipcode: e.target.value }))} placeholder="Zip code" className={inputCls} />
              </div>
              <div className="mt-3 flex justify-end gap-2">
                <button onClick={() => setShowAddLocation(false)} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800">Cancel</button>
                <button onClick={saveLocation} disabled={savingLocation} className="flex items-center gap-1.5 rounded-lg bg-lime-500 px-3 py-1.5 text-xs font-semibold text-zinc-950 hover:bg-lime-400 disabled:opacity-60">
                  {savingLocation ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Save location
                </button>
              </div>
            </div>
          )}

          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-zinc-300">What happened? <span className="text-red-400">*</span></label>
              <textarea value={draft.description} onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))} rows={4} placeholder="Describe the incident in as much detail as you can." className={inputCls} />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-sm font-medium text-zinc-300">Title <span className="text-zinc-500">(optional — inferred if blank)</span></label>
                <input value={draft.title} onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))} placeholder="Short summary" className={inputCls} />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-zinc-300">When did it occur? <span className="text-red-400">*</span></label>
                <input type="datetime-local" value={draft.occurred_at} onChange={(e) => setDraft((d) => ({ ...d, occurred_at: e.target.value }))} className={inputCls} />
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <div>
                <label className="mb-1 block text-sm font-medium text-zinc-300">Location <span className="text-red-400">*</span></label>
                <div className="flex items-center gap-1.5">
                  <select value={draft.location_id} onChange={(e) => setDraft((d) => ({ ...d, location_id: e.target.value }))} className={inputCls}>
                    <option value="">Select…</option>
                    {(locations ?? []).map((l) => (
                      <option key={l.id} value={l.id}>{formatLocation(l)}</option>
                    ))}
                  </select>
                  {!noLocations && (
                    <button onClick={() => setShowAddLocation((v) => !v)} title="Add a location" className="rounded-lg border border-zinc-700 p-2 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200">
                      <Plus className="h-4 w-4" />
                    </button>
                  )}
                  {draft.location_id && (locations ?? []).length > 1 && (
                    <button onClick={() => removeLocation(draft.location_id)} title="Remove this location" className="rounded-lg border border-zinc-700 p-2 text-zinc-500 hover:bg-zinc-800 hover:text-red-400">
                      <Trash2 className="h-4 w-4" />
                    </button>
                  )}
                </div>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-zinc-300">Type <span className="text-zinc-500">(optional)</span></label>
                <select value={draft.incident_type} onChange={(e) => setDraft((d) => ({ ...d, incident_type: e.target.value as CreateDraft['incident_type'] }))} className={inputCls}>
                  <option value="">Auto-classify</option>
                  {CAPPE_IR_INCIDENT_TYPES.map((t) => <option key={t} value={t}>{labelFor(t)}</option>)}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-zinc-300">Severity</label>
                <select value={draft.severity} onChange={(e) => setDraft((d) => ({ ...d, severity: e.target.value as CappeIrSeverity }))} className={inputCls}>
                  {CAPPE_IR_SEVERITIES.map((s) => <option key={s} value={s}>{labelFor(s)}</option>)}
                </select>
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-sm font-medium text-zinc-300">Reported by <span className="text-red-400">*</span></label>
                <input value={draft.reported_by_name} onChange={(e) => setDraft((d) => ({ ...d, reported_by_name: e.target.value }))} placeholder="Full name" className={inputCls} />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-zinc-300">Reporter email <span className="text-zinc-500">(optional)</span></label>
                <input type="email" value={draft.reported_by_email} onChange={(e) => setDraft((d) => ({ ...d, reported_by_email: e.target.value }))} placeholder="name@business.com" className={inputCls} />
              </div>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-zinc-300">Witnesses <span className="text-zinc-500">(optional)</span></label>
              <div className="space-y-1.5">
                {draft.witnesses.map((w, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <input value={w.name} onChange={(e) => setDraft((d) => ({ ...d, witnesses: d.witnesses.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)) }))} placeholder="Witness name" className={inputCls} />
                    <input value={w.contact} onChange={(e) => setDraft((d) => ({ ...d, witnesses: d.witnesses.map((x, j) => (j === i ? { ...x, contact: e.target.value } : x)) }))} placeholder="Contact (optional)" className={inputCls} />
                    <button onClick={() => setDraft((d) => ({ ...d, witnesses: d.witnesses.filter((_, j) => j !== i) }))} className="text-zinc-500 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
                  </div>
                ))}
              </div>
              <button onClick={() => setDraft((d) => ({ ...d, witnesses: [...d.witnesses, { name: '', contact: '' }] }))} className="mt-1.5 inline-flex items-center gap-1 text-xs font-semibold text-lime-400 hover:text-lime-300">
                <Plus className="h-3.5 w-3.5" /> Add witness
              </button>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-zinc-300">Recommended next steps <span className="text-zinc-500">(optional)</span></label>
              <textarea value={draft.corrective_actions} onChange={(e) => setDraft((d) => ({ ...d, corrective_actions: e.target.value }))} rows={2} placeholder="Anything that should happen next." className={inputCls} />
            </div>
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowCreate(false)} className="rounded-lg border border-zinc-700 px-4 py-2 text-sm font-medium text-zinc-300 hover:bg-zinc-800">Cancel</button>
              <button onClick={submitIncident} disabled={saving || noLocations} className="flex items-center gap-2 rounded-lg bg-lime-500 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-lime-400 disabled:opacity-60">
                {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} Submit report
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="mb-4 space-y-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
          <input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search incidents…"
            className={`${inputCls} pl-9`}
          />
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-600">Status</span>
          <Chip active={status === ''} onClick={() => setStatus('')}>All</Chip>
          {CAPPE_IR_STATUSES.map((s) => (
            <Chip key={s} active={status === s} onClick={() => setStatus(status === s ? '' : s)}>{labelFor(s)}</Chip>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-600">Severity</span>
          <Chip active={severity === ''} onClick={() => setSeverity('')}>All</Chip>
          {CAPPE_IR_SEVERITIES.map((s) => (
            <Chip key={s} active={severity === s} onClick={() => setSeverity(severity === s ? '' : s)}>{labelFor(s)}</Chip>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-600">Type</span>
          <Chip active={type === ''} onClick={() => setType('')}>All</Chip>
          {CAPPE_IR_INCIDENT_TYPES.map((t) => (
            <Chip key={t} active={type === t} onClick={() => setType(type === t ? '' : t)}>{labelFor(t)}</Chip>
          ))}
        </div>
      </div>

      {/* List */}
      {incidents === null ? (
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>
      ) : incidents.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-zinc-700 py-12 text-center text-sm text-zinc-500">
          <ShieldAlert className="mx-auto mb-2 h-7 w-7 text-zinc-300" />
          {status || severity || type || search ? 'No incidents match these filters.' : 'No incidents reported yet.'}
          {!showCreate && !(status || severity || type || search) && (
            <div>
              <button onClick={openCreate} className="mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-lime-400 hover:text-lime-300">
                <Plus className="h-4 w-4" /> Report your first incident
              </button>
            </div>
          )}
        </div>
      ) : (
        <>
          <div className="divide-y divide-zinc-800 rounded-2xl border border-zinc-800 bg-zinc-900">
            {incidents.map((inc) => (
              <Link key={inc.id} to={`/cappe/incidents/${inc.id}`} className="flex items-center gap-4 px-5 py-3.5 transition-colors hover:bg-zinc-800/50">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="shrink-0 font-mono text-xs text-zinc-500">{inc.incident_number}</span>
                    <span className="truncate text-sm font-medium text-zinc-100">{inc.title}</span>
                  </div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-zinc-500">
                    <span>{new Date(inc.occurred_at).toLocaleString()}</span>
                    {(inc.location_name || inc.location) && (
                      <span className="inline-flex items-center gap-1"><MapPin className="h-3 w-3" />{inc.location_name || inc.location}</span>
                    )}
                    {inc.document_count > 0 && (
                      <span className="inline-flex items-center gap-1"><FileText className="h-3 w-3" />{inc.document_count}</span>
                    )}
                  </div>
                </div>
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${typeStyle[inc.incident_type]}`}>{labelFor(inc.incident_type)}</span>
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${severityStyle[inc.severity]}`}>{inc.severity}</span>
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${statusStyle[inc.status]}`}>{labelFor(inc.status)}</span>
              </Link>
            ))}
          </div>
          <div className="mt-3 flex items-center justify-between text-xs text-zinc-500">
            <span>{incidents.length} of {total}</span>
            {incidents.length < total && (
              <button onClick={loadMore} disabled={loadingMore} className="flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-60">
                {loadingMore && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Load more
              </button>
            )}
          </div>
        </>
      )}
    </SurfaceShell>
  )
}
