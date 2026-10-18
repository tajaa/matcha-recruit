import { AdminButton } from '../../AdminUI'
import { Loader2 } from 'lucide-react'

import { type OnboardingSessionDetail } from '../../../../api/admin/adminOnboarding'

// True when the AI scope expansion came back essentially blank — no
// NAICS sector and no items in any of the four lists. Means Gemini
// either refused to infer or returned malformed JSON that fell back
// to the route's empty-AIScope() default. Frontend uses this to swap
// the "Check our database" CTA for a "re-run expansion" prompt.


// ── Shared ──────────────────────────────────────────────────────────────

export type StepProps = {
  session: OnboardingSessionDetail
  onUpdated: (s: OnboardingSessionDetail) => void
  onNext: () => void
}



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
    <AdminButton
      onClick={onClick}
      disabled={disabled || busy}
      className="gap-2 h-10 hover:opacity-90 disabled:opacity-50" variant="primary"
    >
      {busy && <Loader2 className="w-4 h-4 animate-spin" />}
      {children}
    </AdminButton>
  )
}

export function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <label className="block text-[11px] text-zinc-400 mb-1">
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
