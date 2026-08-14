import { useEffect, useState } from 'react'
import { Navigate, useLocation, useParams } from 'react-router-dom'
import { getChannel } from '../api/channels'

export function LegacyOpsRedirect({ fromPrefix, toPrefix }: { fromPrefix: string; toPrefix: string }) {
  const location = useLocation()
  const target = `${location.pathname.replace(fromPrefix, toPrefix)}${location.search}${location.hash}`
  return <Navigate to={target} replace />
}

export function LegacyInviteRedirect() {
  const { code } = useParams<{ code: string }>()
  return <Navigate to={code ? `/ops/channels/join/${code}` : '/ops/channels'} replace />
}

export default function LegacyChannelRedirect() {
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
        if (channel.channel_scope === 'project_discussion' && channel.project_id) {
          const suffix = query ? `${query}&tab=chat` : '?tab=chat'
          setTarget(`/work/projects/${channel.project_id}${suffix}`)
        } else if (channel.channel_scope === 'community') {
          setTarget(`/werk/channels/${channelId}${query}`)
        } else {
          setTarget(`/ops/channels/${channelId}${query}`)
        }
      })
      .catch(() => setTarget('/ops'))
    return () => { cancelled = true }
  }, [channelId, location.search])

  return target ? <Navigate to={target} replace /> : <div className="p-6 text-sm text-w-dim">Opening channel...</div>
}
