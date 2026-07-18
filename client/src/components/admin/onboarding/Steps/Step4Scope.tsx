import { useState } from 'react'
import { Loader2 } from 'lucide-react'

import { adminOnboarding } from '../../../../api/admin/adminOnboarding'
import { ErrorBox, PrimaryButton, isScopeEmpty, type StepProps } from './_shared'

// ── Step 4: Scope (AI expand) ──────────────────────────────────────────

export function Step4Scope({ session, onUpdated, onNext }: StepProps) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const scope = session.ai_scope

  async function expand() {
    setBusy(true)
    setError(null)
    try {
      await adminOnboarding.expand(session.id)
      const refreshed = await adminOnboarding.getSession(session.id)
      onUpdated(refreshed)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Scope expansion failed')
    } finally {
      setBusy(false)
    }
  }

  async function resolve() {
    setBusy(true)
    setError(null)
    try {
      await adminOnboarding.resolve(session.id)
      const refreshed = await adminOnboarding.getSession(session.id)
      onUpdated(refreshed)
      onNext()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Coverage check failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-3xl">
      <h2 className="text-base font-medium text-zinc-100 mb-1">AI scope expansion</h2>
      <p className="text-sm text-zinc-400 mb-6">
        Gemini reads industry + specialty + locations and proposes compliance categories, certifications, and licenses. Next you'll see which ones we already have data for and which need new research.
      </p>
      <ErrorBox message={error} />

      {!scope ? (
        <PrimaryButton busy={busy} onClick={() => void expand()}>
          Run AI scope expansion
        </PrimaryButton>
      ) : (
        <>
          <div className="mb-4 text-xs text-zinc-400">
            NAICS sector: <span className="text-zinc-200">{scope.naics_sector || '—'}</span>
          </div>
          <ScopeList title="Compliance categories" items={scope.compliance_categories.map((c) => `${c.category_slug} · ${c.scope}`)} />
          <ScopeList title="Certifications" items={scope.required_certifications.map((c) => c.name)} />
          <ScopeList title="Licenses" items={scope.required_licenses.map((l) => l.name)} />
          <ScopeList title="Applicable jurisdictions" items={scope.applicable_jurisdictions.map((j) => `${j.state || 'US'}${j.county ? ` · ${j.county}` : ''}${j.city ? ` · ${j.city}` : ''}`)} />

          {isScopeEmpty(scope) ? (
            <div className="mt-2 mb-4 rounded border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-200">
              <div className="font-medium">AI couldn't infer scope from your inputs.</div>
              <div className="mt-1 text-amber-200/80">
                Try expanding the company description in Step 1 (industry, services, specialties) or re-run the expansion. If this keeps happening, the AI may be timing out.
              </div>
              <button
                onClick={() => void expand()}
                disabled={busy}
                className="mt-3 inline-flex items-center gap-2 px-3 h-9 text-xs rounded bg-amber-500/90 hover:bg-amber-500 text-zinc-950 disabled:opacity-50"
              >
                {busy && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                Re-run AI scope expansion
              </button>
            </div>
          ) : (
            <div className="mt-6 flex items-center gap-2">
              <PrimaryButton busy={busy} onClick={() => void resolve()}>
                Check our database
              </PrimaryButton>
              <button
                onClick={() => void expand()}
                disabled={busy}
                className="px-3 h-9 text-xs text-zinc-400 hover:text-zinc-100 disabled:opacity-50"
              >
                Re-run AI expand
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function ScopeList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="mb-4">
      <div className="text-[11px] uppercase tracking-wider text-zinc-500 mb-1">{title}</div>
      {items.length === 0 ? (
        <div className="text-sm text-zinc-600">— none —</div>
      ) : (
        <ul className="text-sm text-zinc-200 space-y-0.5">
          {items.map((i) => (
            <li key={i}>• {i}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
