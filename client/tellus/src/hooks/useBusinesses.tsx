import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { tellusApi } from '../api/tellusClient'
import type { BrandCapability, BusinessMembership } from '../api/types'
import { useAccount } from './useAccount'

type BusinessContextValue = {
  memberships: BusinessMembership[]
  loading: boolean
  refresh: () => Promise<void>
  membershipFor: (brandId: string) => BusinessMembership | null
  can: (brandId: string, capability: BrandCapability) => boolean
}

const Context = createContext<BusinessContextValue | null>(null)

export function BusinessProvider({ children }: { children: ReactNode }) {
  const { account } = useAccount()
  const [memberships, setMemberships] = useState<BusinessMembership[]>([])
  const [loading, setLoading] = useState(true)

  async function refresh() {
    if (!account) {
      setMemberships([])
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      setMemberships(await tellusApi.get<BusinessMembership[]>('/me/businesses'))
    } catch {
      setMemberships([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void refresh() }, [account?.id])

  const value: BusinessContextValue = {
    memberships,
    loading,
    refresh,
    membershipFor: (brandId) => memberships.find((item) => item.brand_id === brandId) ?? null,
    can: (brandId, capability) => {
      const membership = memberships.find((item) => item.brand_id === brandId)
      return membership?.status === 'active' && membership.plan_status === 'active'
        && membership.capabilities.includes(capability)
    },
  }
  return <Context.Provider value={value}>{children}</Context.Provider>
}

export function useBusinesses(): BusinessContextValue {
  const context = useContext(Context)
  if (!context) throw new Error('useBusinesses must be used within BusinessProvider')
  return context
}
