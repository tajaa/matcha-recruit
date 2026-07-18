import { useState } from 'react'

import {
  adminOnboarding,
  type LocationInput,
} from '../../../../api/admin/adminOnboarding'
import { ALL_STATES, ErrorBox, FieldLabel, PrimaryButton, type StepProps } from './_shared'

// ── Step 3: Locations + create-company ─────────────────────────────────

export function Step3Locations({ session, onUpdated, onNext }: StepProps) {
  const [locations, setLocations] = useState<LocationInput[]>(
    session.locations.length ? session.locations : [{}],
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function update(idx: number, patch: Partial<LocationInput>) {
    setLocations((prev) => prev.map((l, i) => (i === idx ? { ...l, ...patch } : l)))
  }
  function add() {
    setLocations((prev) => [...prev, {}])
  }
  function remove(idx: number) {
    setLocations((prev) => prev.filter((_, i) => i !== idx))
  }

  async function save() {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const updated = await adminOnboarding.patchSession(session.id, {
        locations: { locations },
        step: 'scope',
      })
      // Provision the company + sentinel + per-location rows.
      await adminOnboarding.createCompany(session.id)
      const refreshed = await adminOnboarding.getSession(session.id)
      onUpdated(refreshed)
      // Step 3 ends with provisioning; advancing leads into Step 4 (scope).
      onNext()
      return updated
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-3xl">
      <h2 className="text-base font-medium text-zinc-100 mb-1">Locations</h2>
      <p className="text-sm text-zinc-400 mb-6">
        Add each physical location. State drives jurisdiction-specific scope. County / city refine it. A company-wide sentinel is added automatically for federal-only requirements.
      </p>
      <ErrorBox message={error} />

      <div className="space-y-3 mb-4">
        {locations.map((loc, idx) => (
          <div key={idx} className="rounded-md border border-vsc-border bg-vsc-panel p-3">
            <div className="grid grid-cols-12 gap-2 items-end">
              <div className="col-span-3">
                <FieldLabel>Name</FieldLabel>
                <input
                  value={loc.name || ''}
                  onChange={(e) => update(idx, { name: e.target.value })}
                  placeholder="Main"
                  className="w-full rounded-md bg-vsc-bg border border-vsc-border px-2 py-1.5 text-sm text-zinc-100 outline-none focus:border-emerald-500"
                />
              </div>
              <div className="col-span-3">
                <FieldLabel>City</FieldLabel>
                <input
                  value={loc.city || ''}
                  onChange={(e) => update(idx, { city: e.target.value })}
                  className="w-full rounded-md bg-vsc-bg border border-vsc-border px-2 py-1.5 text-sm text-zinc-100 outline-none focus:border-emerald-500"
                />
              </div>
              <div className="col-span-2">
                <FieldLabel>State</FieldLabel>
                <select
                  value={loc.state || ''}
                  onChange={(e) => update(idx, { state: e.target.value })}
                  className="w-full rounded-md bg-vsc-bg border border-vsc-border px-2 py-1.5 text-sm text-zinc-100 outline-none focus:border-emerald-500"
                >
                  <option value="">—</option>
                  {ALL_STATES.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
              <div className="col-span-2">
                <FieldLabel>County</FieldLabel>
                <input
                  value={loc.county || ''}
                  onChange={(e) => update(idx, { county: e.target.value })}
                  className="w-full rounded-md bg-vsc-bg border border-vsc-border px-2 py-1.5 text-sm text-zinc-100 outline-none focus:border-emerald-500"
                />
              </div>
              <div className="col-span-1">
                <FieldLabel>Zip</FieldLabel>
                <input
                  value={loc.zipcode || ''}
                  onChange={(e) => update(idx, { zipcode: e.target.value })}
                  className="w-full rounded-md bg-vsc-bg border border-vsc-border px-2 py-1.5 text-sm text-zinc-100 outline-none focus:border-emerald-500"
                />
              </div>
              <div className="col-span-1 flex justify-end">
                {locations.length > 1 && (
                  <button
                    onClick={() => remove(idx)}
                    className="text-zinc-500 hover:text-red-400 text-xs"
                  >
                    Remove
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={add}
          className="px-3 h-8 text-xs text-zinc-300 border border-vsc-border rounded-md hover:border-zinc-500"
        >
          + Add location
        </button>
        <div className="ml-auto">
          <PrimaryButton busy={busy} onClick={() => void save()}>
            Save + Provision company
          </PrimaryButton>
        </div>
      </div>
    </div>
  )
}
