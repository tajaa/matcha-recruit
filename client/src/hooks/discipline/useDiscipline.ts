import { useCallback, useEffect, useState } from 'react'
import {
  disciplineApi,
  type DisciplineRecord,
  type DisciplineStatus,
  type DisciplineRecommendation,
  type DisciplineRecommendInput,
  type DisciplineIssueInput,
  type DisciplinePolicy,
  type DisciplineAuditEntry,
} from '../../api/discipline'

export function useDisciplineList(initialStatus: DisciplineStatus | undefined = undefined) {
  const [records, setRecords] = useState<DisciplineRecord[]>([])
  const [status, setStatus] = useState<DisciplineStatus | undefined>(initialStatus)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const refetch = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const rows = await disciplineApi.list(status)
      setRecords(rows)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load discipline records')
    } finally {
      setLoading(false)
    }
  }, [status])

  useEffect(() => { refetch() }, [refetch])

  return { records, status, setStatus, loading, error, refetch }
}

export function useDisciplineRecord(recordId: string | undefined) {
  const [record, setRecord] = useState<DisciplineRecord | null>(null)
  const [auditLog, setAuditLog] = useState<DisciplineAuditEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const refetch = useCallback(async () => {
    if (!recordId) return
    setLoading(true)
    setError('')
    try {
      const [r, log] = await Promise.all([
        disciplineApi.get(recordId),
        disciplineApi.auditLog(recordId).catch(() => [] as DisciplineAuditEntry[]),
      ])
      setRecord(r)
      setAuditLog(log)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load discipline record')
    } finally {
      setLoading(false)
    }
  }, [recordId])

  useEffect(() => { refetch() }, [refetch])

  const markMeetingHeld = useCallback(async () => {
    if (!recordId) return
    const updated = await disciplineApi.markMeetingHeld(recordId)
    setRecord(updated)
    await refetch()
    return updated
  }, [recordId, refetch])

  const requestSignature = useCallback(async () => {
    if (!recordId) return
    const updated = await disciplineApi.requestSignature(recordId)
    setRecord(updated)
    await refetch()
    return updated
  }, [recordId, refetch])

  const refuse = useCallback(async (notes: string) => {
    if (!recordId) return
    const updated = await disciplineApi.refuse(recordId, notes)
    setRecord(updated)
    await refetch()
    return updated
  }, [recordId, refetch])

  const uploadPhysical = useCallback(async (file: File) => {
    if (!recordId) return
    const updated = await disciplineApi.uploadPhysical(recordId, file)
    setRecord(updated)
    await refetch()
    return updated
  }, [recordId, refetch])

  const downloadLetter = useCallback(async () => {
    if (!recordId) return
    await disciplineApi.downloadLetter(recordId)
  }, [recordId])

  return {
    record,
    auditLog,
    loading,
    error,
    refetch,
    markMeetingHeld,
    requestSignature,
    refuse,
    uploadPhysical,
    downloadLetter,
  }
}

export function useDisciplineRecommendation() {
  const [recommendation, setRecommendation] = useState<DisciplineRecommendation | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const recommend = useCallback(async (input: DisciplineRecommendInput) => {
    setLoading(true)
    setError('')
    try {
      const r = await disciplineApi.recommend(input)
      setRecommendation(r)
      return r
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch recommendation')
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  const issue = useCallback(async (input: DisciplineIssueInput) => {
    return await disciplineApi.issue(input)
  }, [])

  const reset = useCallback(() => {
    setRecommendation(null)
    setError('')
  }, [])

  return { recommendation, recommend, issue, reset, loading, error }
}

export function useDisciplinePolicies() {
  const [policies, setPolicies] = useState<DisciplinePolicy[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const refetch = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const rows = await disciplineApi.listPolicies()
      setPolicies(rows)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load policies')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refetch() }, [refetch])

  const upsert = useCallback(async (
    infractionType: string,
    body: Parameters<typeof disciplineApi.upsertPolicy>[1],
  ) => {
    const updated = await disciplineApi.upsertPolicy(infractionType, body)
    setPolicies((prev) => {
      const idx = prev.findIndex((p) => p.infraction_type === infractionType)
      if (idx === -1) return [...prev, updated]
      const next = [...prev]
      next[idx] = updated
      return next
    })
    return updated
  }, [])

  return { policies, loading, error, refetch, upsert }
}
