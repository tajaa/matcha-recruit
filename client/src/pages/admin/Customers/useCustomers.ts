import { useEffect, useMemo, useState } from 'react'
import { api } from '../../../api/client'
import { tierFromRegistration } from './helpers'
import type { Individual, Registration, Tab } from './types'

export function useCustomers() {
  const [tab, setTab] = useState<Tab>('all')
  const [search, setSearch] = useState('')
  const [registrations, setRegistrations] = useState<Registration[] | null>(null)
  const [individuals, setIndividuals] = useState<Individual[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [resetUrl, setResetUrl] = useState<{ email: string; url: string } | null>(null)

  async function refresh() {
    setBusy(true)
    try {
      const [regs, indis] = await Promise.all([
        api.get<{ registrations: Registration[]; total: number }>('/admin/business-registrations').catch(() => ({ registrations: [], total: 0 })),
        api.get<Individual[]>('/matcha-work/billing/admin/individuals').catch(() => []),
      ])
      setRegistrations(regs.registrations)
      setIndividuals(indis)
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => { refresh() }, [])

  const tabRows = useMemo(() => {
    if (tab === 'personal') return individuals
    if (!registrations) return null
    if (tab === 'all') return registrations
    return registrations.filter((r) => tierFromRegistration(r) === tab)
  }, [tab, registrations, individuals])

  const counts = useMemo(() => {
    const c = { all: 0, free: 0, lite: 0, x: 0, platform: 0, personal: individuals?.length ?? 0 }
    if (registrations) {
      c.all = registrations.length
      for (const r of registrations) {
        const t = tierFromRegistration(r)
        if (t !== 'personal') c[t] += 1
      }
    }
    return c
  }, [registrations, individuals])

  // Lifecycle quick-actions
  async function suspendUser(userId: string | null | undefined, currentlySuspended: boolean | undefined) {
    if (!userId) return
    const path = currentlySuspended ? 'unsuspend' : 'suspend'
    if (!currentlySuspended && !confirm('Suspend this user? They will be locked out.')) return
    try {
      await api.post(`/admin/users/${userId}/${path}`, {})
      await refresh()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed')
    }
  }

  async function passwordReset(userId: string | null | undefined, email: string) {
    if (!userId) return
    try {
      const res = await api.post<{ reset_url: string }>(`/admin/users/${userId}/password-reset`, {})
      try { await navigator.clipboard.writeText(res.reset_url) } catch {}
      setResetUrl({ email, url: res.reset_url })
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed')
    }
  }

  async function cancelSub(companyId: string, immediate: boolean) {
    if (!confirm(immediate ? 'Cancel subscription immediately?' : 'Cancel subscription at period end?')) return
    try {
      const qs = immediate ? '?immediate=true' : ''
      await api.post(`/admin/companies/${companyId}/cancel-subscription${qs}`, {})
      await refresh()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed')
    }
  }

  async function softDelete(companyId: string) {
    if (!confirm('Soft-delete? Customer is locked out, rows persist for audit.')) return
    try {
      await api.delete(`/admin/companies/${companyId}`)
      await refresh()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed')
    }
  }

  async function restore(companyId: string) {
    try {
      await api.post(`/admin/companies/${companyId}/restore`, {})
      await refresh()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed')
    }
  }

  return {
    tab,
    setTab,
    search,
    setSearch,
    registrations,
    individuals,
    busy,
    resetUrl,
    setResetUrl,
    refresh,
    tabRows,
    counts,
    suspendUser,
    passwordReset,
    cancelSub,
    softDelete,
    restore,
  }
}
