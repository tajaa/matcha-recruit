import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { tellusApi, clearTellusTokens, getTellusToken, setTellusTokens } from '../api/tellusClient'
import type { TellusAccount, TokenResponse } from '../api/types'

interface AccountCtx {
  account: TellusAccount | null
  loading: boolean
  setSession: (t: TokenResponse) => void
  refreshAccount: () => Promise<void>
  logout: () => void
}

const Ctx = createContext<AccountCtx | null>(null)

export function AccountProvider({ children }: { children: ReactNode }) {
  const [account, setAccount] = useState<TellusAccount | null>(null)
  const [loading, setLoading] = useState(true)

  async function refreshAccount() {
    if (!getTellusToken()) { setAccount(null); setLoading(false); return }
    try {
      const me = await tellusApi.get<TellusAccount>('/auth/me')
      setAccount(me)
    } catch {
      setAccount(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void refreshAccount() }, [])

  function setSession(t: TokenResponse) {
    setTellusTokens(t.access_token, t.refresh_token)
    setAccount(t.account)
    setLoading(false)
  }

  function logout() {
    tellusApi.post('/auth/logout').catch(() => {})
    clearTellusTokens()
    setAccount(null)
    window.location.href = '/tellus/login'
  }

  return (
    <Ctx.Provider value={{ account, loading, setSession, refreshAccount, logout }}>
      {children}
    </Ctx.Provider>
  )
}

export function useAccount(): AccountCtx {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useAccount must be used within AccountProvider')
  return ctx
}
