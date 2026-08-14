import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useMe } from '../../hooks/useMe'
import { UpgradeUpsellCard } from './UpgradeUpsellCard'

type Props = {
  /** Company feature flag (`enabled_features.<name>`) required to view children.
   *  Mutually exclusive with `anyOf` — provide one or the other. */
  feature?: string
  /** Admit the page if the company has ANY of these flags (e.g. a Pro flag OR
   *  its lite-tier counterpart). Takes precedence over `feature` when present. */
  anyOf?: string[]
  /** Page label used for the upsell title + lead-source tag. */
  label: string
  children: ReactNode
  /** Optional one-line pitch describing what the feature unlocks. */
  pitch?: string
  /** Optional bullets of unlocked capabilities. */
  bullets?: string[]
  /** Platform admins bypass this client-side gate when the backend admits them. */
  allowPlatformAdmin?: boolean
}

/**
 * Wraps a page so URL-hopping by a Cap-tier user (or any company without
 * the feature flag) lands on the in-app upsell card instead of an empty
 * page or backend 403. While `useMe` is still loading we render nothing to
 * avoid a flash of upsell on legitimate full-tier users.
 *
 * On a denial, we perform one revalidation before showing the upsell. This
 * covers the case where an admin or webhook flipped the company's feature
 * flags while the current SPA session still holds the previous profile.
 */
export function FeatureGate({ feature, anyOf, label, children, pitch, bullets, allowPlatformAdmin = false }: Props) {
  const { me, hasFeature, loading, refresh } = useMe()
  const allowed = (allowPlatformAdmin && me?.user.role === 'admin') ||
    (anyOf ? anyOf.some((f) => hasFeature(f)) : hasFeature(feature ?? ''))
  const sourceFlag = feature ?? anyOf?.[0] ?? 'unknown'
  const refreshAttempted = useRef(false)
  const [revalidating, setRevalidating] = useState(false)

  useEffect(() => {
    if (loading || allowed || refreshAttempted.current) return
    refreshAttempted.current = true
    setRevalidating(true)
    void refresh().finally(() => setRevalidating(false))
  }, [loading, allowed, refresh])

  if (loading || revalidating || (!allowed && !refreshAttempted.current)) return null
  if (allowed) return <>{children}</>
  return (
    <div className="p-6">
      <UpgradeUpsellCard
        source={`feature_gate:${sourceFlag}`}
        title={`Upgrade to unlock ${label}`}
        pitch={pitch ?? `${label} is part of Matcha Platform. Talk to our team about adding it to your account.`}
        bullets={bullets}
        variant="page"
      />
    </div>
  )
}
