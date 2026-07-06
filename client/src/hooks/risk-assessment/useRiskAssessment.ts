import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../../api/client'
import type { RiskAssessment, AdminCompany } from '../../types/risk-assessment'
import { useMe } from '../useMe'

export function useRiskAssessment() {
  const [assessment, setAssessment] = useState<RiskAssessment | null>(null)
  const [loading, setLoading] = useState(true)
  const [noSnapshot, setNoSnapshot] = useState(false)

  // Role comes from the central auth state, not a hand-decoded JWT.
  const { me, loading: meLoading } = useMe()
  const isAdmin = me?.user?.role === 'admin'
  const [companies, setCompanies] = useState<AdminCompany[]>([])
  const [selectedCompanyId, setSelectedCompanyId] = useState<string | null>(null)
  const [running, setRunning] = useState(false)

  const qs = isAdmin && selectedCompanyId ? `?company_id=${selectedCompanyId}` : ''

  // Fetch admin companies
  useEffect(() => {
    if (!isAdmin) return
    api.get<{ registrations: AdminCompany[] }>('/admin/business-registrations')
      .then((res) => {
        setCompanies(res.registrations)
        if (res.registrations.length > 0) {
          setSelectedCompanyId((prev) => prev ?? res.registrations[0].id)
        }
      })
      .catch(() => {})
  }, [isAdmin])

  // Drops out-of-order snapshot responses when the admin company switcher
  // changes selection while an older fetch is still in flight.
  const reqId = useRef(0)
  useEffect(() => () => { reqId.current++ }, [])

  const fetchSnapshot = useCallback(() => {
    if (meLoading) return
    if (isAdmin && !selectedCompanyId) return
    const q = isAdmin && selectedCompanyId ? `?company_id=${selectedCompanyId}` : ''
    const id = ++reqId.current
    setLoading(true)
    setNoSnapshot(false)
    api.get<RiskAssessment>(`/risk-assessment${q}`)
      .then((res) => { if (id === reqId.current) setAssessment(res) })
      .catch((e) => {
        if (id !== reqId.current) return
        if (e instanceof ApiError && e.status === 404) setNoSnapshot(true)
      })
      .finally(() => { if (id === reqId.current) setLoading(false) })
  }, [isAdmin, selectedCompanyId, meLoading])

  useEffect(() => { fetchSnapshot() }, [fetchSnapshot])

  async function handleRunAssessment() {
    if (!selectedCompanyId) return
    setRunning(true)
    try {
      await api.post(`/risk-assessment/admin/run/${selectedCompanyId}`, {})
      fetchSnapshot()
    } finally {
      setRunning(false)
    }
  }

  return {
    assessment,
    loading,
    noSnapshot,
    isAdmin,
    companies,
    selectedCompanyId,
    setSelectedCompanyId,
    running,
    handleRunAssessment,
    qs,
    refetchSnapshot: fetchSnapshot,
  }
}
