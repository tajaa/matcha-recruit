import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { api } from '../../api/client'

export default function Step1CompanyInfo({ onDone }: { onDone: () => void }) {
  const [name, setName] = useState('Main Office')
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
      onDone()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save location')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-zinc-100 mb-1">Add your first location</h2>
        <p className="text-sm text-zinc-400">Where do incidents occur? You can add more locations later.</p>
      </div>
      <Field label="Location name" value={name} onChange={setName} />
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
        className="bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white font-medium px-5 py-2 rounded transition-colors flex items-center"
      >
        {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Continue'}
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
        className="mt-1 w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700"
      />
    </label>
  )
}
