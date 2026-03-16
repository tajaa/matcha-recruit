import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { RiskAssessment, AdminCompany } from '../../types/risk-assessment'
import { decodeTokenRole } from '../../types/risk-assessment'

export function useRiskAssessment() {
  const [assessment, setAssessment] = useState<RiskAssessment | null>(null)
  const [loading, setLoading] = useState(true)
  const [noSnapshot, setNoSnapshot] = useState(false)

  const [isAdmin] = useState(() => decodeTokenRole() === 'admin')
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

  const fetchSnapshot = useCallback(() => {
    if (isAdmin && !selectedCompanyId) return
    const q = isAdmin && selectedCompanyId ? `?company_id=${selectedCompanyId}` : ''
    setLoading(true)
    setNoSnapshot(false)
    api.get<RiskAssessment>(`/risk-assessment${q}`)
      .then((res) => setAssessment(res))
      .catch((e: Error) => {
        if (e.message.includes('404')) setNoSnapshot(true)
      })
      .finally(() => setLoading(false))
  }, [isAdmin, selectedCompanyId])

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
