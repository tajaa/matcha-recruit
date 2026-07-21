import { useEffect, useState } from 'react'
import { useCredentialDocuments } from '../../hooks/employees/useCredentialDocuments'
import { api } from '../../api/client'
import { fetchEmployeeRequirements } from '../../api/employees/credentialTemplates'
import type { CredentialDocument } from '../../types/employee'
import type { EmployeeCredentialRequirement } from '../../types/credentialTemplates'

export const DOC_TYPE_LABELS: Record<string, string> = {
  medical_license: 'Professional License',
  dea: 'DEA Registration',
  npi: 'NPI Verification',
  board_cert: 'Board Certification',
  malpractice: 'Malpractice Insurance',
  health_clearance: 'Health Clearance',
  other: 'Other Document',
}

export function useCredentialManager(employeeId: string) {
  const {
    documents, credentials, loading,
    upload, approve, reject, remove, download, refetch,
  } = useCredentialDocuments(employeeId)

  const [requirements, setRequirements] = useState<EmployeeCredentialRequirement[]>([])
  const [reqLoading, setReqLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    fetchEmployeeRequirements(employeeId)
      .then((reqs) => { if (!cancelled) setRequirements(reqs) })
      .catch(() => {})
      .finally(() => { if (!cancelled) setReqLoading(false) })
    return () => { cancelled = true }
  }, [employeeId])

  const [editing, setEditing] = useState(false)
  const [editForm, setEditForm] = useState<Record<string, string>>({})
  const [confirmWord, setConfirmWord] = useState('')
  const [editSaving, setEditSaving] = useState(false)
  const [editError, setEditError] = useState('')

  function startEdit() {
    if (!credentials) return
    setEditForm({
      license_type: credentials.license_type ?? '',
      license_number: credentials.license_number ?? '',
      license_state: credentials.license_state ?? '',
      license_expiration: credentials.license_expiration ?? '',
      npi_number: credentials.npi_number ?? '',
      dea_number: credentials.dea_number ?? '',
      dea_expiration: credentials.dea_expiration ?? '',
      board_certification: credentials.board_certification ?? '',
      board_certification_expiration: credentials.board_certification_expiration ?? '',
      malpractice_carrier: credentials.malpractice_carrier ?? '',
      malpractice_expiration: credentials.malpractice_expiration ?? '',
      clinical_specialty: credentials.clinical_specialty ?? '',
    })
    setConfirmWord('')
    setEditError('')
    setEditing(true)
  }

  async function saveEdit() {
    if (confirmWord.toLowerCase() !== 'confirm') {
      setEditError('Type "confirm" to save changes')
      return
    }
    setEditSaving(true)
    setEditError('')
    try {
      const body: Record<string, string | null> = {}
      for (const [k, v] of Object.entries(editForm)) {
        body[k] = v.trim() || null
      }
      await api.put(`/employees/${employeeId}/credentials`, body)
      setEditing(false)
      refetch()
    } catch (err) {
      setEditError(err instanceof Error ? err.message : 'Failed to update credentials')
    } finally {
      setEditSaving(false)
    }
  }

  // Group documents by type
  const docsByType: Record<string, CredentialDocument[]> = {}
  for (const doc of documents) {
    ;(docsByType[doc.document_type] ??= []).push(doc)
  }

  // Requirement-driven: show only types this employee actually needs
  // Fall back to the old hardcoded set if no requirements loaded yet
  const hasRequirements = requirements.length > 0
  const requiredTypeKeys = hasRequirements
    ? requirements.map(r => r.credential_type_key)
    : Object.keys(DOC_TYPE_LABELS).filter((t) => t !== 'other')
  const allTypes = Array.from(new Set([
    ...requiredTypeKeys,
    ...Object.keys(docsByType),
  ]))
  const reqByType = Object.fromEntries(requirements.map(r => [r.credential_type_key, r]))

  // Credential expiration data for summary
  const expirations: { label: string; date: string | null }[] = []
  if (credentials) {
    if (credentials.license_expiration) expirations.push({ label: 'License', date: credentials.license_expiration })
    if (credentials.dea_expiration) expirations.push({ label: 'DEA', date: credentials.dea_expiration })
    if (credentials.board_certification_expiration) expirations.push({ label: 'Board Cert', date: credentials.board_certification_expiration })
    if (credentials.malpractice_expiration) expirations.push({ label: 'Malpractice', date: credentials.malpractice_expiration })
  }

  const handleUpload = async (file: File, docType: string) => {
    await upload(file, docType)
  }

  return {
    credentials,
    loading,
    approve, reject, remove, download,
    requirements,
    reqLoading,
    editing, setEditing,
    editForm, setEditForm,
    confirmWord, setConfirmWord,
    editSaving,
    editError,
    startEdit,
    saveEdit,
    docsByType,
    hasRequirements,
    allTypes,
    reqByType,
    expirations,
    handleUpload,
  }
}
