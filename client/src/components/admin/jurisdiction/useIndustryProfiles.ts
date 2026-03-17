import { useState, useCallback, useEffect } from 'react'
import { api } from '../../../api/client'
import type { IndustryProfile } from './types'

export function useIndustryProfiles() {
  const [profiles, setProfiles] = useState<IndustryProfile[]>([])
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      setProfiles(await api.get<IndustryProfile[]>('/admin/industry-profiles'))
    } catch {
      setProfiles([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const create = useCallback(async (data: Omit<IndustryProfile, 'id' | 'created_at' | 'updated_at'>) => {
    const profile = await api.post<IndustryProfile>('/admin/industry-profiles', data)
    setProfiles((prev) => [...prev, profile])
    return profile
  }, [])

  const update = useCallback(async (id: string, data: Partial<Omit<IndustryProfile, 'id' | 'created_at' | 'updated_at'>>) => {
    const profile = await api.put<IndustryProfile>(`/admin/industry-profiles/${id}`, data)
    setProfiles((prev) => prev.map((p) => (p.id === id ? profile : p)))
    return profile
  }, [])

  const remove = useCallback(async (id: string) => {
    await api.delete(`/admin/industry-profiles/${id}`)
    setProfiles((prev) => prev.filter((p) => p.id !== id))
  }, [])

  return { profiles, loading, create, update, remove, refresh }
}
