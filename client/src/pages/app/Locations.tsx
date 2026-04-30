import { useEffect, useState } from 'react'
import { Loader2, MapPin, Plus, X } from 'lucide-react'
import { api } from '../../api/client'

type LocationRow = {
  id: string
  name: string | null
  address: string | null
  city: string
  state: string
  zipcode: string | null
  is_active: boolean
}

export default function Locations() {
  const [rows, setRows] = useState<LocationRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showAdd, setShowAdd] = useState(false)
  const [removing, setRemoving] = useState<string | null>(null)

  async function refresh() {
    try {
      const data = await api.get<LocationRow[]>('/ir-onboarding/locations?include_inactive=true')
      setRows(data || [])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load locations')
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  async function handleRemove(id: string) {
    if (!confirm('Deactivate this location? Past incidents will keep referencing it.')) return
    setRemoving(id)
    try {
      await api.delete<void>(`/ir-onboarding/locations/${id}`)
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to deactivate location')
    } finally {
      setRemoving(null)
    }
  }

  if (!rows) {
    return (
      <div className="flex items-center justify-center py-10">
        <Loader2 className="w-5 h-5 text-zinc-500 animate-spin" />
      </div>
    )
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-zinc-100">
            <MapPin className="w-5 h-5" />
            Locations
          </h1>
          <p className="text-sm text-zinc-500 mt-1">
            Sites, stores, or facilities your team operates. Required when submitting an incident.
          </p>
        </div>
        <button
          onClick={() => setShowAdd((v) => !v)}
          className="bg-emerald-700 hover:bg-emerald-600 text-white text-sm font-medium px-4 py-2 rounded transition-colors flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          {showAdd ? 'Close' : 'Add location'}
        </button>
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}

      {showAdd && <AddLocationForm onAdded={() => { setShowAdd(false); refresh() }} />}

      {rows.length === 0 && !showAdd && (
        <div className="text-sm text-zinc-500 bg-zinc-900 border border-zinc-800 rounded p-6 text-center">
          No locations yet. Add one to start submitting incidents.
        </div>
      )}

      {rows.length > 0 && (
        <ul className="divide-y divide-zinc-800 border border-zinc-800 rounded overflow-hidden">
          {rows.map((r) => (
            <li
              key={r.id}
              className={
                'flex items-center justify-between gap-3 px-4 py-3 ' +
                (r.is_active ? 'bg-zinc-950' : 'bg-zinc-900/40 text-zinc-500')
              }
            >
              <div>
                <div className="text-sm font-medium text-zinc-200">
                  {r.name || `${r.city}, ${r.state}`}
                  {!r.is_active && <span className="text-xs text-zinc-600 ml-2">(inactive)</span>}
                </div>
                <div className="text-xs text-zinc-500 mt-0.5">
                  {[r.address, r.city, r.state, r.zipcode].filter(Boolean).join(', ')}
                </div>
              </div>
              {r.is_active && (
                <button
                  onClick={() => handleRemove(r.id)}
                  disabled={removing === r.id}
                  className="text-zinc-500 hover:text-red-400 disabled:opacity-50"
                  title="Deactivate"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function AddLocationForm({ onAdded }: { onAdded: () => void }) {
  const [name, setName] = useState('')
  const [address, setAddress] = useState('')
  const [city, setCity] = useState('')
  const [state, setState] = useState('')
  const [zipcode, setZipcode] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!city || !state || !zipcode) return
    setSubmitting(true)
    setError(null)
    try {
      await api.post('/ir-onboarding/locations', {
        name: name.trim() || null,
        address: address.trim() || null,
        city: city.trim(),
        state: state.trim().toUpperCase(),
        zipcode: zipcode.trim(),
      })
      onAdded()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save location')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3 bg-zinc-900 border border-zinc-800 rounded p-4">
      <Field label="Location name" value={name} onChange={setName} optional />
      <Field label="Address" value={address} onChange={setAddress} optional />
      <div className="grid grid-cols-3 gap-3">
        <Field label="City" value={city} onChange={setCity} />
        <Field label="State" value={state} onChange={setState} maxLength={2} />
        <Field label="ZIP" value={zipcode} onChange={setZipcode} />
      </div>
      {error && <p className="text-sm text-red-400">{error}</p>}
      <button
        type="submit"
        disabled={submitting || !city || !state || !zipcode}
        className="bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded transition-colors flex items-center"
      >
        {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Save location'}
      </button>
    </form>
  )
}

function Field({
  label,
  value,
  onChange,
  optional,
  maxLength,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  optional?: boolean
  maxLength?: number
}) {
  return (
    <label className="block">
      <span className="text-xs text-zinc-400 uppercase tracking-wide">
        {label}
        {optional && <span className="text-zinc-600 normal-case ml-1">(optional)</span>}
      </span>
      <input
        type="text"
        value={value}
        maxLength={maxLength}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700"
      />
    </label>
  )
}
