import { useEffect, type ReactNode } from 'react'
import { getMeCacheAgeMs, useMe } from '../hooks/useMe'
import { UpgradeUpsellCard } from './UpgradeUpsellCard'

const STALE_REVALIDATE_AFTER_MS = 60_000

type Props = {
  /** Company feature flag (`enabled_features.<name>`) required to view children. */
  feature: string
  /** Page label used for the upsell title + lead-source tag. */
  label: string
  children: ReactNode
  /** Optional one-line pitch describing what the feature unlocks. */
  pitch?: string
  /** Optional bullets of unlocked capabilities. */
  bullets?: string[]
}

/**
 * Wraps a page so URL-hopping by a Cap-tier user (or any company without
 * the feature flag) lands on the in-app upsell card instead of an empty
 * page or backend 403. While `useMe` is still loading we render nothing to
 * avoid a flash of upsell on legitimate full-tier users.
 *
 * On a denial, if the `useMe` cache is older than 60s we kick off a
 * background revalidation — covers the case where sales just flipped the
 * company's feature flags and the user URL-hops to the page in the same
 * session.
 */
export function FeatureGate({ feature, label, children, pitch, bullets }: Props) {
  const { hasFeature, loading, refresh } = useMe()
  const allowed = hasFeature(feature)

  useEffect(() => {
    if (!loading && !allowed && getMeCacheAgeMs() > STALE_REVALIDATE_AFTER_MS) {
      refresh()
    }
  }, [loading, allowed, refresh])

  if (loading) return null
  if (allowed) return <>{children}</>
  return (
    <div className="p-6">
      <UpgradeUpsellCard
        source={`feature_gate:${feature}`}
        title={`Upgrade to unlock ${label}`}
        pitch={pitch ?? `${label} is part of Matcha Platform. Talk to our team about adding it to your account.`}
        bullets={bullets}
        variant="page"
      />
    </div>
  )
}
