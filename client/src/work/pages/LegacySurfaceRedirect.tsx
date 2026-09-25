import { useEffect, useState, type ReactNode } from 'react'
import { Navigate, useLocation, useParams } from 'react-router-dom'
import { getChannel } from '../api/channels'
import { resolveLegacyChannelTarget } from './legacyChannelTarget'

export function LegacySurfacePrefixRedirect({ fromPrefix, toPrefix }: { fromPrefix: string; toPrefix: string }) {
  const location = useLocation()
  const [toPath, toQuery] = toPrefix.split('?')
  const existingQuery = location.search.slice(1)
  const query = [toQuery, existingQuery].filter(Boolean).join('&')
  const target = `${location.pathname.replace(fromPrefix, toPath)}${query ? `?${query}` : ''}${location.hash}`
  return <Navigate to={target} replace />
}

export function LegacyInviteRedirect() {
  const { code } = useParams<{ code: string }>()
  return <Navigate to={code ? `/ops/channels/join/${code}` : '/ops/channels'} replace />
}

export default function LegacyChannelRedirect({ communityElement }: { communityElement?: ReactNode }) {
  const { channelId } = useParams<{ channelId: string }>()
  const location = useLocation()
  const [target, setTarget] = useState<string | null>(null)

  useEffect(() => {
    if (!channelId) return
    let cancelled = false
    getChannel(channelId)
      .then((channel) => {
        if (cancelled) return
        const query = location.search
        setTarget(resolveLegacyChannelTarget(channel, channelId, query) ?? '')
      })
      .catch(() => setTarget('/ops'))
    return () => { cancelled = true }
  }, [channelId, location.search])

  if (target === '') return <>{communityElement}</>
  return target ? <Navigate to={target} replace /> : <div className="p-6 text-sm text-w-dim">Opening channel...</div>
}
