import { useEffect, useState, useCallback } from 'react'
import { api } from '../api/client'

export interface OnlineUser {
  id: string
  name: string
  email: string
  avatar_url: string | null
  last_active: string | null
}

const POLL_MS = 30_000

export function useOnlineUsers() {
  const [users, setUsers] = useState<OnlineUser[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const data = await api.get<OnlineUser[]>('/matcha-work/presence/online')
      setUsers(data)
    } catch {
      setUsers([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, POLL_MS)
    return () => clearInterval(id)
  }, [load])

  return { users, loading }
}
