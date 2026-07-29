import { useCallback, useEffect, useRef, useState } from 'react'
import {
  disciplineApi,
  type DisciplineRecord,
  type DisciplineStatus,
  type DisciplineApprovalStatus,
  type DisciplineRecommendation,
  type DisciplineRecommendInput,
  type DisciplineIssueInput,
  type DisciplinePolicy,
  type DisciplineAuditEntry,
  type DisciplineTemplate,
  type DisciplineTemplateUpsertInput,
  type DisciplineApprover,
} from '../../api/discipline/discipline'

export function useDisciplineList(
  initialStatus: DisciplineStatus | undefined = undefined,
  approvalStatus: DisciplineApprovalStatus | undefined = undefined,
) {
  const [records, setRecords] = useState<DisciplineRecord[]>([])
  const [status, setStatus] = useState<DisciplineStatus | undefined>(initialStatus)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const reqId = useRef(0)
  useEffect(() => () => { reqId.current++ }, [])

  const refetch = useCallback(async () => {
    const id = ++reqId.current
    setLoading(true)
    setError('')
    try {
      const rows = await disciplineApi.list(status, approvalStatus)
      if (id !== reqId.current) return
      setRecords(rows)
    } catch (e) {
      if (id !== reqId.current) return
      setError(e instanceof Error ? e.message : 'Failed to load discipline records')
    } finally {
      if (id === reqId.current) setLoading(false)
    }
  }, [status, approvalStatus])

  useEffect(() => { refetch() }, [refetch])

  return { records, status, setStatus, loading, error, refetch }
}

export function useDisciplineRecord(recordId: string | undefined) {
  const [record, setRecord] = useState<DisciplineRecord | null>(null)
  const [auditLog, setAuditLog] = useState<DisciplineAuditEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const reqId = useRef(0)
  useEffect(() => () => { reqId.current++ }, [])

  const refetch = useCallback(async () => {
    if (!recordId) return
    const id = ++reqId.current
    setLoading(true)
    setError('')
    try {
      const [r, log] = await Promise.all([
        disciplineApi.get(recordId),
        disciplineApi.auditLog(recordId).catch(() => [] as DisciplineAuditEntry[]),
      ])
      if (id !== reqId.current) return
      setRecord(r)
      setAuditLog(log)
    } catch (e) {
      if (id !== reqId.current) return
      setError(e instanceof Error ? e.message : 'Failed to load discipline record')
    } finally {
      if (id === reqId.current) setLoading(false)
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

  /** Throws ApiError 409 if the record isn't awaiting approval — caller
   *  surfaces the message rather than this hook swallowing it, since a 409
   *  here usually means someone else already decided it. */
  const approve = useCallback(async () => {
    if (!recordId) return
    const updated = await disciplineApi.approve(recordId)
    setRecord(updated)
    await refetch()
    return updated
  }, [recordId, refetch])

  const deny = useCallback(async (reason: string) => {
    if (!recordId) return
    const updated = await disciplineApi.deny(recordId, reason)
    setRecord(updated)
    await refetch()
    return updated
  }, [recordId, refetch])

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
    approve,
    deny,
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

export function useDisciplineTemplates() {
  const [templates, setTemplates] = useState<DisciplineTemplate[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const refetch = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const rows = await disciplineApi.listTemplates(true)
      setTemplates(rows)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load templates')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refetch() }, [refetch])

  const create = useCallback(async (body: DisciplineTemplateUpsertInput) => {
    const created = await disciplineApi.createTemplate(body)
    await refetch()
    return created
  }, [refetch])

  const update = useCallback(async (templateId: string, body: DisciplineTemplateUpsertInput) => {
    const updated = await disciplineApi.updateTemplate(templateId, body)
    await refetch()
    return updated
  }, [refetch])

  const remove = useCallback(async (templateId: string) => {
    await disciplineApi.deleteTemplate(templateId)
    await refetch()
  }, [refetch])

  return { templates, loading, error, refetch, create, update, remove }
}

export function useDisciplineApprovers() {
  const [approvers, setApprovers] = useState<DisciplineApprover[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const refetch = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const rows = await disciplineApi.listApprovers()
      setApprovers(rows)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load approvers')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refetch() }, [refetch])

  const setApprover = useCallback(async (userId: string, isHrApprover: boolean) => {
    await disciplineApi.setApprover(userId, isHrApprover)
    setApprovers((prev) => prev.map((a) => a.user_id === userId ? { ...a, is_hr_approver: isHrApprover } : a))
  }, [])

  return { approvers, loading, error, refetch, setApprover }
}
