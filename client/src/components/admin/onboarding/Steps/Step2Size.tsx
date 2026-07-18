import { useState } from 'react'

import {
  adminOnboarding,
  type SizePayload,
} from '../../../../api/admin/adminOnboarding'
import { ErrorBox, FieldLabel, PrimaryButton, type StepProps } from './_shared'

// ── Step 2: Size ────────────────────────────────────────────────────────

export function Step2Size({ session, onUpdated, onNext }: StepProps) {
  const initial = session.size as Partial<SizePayload>
  const [ft, setFt] = useState(initial.full_time ?? 0)
  const [pt, setPt] = useState(initial.part_time ?? 0)
  const [contractor, setContractor] = useState(initial.contractor ?? 0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function save(source: SizePayload['source']) {
    setBusy(true)
    setError(null)
    try {
      const payload: SizePayload = {
        full_time: ft,
        part_time: pt,
        contractor,
        unknown: 0,
        source,
      }
      const updated = await adminOnboarding.patchSession(session.id, {
        size: payload,
        step: 'locations',
      })
      onUpdated(updated)
      onNext()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-2xl">
      <h2 className="text-base font-medium text-zinc-100 mb-1">Headcount</h2>
      <p className="text-sm text-zinc-400 mb-6">
        Rough totals. Full HRIS / employee import is Phase 2 — we just need ballpark counts for scope decisions.
      </p>
      <ErrorBox message={error} />

      <div className="grid grid-cols-3 gap-4 mb-6">
        <div>
          <FieldLabel>Full-time</FieldLabel>
          <input
            type="number" min={0} value={ft}
            onChange={(e) => setFt(parseInt(e.target.value) || 0)}
            className="w-full rounded-md bg-vsc-bg border border-vsc-border px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500"
          />
        </div>
        <div>
          <FieldLabel>Part-time</FieldLabel>
          <input
            type="number" min={0} value={pt}
            onChange={(e) => setPt(parseInt(e.target.value) || 0)}
            className="w-full rounded-md bg-vsc-bg border border-vsc-border px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500"
          />
        </div>
        <div>
          <FieldLabel>Contractor</FieldLabel>
          <input
            type="number" min={0} value={contractor}
            onChange={(e) => setContractor(parseInt(e.target.value) || 0)}
            className="w-full rounded-md bg-vsc-bg border border-vsc-border px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500"
          />
        </div>
      </div>

      <div className="flex items-center gap-2">
        <PrimaryButton busy={busy} onClick={() => void save('manual')}>
          Save + Continue
        </PrimaryButton>
        <button
          onClick={() => void save('skipped')}
          disabled={busy}
          className="px-4 h-10 text-sm text-zinc-400 hover:text-zinc-100 disabled:opacity-50"
        >
          Skip
        </button>
      </div>
    </div>
  )
}
