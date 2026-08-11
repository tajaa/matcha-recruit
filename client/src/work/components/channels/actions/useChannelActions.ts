import { useCallback, useEffect, useState } from 'react'
import { getSharedChannelSocket } from '../../../api/channelSocket'
import { listChannelActions, type ChannelAction } from '../../../api/channelActions'

export function useChannelActions(channelId: string | undefined, enabled: boolean) {
  const [actions, setActions] = useState<ChannelAction[]>([])
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(async () => {
    if (!channelId || !enabled) {
      setActions([])
      return
    }
    setLoading(true)
    try {
      const response = await listChannelActions(channelId)
      setActions(response.actions)
    } catch {
      setActions([])
    } finally {
      setLoading(false)
    }
  }, [channelId, enabled])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    if (!channelId || !enabled) return
    const socket = getSharedChannelSocket()
    const onUpdate = (update: { channel_id: string }) => {
      if (update.channel_id === channelId) void refresh()
    }
    socket.addChannelActionListener(onUpdate)
    return () => socket.removeChannelActionListener(onUpdate)
  }, [channelId, enabled, refresh])

  return { actions, loading, refresh }
}
