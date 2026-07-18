import { useState } from 'react'
import { Link } from 'react-router-dom'

import { adminOnboarding } from '../../../../api/admin/adminOnboarding'
import { ErrorBox, PrimaryButton, type StepProps } from './_shared'

// ── Step 6: Finalize ───────────────────────────────────────────────────

export function Step6Review({ session, onUpdated }: StepProps) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [finalized, setFinalized] = useState<{
    company_id: string
    invite_token?: string | null
    scope_rows_written: number
    certifications_written: number
    licenses_written: number
  } | null>(null)

  async function finalize() {
    setBusy(true)
    setError(null)
    try {
      const res = await adminOnboarding.finalize(session.id)
      setFinalized(res)
      const refreshed = await adminOnboarding.getSession(session.id)
      onUpdated(refreshed)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Finalize failed')
    } finally {
      setBusy(false)
    }
  }

  const basics = session.basics
  const resolved = session.resolved_scope
  const ai = session.ai_scope

  return (
    <div className="max-w-3xl">
      <h2 className="text-base font-medium text-zinc-100 mb-1">Finalize</h2>
      <p className="text-sm text-zinc-400 mb-6">
        One last look before we write the scope manifest and issue the owner invite.
      </p>
      <ErrorBox message={error} />

      <SummaryRow label="Business" value={basics.business_name || '—'} />
      <SummaryRow label="Industry" value={`${basics.industry || '—'}${basics.specialty ? ` · ${basics.specialty}` : ''}`} />
      <SummaryRow label="Owner" value={basics.owner_email || '—'} />
      <SummaryRow label="Locations" value={`${session.locations.length} location${session.locations.length === 1 ? '' : 's'}`} />
      <SummaryRow label="Already covered" value={`${resolved?.existing.length ?? 0}`} />
      <SummaryRow label="Certifications" value={`${ai?.required_certifications.length ?? 0}`} />
      <SummaryRow label="Licenses" value={`${ai?.required_licenses.length ?? 0}`} />

      <div className="mt-6">
        {finalized ? (
          <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 p-4 text-sm text-emerald-200 space-y-1">
            <div className="font-medium">Gap analysis finalized.</div>
            <div>Scope rows written: {finalized.scope_rows_written}</div>
            <div>Certifications: {finalized.certifications_written} · Licenses: {finalized.licenses_written}</div>
            {finalized.invite_token && (
              <div className="pt-2 border-t border-emerald-500/20">
                <div className="text-[11px] uppercase tracking-wider text-emerald-300 mb-0.5">
                  Owner invite token
                </div>
                <code className="text-xs text-zinc-100 break-all">{finalized.invite_token}</code>
              </div>
            )}
            <div className="pt-2 border-t border-emerald-500/20">
              <Link
                to={`/admin/gap-analysis/${session.id}/report`}
                className="text-sm text-emerald-300 hover:underline font-medium"
              >
                View full gap analysis →
              </Link>
            </div>
          </div>
        ) : (
          <PrimaryButton busy={busy} onClick={() => void finalize()}>
            Finalize onboarding
          </PrimaryButton>
        )}
      </div>
    </div>
  )
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center gap-4 py-1.5 border-b border-vsc-border last:border-b-0">
      <div className="w-44 text-[11px] uppercase tracking-wider text-zinc-500">{label}</div>
      <div className="text-sm text-zinc-200">{value}</div>
    </div>
  )
}
