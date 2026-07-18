import { Loader2 } from 'lucide-react'

import { type AIScope, type OnboardingSessionDetail } from '../../../../api/admin/adminOnboarding'

// True when the AI scope expansion came back essentially blank — no
// NAICS sector and no items in any of the four lists. Means Gemini
// either refused to infer or returned malformed JSON that fell back
// to the route's empty-AIScope() default. Frontend uses this to swap
// the "Check our database" CTA for a "re-run expansion" prompt.
export function isScopeEmpty(s: AIScope | null | undefined): boolean {
  if (!s) return true
  return (
    !s.naics_sector
    && (s.compliance_categories?.length || 0) === 0
    && (s.required_certifications?.length || 0) === 0
    && (s.required_licenses?.length || 0) === 0
    && (s.applicable_jurisdictions?.length || 0) === 0
  )
}

// ── Shared ──────────────────────────────────────────────────────────────

export type StepProps = {
  session: OnboardingSessionDetail
  onUpdated: (s: OnboardingSessionDetail) => void
  onNext: () => void
}

export const ALL_STATES = [
  'AL','AK','AZ','AR','CA','CO','CT','DE','DC','FL','GA','HI','ID','IL','IN','IA',
  'KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM',
  'NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT','VA','WA',
  'WV','WI','WY',
]

export function PrimaryButton({
  busy,
  children,
  disabled,
  onClick,
}: {
  busy?: boolean
  children: React.ReactNode
  disabled?: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled || busy}
      className="inline-flex items-center gap-2 px-5 h-10 rounded-md bg-vsc-accent text-vsc-bg hover:opacity-90 text-sm font-medium disabled:opacity-50"
    >
      {busy && <Loader2 className="w-4 h-4 animate-spin" />}
      {children}
    </button>
  )
}

export function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <label className="block text-[11px] uppercase tracking-wider text-zinc-400 mb-1">
      {children}
    </label>
  )
}

export function ErrorBox({ message }: { message: string | null }) {
  if (!message) return null
  return (
    <div className="rounded-md border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-300 mb-4">
      {message}
    </div>
  )
}
