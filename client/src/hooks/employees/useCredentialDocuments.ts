import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import type { CredentialDocument, EmployeeCredentials } from '../../types/employee'

export function useCredentialDocuments(employeeId: string) {
  const [documents, setDocuments] = useState<CredentialDocument[]>([])
  const [credentials, setCredentials] = useState<EmployeeCredentials | null>(null)
  const [loading, setLoading] = useState(true)

  const reqId = useRef(0)
  useEffect(() => () => { reqId.current++ }, [])

  const fetchAll = useCallback(async () => {
    const id = ++reqId.current
    setLoading(true)
    try {
      const [docs, creds] = await Promise.all([
        api.get<CredentialDocument[]>(`/employees/${employeeId}/credential-documents`),
        api.get<EmployeeCredentials>(`/employees/${employeeId}/credentials`),
      ])
      if (id !== reqId.current) return
      setDocuments(docs)
      setCredentials(creds)
    } catch {
      if (id !== reqId.current) return
      setDocuments([])
      setCredentials(null)
    } finally {
      if (id === reqId.current) setLoading(false)
    }
  }, [employeeId])

  useEffect(() => { fetchAll() }, [fetchAll])

  const upload = useCallback(async (file: File, documentType: string) => {
    const fd = new FormData()
    fd.append('file', file)
    const doc = await api.upload<CredentialDocument>(
      `/employees/${employeeId}/credential-documents?document_type=${encodeURIComponent(documentType)}`,
      fd,
    )
    setDocuments((prev) => [...prev, doc])
    return doc
  }, [employeeId])

  const approve = useCallback(async (docId: string, applyToCredentials = true, notes?: string) => {
    await api.post(`/employees/${employeeId}/credential-documents/${docId}/approve`, {
      apply_to_credentials: applyToCredentials,
      notes,
    })
    await fetchAll()
  }, [employeeId, fetchAll])

  const reject = useCallback(async (docId: string, notes?: string) => {
    await api.post(`/employees/${employeeId}/credential-documents/${docId}/reject`, { notes })
    setDocuments((prev) => prev.map((d) => d.id === docId ? { ...d, review_status: 'rejected' } : d))
  }, [employeeId])

  const remove = useCallback(async (docId: string) => {
    await api.delete(`/employees/${employeeId}/credential-documents/${docId}`)
    setDocuments((prev) => prev.filter((d) => d.id !== docId))
  }, [employeeId])

  const download = useCallback(async (docId: string) => {
    const { url } = await api.get<{ url: string; filename: string }>(
      `/employees/${employeeId}/credential-documents/${docId}/download`,
    )
    window.open(url, '_blank')
  }, [employeeId])

  return { documents, credentials, loading, upload, approve, reject, remove, download, refetch: fetchAll }
}
