import { useEffect, useState, type ReactNode } from 'react'
import { Navigate, useLocation, useParams } from 'react-router-dom'
import { getChannel } from '../api/channels'

export function resolveLegacyChannelTarget(
  channel: { channel_scope?: 'operations' | 'project_discussion' | 'community'; project_id?: string | null },
  channelId: string,
  search: string,
): string | null {
  if (channel.channel_scope === 'project_discussion' && channel.project_id) {
    const suffix = search ? `${search}&tab=chat` : '?tab=chat'
    return `/work/projects/${channel.project_id}${suffix}`
  }
  if (channel.channel_scope === 'operations') {
    return `/ops/channels/${channelId}${search}`
  }
  // Community channels are valid in the business shell too. Returning null
  // tells the caller to render the local channel view instead of bouncing
  // between /work and /werk based on identity.
  return null
}

export function LegacyOpsRedirect({ fromPrefix, toPrefix }: { fromPrefix: string; toPrefix: string }) {
  const location = useLocation()
  const target = `${location.pathname.replace(fromPrefix, toPrefix)}${location.search}${location.hash}`
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
