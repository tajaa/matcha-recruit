import { AdminSection, AdminInput, AdminSelect, AdminButton } from '../../AdminUI'
import { useState } from 'react'

import {
  adminOnboarding,
  type LocationInput,
} from '../../../../api/admin/adminOnboarding'
import { ErrorBox, FieldLabel, PrimaryButton, type StepProps } from './_shared'
import { ALL_STATES } from './helpers'

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
    <AdminSection title={<>Locations</>} description={<>Add each physical location. State drives jurisdiction-specific scope. County / city refine it. A company-wide sentinel is added automatically for federal-only requirements.</>}>
      <ErrorBox message={error} />

      <div className="space-y-3 mb-4">
        {locations.map((loc, idx) => (
          <div key={idx} className="rounded-md border border-vsc-border bg-vsc-panel p-3">
            <div className="grid grid-cols-12 gap-2 items-end">
              <div className="col-span-3">
                <FieldLabel>Name</FieldLabel>
                <AdminInput
                  value={loc.name || ''}
                  onChange={(e) => update(idx, { name: e.target.value })}
                  placeholder="Main"
                  className="bg-vsc-bg border-vsc-border"
                />
              </div>
              <div className="col-span-3">
                <FieldLabel>City</FieldLabel>
                <AdminInput
                  value={loc.city || ''}
                  onChange={(e) => update(idx, { city: e.target.value })}
                  className="bg-vsc-bg border-vsc-border"
                />
              </div>
              <div className="col-span-2">
                <FieldLabel>State</FieldLabel>
                <AdminSelect
                  value={loc.state || ''}
                  onChange={(e) => update(idx, { state: e.target.value })}
                  className="w-full bg-vsc-bg border-vsc-border"
                >
                  <option value="">—</option>
                  {ALL_STATES.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </AdminSelect>
              </div>
              <div className="col-span-2">
                <FieldLabel>County</FieldLabel>
                <AdminInput
                  value={loc.county || ''}
                  onChange={(e) => update(idx, { county: e.target.value })}
                  className="bg-vsc-bg border-vsc-border"
                />
              </div>
              <div className="col-span-1">
                <FieldLabel>Zip</FieldLabel>
                <AdminInput
                  value={loc.zipcode || ''}
                  onChange={(e) => update(idx, { zipcode: e.target.value })}
                  className="bg-vsc-bg border-vsc-border"
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
        <AdminButton
          onClick={add}
          className="h-8" variant="ghost"
        >
          + Add location
        </AdminButton>
        <div className="ml-auto">
          <PrimaryButton busy={busy} onClick={() => void save()}>
            Save + Provision company
          </PrimaryButton>
        </div>
      </div>
    </AdminSection>
  )
}
