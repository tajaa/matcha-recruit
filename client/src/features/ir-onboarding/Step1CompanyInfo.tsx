import { useEffect, useRef, useState } from 'react'
import { AlertCircle, Loader2, X } from 'lucide-react'
import { api } from '../../api/client'

type LocationRow = {
  id: string
  name: string | null
  city: string
  state: string
  zipcode: string | null
  is_active: boolean
}

export default function Step1CompanyInfo({ onDone }: { onDone: () => void }) {
  const [locations, setLocations] = useState<LocationRow[]>([])
  const [loading, setLoading] = useState(true)
  const [name, setName] = useState('Main Office')
  const [address, setAddress] = useState('')
  const [city, setCity] = useState('')
  const [state, setState] = useState('')
  const [zipcode, setZipcode] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [removing, setRemoving] = useState<string | null>(null)
  // Brief lockout after a successful add to prevent double-submits
  // (a likely cause of "second one not saved" reports — fast double-click
  // on Add fired two POSTs but only one persisted before the form reset).
  const submitLockRef = useRef(false)

  async function refresh() {
    try {
      const rows = await api.get<LocationRow[]>('/ir-onboarding/locations')
      setLocations((rows || []).filter((r) => r.is_active))
    } catch {
      /* ignore — first-load failure handled below */
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    if (!city || !state || !zipcode) return
    if (submitLockRef.current) return
    submitLockRef.current = true
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
      // Reset address-specific fields; keep `name` as a sensible default
      // for the next entry (most companies have one of each named site).
      setAddress('')
      setCity('')
      setState('')
      setZipcode('')
      setName('')
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save location')
    } finally {
      setSubmitting(false)
      // Brief debounce so a fast second click doesn't reach the network.
      setTimeout(() => { submitLockRef.current = false }, 500)
    }
  }

  async function handleRemove(id: string) {
    setRemoving(id)
    try {
      await api.delete<void>(`/ir-onboarding/locations/${id}`)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove location')
    } finally {
      setRemoving(null)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-10">
        <Loader2 className="w-5 h-5 text-zinc-500 animate-spin" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-zinc-100 mb-1">Add your locations</h2>
        <p className="text-sm text-zinc-400">
          Incidents are submitted per-location and notifications fan out to your business admins.
          Add every site, store, or facility you operate.
        </p>
      </div>

      {error && (
        <div className="flex items-start gap-2 bg-red-950/40 border border-red-900 text-red-300 rounded px-3 py-2.5">
          <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
          <div className="flex-1 text-sm">{error}</div>
          <button
            type="button"
            onClick={() => setError(null)}
            className="text-red-400 hover:text-red-200"
            aria-label="Dismiss"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {locations.length > 0 && (
        <ul className="space-y-2">
          {locations.map((l) => (
            <li
              key={l.id}
              className="flex items-center justify-between gap-3 bg-zinc-900 border border-zinc-800 rounded px-3 py-2"
            >
              <div className="text-sm text-zinc-200">
                <div className="font-medium">{l.name || `${l.city}, ${l.state}`}</div>
                <div className="text-xs text-zinc-500">
                  {[l.city, l.state, l.zipcode].filter(Boolean).join(', ')}
                </div>
              </div>
              <button
                type="button"
                onClick={() => handleRemove(l.id)}
                disabled={removing === l.id}
                className="text-zinc-500 hover:text-red-400 disabled:opacity-50"
                title="Remove location"
              >
                <X className="w-4 h-4" />
              </button>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={handleAdd} className="space-y-3 border-t border-zinc-800 pt-4">
        <Field label="Location name" value={name} onChange={setName} optional />
        <Field label="Address" value={address} onChange={setAddress} optional />
        <div className="grid grid-cols-3 gap-3">
          <Field label="City" value={city} onChange={setCity} />
          <Field label="State" value={state} onChange={setState} maxLength={2} />
          <Field label="ZIP" value={zipcode} onChange={setZipcode} />
        </div>
        <button
          type="submit"
          disabled={submitting || !city || !state || !zipcode}
          className="bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 text-zinc-100 text-sm font-medium px-4 py-2 rounded transition-colors flex items-center"
        >
          {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : '+ Add location'}
        </button>
      </form>

      <div className="space-y-1.5">
        <button
          type="button"
          onClick={onDone}
          disabled={locations.length === 0}
          className="bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white font-medium px-5 py-2 rounded transition-colors"
        >
          Continue
        </button>
        <p className="text-xs text-zinc-500">
          One location is enough to get started — you can add more later from Company Settings.
        </p>
      </div>
    </div>
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
        className="mt-1 w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700"
      />
    </label>
  )
}
