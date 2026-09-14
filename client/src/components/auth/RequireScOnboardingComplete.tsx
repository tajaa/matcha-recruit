import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useMe } from '../../hooks/useMe'
import { isCustomProductPending } from '../../utils/tier'

/** Keeps an activated S&C tenant in first-account setup until it commits. */
export default function RequireScOnboardingComplete({ children }: { children: ReactNode }) {
  const { me, loading } = useMe()
  const profile = me?.profile
  const needsSetup =
    me?.user.role === 'client'
    && profile?.product?.onboarding_kind === 'sc'
    && !isCustomProductPending(profile)
    && !profile.sc_onboarding_completed_at

  if (!loading && needsSetup) return <Navigate to="/sc/onboarding" replace />
  return <>{children}</>
}
