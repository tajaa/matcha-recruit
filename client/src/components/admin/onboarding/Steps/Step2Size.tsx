import { AdminSection, AdminInput } from '../../AdminUI'
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
    <AdminSection title={<>Headcount</>} description={<>Rough totals. Full HRIS / employee import is Phase 2 — we just need ballpark counts for scope decisions.</>}>
      <ErrorBox message={error} />

      <div className="grid grid-cols-3 gap-4 mb-6">
        <div>
          <FieldLabel>Full-time</FieldLabel>
          <AdminInput
            type="number" min={0} value={ft}
            onChange={(e) => setFt(parseInt(e.target.value) || 0)}
            className="bg-vsc-bg border-vsc-border"
          />
        </div>
        <div>
          <FieldLabel>Part-time</FieldLabel>
          <AdminInput
            type="number" min={0} value={pt}
            onChange={(e) => setPt(parseInt(e.target.value) || 0)}
            className="bg-vsc-bg border-vsc-border"
          />
        </div>
        <div>
          <FieldLabel>Contractor</FieldLabel>
          <AdminInput
            type="number" min={0} value={contractor}
            onChange={(e) => setContractor(parseInt(e.target.value) || 0)}
            className="bg-vsc-bg border-vsc-border"
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
    </AdminSection>
  )
}
