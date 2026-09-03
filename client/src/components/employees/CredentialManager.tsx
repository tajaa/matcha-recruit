import { useRef, useState } from 'react'
import { Badge, Button, Card, Input } from '../ui'
import type { CredentialDocument } from '../../types/employee'
import { REQUIREMENT_STATUS_COLORS } from '../../types/credentialTemplates'
import { useCredentialManager, DOC_TYPE_LABELS } from './useCredentialManager'

const REVIEW_VARIANT: Record<string, 'success' | 'warning' | 'danger' | 'neutral'> = {
  approved: 'success',
  pending: 'warning',
  rejected: 'danger',
}

const EXTRACTION_LABEL: Record<string, string> = {
  pending: 'Extracting...',
  extracted: 'Data extracted',
  failed: 'Extraction failed',
}

type DocumentTypeOption = {
  value: string
  label: string
  hasExpiration: boolean
}

/** Newest first: approval time when the document has one, upload time otherwise. */
function byRecencyDesc(a: CredentialDocument, b: CredentialDocument) {
  return new Date(b.reviewed_at ?? b.created_at).getTime()
    - new Date(a.reviewed_at ?? a.created_at).getTime()
}

function ExpirationBadge({ date }: { date: string | null }) {
  if (!date) return null
  const exp = new Date(date)
  const now = new Date()
  const daysUntil = Math.ceil((exp.getTime() - now.getTime()) / 86_400_000)

  if (daysUntil < 0) return <Badge variant="danger">Expired</Badge>
  if (daysUntil <= 30) return <Badge variant="danger">Expires in {daysUntil}d</Badge>
  if (daysUntil <= 90) return <Badge variant="warning">Expires in {daysUntil}d</Badge>
  return <Badge variant="success">Valid until {exp.toLocaleDateString()}</Badge>
}

function ExtractedFields({ data }: { data: Record<string, unknown> | null }) {
  if (!data) return null
  const fields = (data as { fields?: Record<string, { value: string | null; confidence: number }> }).fields
  if (!fields || Object.keys(fields).length === 0) return null

  return (
    <div className="mt-2 rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
      <p className="text-[10px] font-medium text-zinc-400 uppercase tracking-wider mb-2">Extracted Data</p>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        {Object.entries(fields).map(([key, val]) => (
          val.value ? (
            <div key={key} className="flex justify-between text-xs">
              <span className="text-zinc-500">{key.replace(/_/g, ' ')}</span>
              <span className="text-zinc-200 font-mono">{val.value}</span>
            </div>
          ) : null
        ))}
      </div>
    </div>
  )
}

function DocumentCard({
  doc,
  onApprove,
  onReject,
  onReclassify,
  onDownload,
  onDelete,
  documentTypeOptions,
  requiresExpiration = false,
  contextLabel,
}: {
  doc: CredentialDocument
  /** Omitted for historical documents: approving one would re-point the
      requirement at a superseded file and demote the current credential. */
  onApprove?: (expirationDate?: string) => void
  onReject: () => void
  onReclassify: (documentType: string, expirationDate?: string) => void
  onDownload: () => void
  onDelete: () => void
  documentTypeOptions: DocumentTypeOption[]
  requiresExpiration?: boolean
  contextLabel?: 'Current' | 'History'
}) {
  const [confirming, setConfirming] = useState(false)
  const [approving, setApproving] = useState(false)
  const [expirationDate, setExpirationDate] = useState(doc.expires_at?.slice(0, 10) ?? '')
  const [reclassifying, setReclassifying] = useState(false)
  const [documentType, setDocumentType] = useState(doc.document_type)
  const needsExpirationConfirmation = requiresExpiration && !doc.expires_at
  const canApprove = !!onApprove && (doc.review_status === 'pending' || (doc.review_status === 'approved' && needsExpirationConfirmation))
  const selectedType = documentTypeOptions.find((option) => option.value === documentType)
  const reclassificationRequiresExpiration = selectedType?.hasExpiration ?? documentType === 'food_handler_card'

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <p className="text-sm font-medium text-zinc-200 truncate">{doc.filename}</p>
            <Badge variant={REVIEW_VARIANT[doc.review_status] ?? 'neutral'}>
              {doc.review_status}
            </Badge>
            {contextLabel && <Badge variant={contextLabel === 'Current' ? 'success' : 'neutral'}>{contextLabel}</Badge>}
            {doc.expires_at && <ExpirationBadge date={doc.expires_at} />}
          </div>
          <p className="text-[11px] text-zinc-500">
            {documentTypeOptions.find((option) => option.value === doc.document_type)?.label ?? doc.document_type}
            {' · '}
            {doc.file_size ? `${(doc.file_size / 1024).toFixed(0)} KB` : ''}
            {' · '}
            Uploaded {new Date(doc.created_at).toLocaleDateString()}
          </p>
          {doc.extraction_status !== 'extracted' && (
            <p className="text-[10px] text-zinc-600 mt-1">
              {EXTRACTION_LABEL[doc.extraction_status] ?? doc.extraction_status}
            </p>
          )}
        </div>
        <div className="flex gap-1 shrink-0">
          <Button size="sm" variant="ghost" onClick={onDownload}>Download</Button>
          <Button size="sm" variant="ghost" onClick={() => setReclassifying((value) => !value)}>Type</Button>
          {canApprove && (
            <>
              <Button size="sm" variant="primary" onClick={() => setApproving(true)}>
                {doc.review_status === 'approved' ? 'Confirm expiry' : 'Approve'}
              </Button>
              {doc.review_status === 'pending' && <Button size="sm" variant="ghost" onClick={onReject}>Reject</Button>}
            </>
          )}
          {confirming ? (
            <Button size="sm" variant="primary" className="!bg-red-600 hover:!bg-red-500" onClick={() => { onDelete(); setConfirming(false) }}>
              Confirm
            </Button>
          ) : (
            <Button size="sm" variant="ghost" onClick={() => setConfirming(true)}>Delete</Button>
          )}
        </div>
      </div>
      {approving && (
        <div className="mt-3 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
          {requiresExpiration && (
            <Input label="Card expiration" type="date" value={expirationDate} onChange={(event) => setExpirationDate(event.target.value)} />
          )}
          <div className="mt-2 flex gap-2">
            <Button size="sm" onClick={() => { onApprove?.(expirationDate || undefined); setApproving(false) }} disabled={requiresExpiration && !expirationDate}>
              Confirm approval
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setApproving(false)}>Cancel</Button>
          </div>
          {requiresExpiration && <p className="mt-2 text-[10px] text-zinc-500">Confirm the expiry from the document; the scheduler will block work after this date.</p>}
        </div>
      )}
      {reclassifying && (
        <div className="mt-3 rounded-lg border border-zinc-800 bg-zinc-950/40 p-3">
          <label className="block text-xs text-zinc-400">Document type
            <select value={documentType} onChange={(event) => setDocumentType(event.target.value)} className="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200">
              {documentTypeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          {reclassificationRequiresExpiration && <Input label="Credential expiration (required for approved documents)" type="date" value={expirationDate} onChange={(event) => setExpirationDate(event.target.value)} />}
          <div className="mt-2 flex gap-2">
            <Button size="sm" onClick={() => { onReclassify(documentType, expirationDate || undefined); setReclassifying(false) }} disabled={doc.review_status === 'approved' && reclassificationRequiresExpiration && !expirationDate}>Save type</Button>
            <Button size="sm" variant="ghost" onClick={() => setReclassifying(false)}>Cancel</Button>
          </div>
        </div>
      )}
      {doc.extraction_status === 'extracted' && (
        <ExtractedFields data={doc.extracted_data} />
      )}
      {doc.review_notes && (
        <p className="text-[11px] text-zinc-500 mt-2 italic">Note: {doc.review_notes}</p>
      )}
    </div>
  )
}

function UploadZone({
  documentType,
  onUpload,
  label = 'Upload credential',
}: {
  documentType: string
  onUpload: (file: File, type: string) => Promise<void>
  label?: string
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const [error, setError] = useState('')

  const handleFile = async (file: File) => {
    setUploading(true)
    setError('')
    try {
      await onUpload(file, documentType)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div
      className={`border border-dashed rounded-lg p-3 text-center cursor-pointer transition-colors ${
        dragOver ? 'border-emerald-500 bg-emerald-500/5' : 'border-zinc-700 hover:border-zinc-500'
      }`}
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragOver(false)
        const file = e.dataTransfer.files[0]
        if (file) handleFile(file)
      }}
    >
      <input
        ref={inputRef}
        type="file"
        className="hidden"
        accept=".pdf,.png,.jpg,.jpeg,.gif,.tiff"
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) handleFile(file)
          e.target.value = ''
        }}
      />
      {uploading ? (
        <p className="text-xs text-zinc-400">Uploading...</p>
      ) : (
        <p className="text-xs text-zinc-500">
          {label}: drop file or <span className="text-emerald-400 underline">browse</span>
          <span className="block text-[10px] text-zinc-600 mt-0.5">PDF, PNG, JPG up to 10MB</span>
        </p>
      )}
      {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
    </div>
  )
}

/** Show inline credential data for requirements verified via HRIS import (no document uploaded). */
function CredentialDataInline({ docType, credentials }: { docType: string; credentials: Record<string, unknown> }) {
  const s = (key: string): string | null => {
    const v = credentials[key]
    return typeof v === 'string' ? v : null
  }
  const d = (key: string): string | null => {
    const v = credentials[key]
    return typeof v === 'string' ? new Date(v).toLocaleDateString() : null
  }

  const fields: { label: string; value: string | null }[] = []

  if (docType === 'medical_license') {
    fields.push(
      { label: 'Type', value: s('license_type') },
      { label: 'Number', value: s('license_number') },
      { label: 'State', value: s('license_state') },
      { label: 'Expires', value: d('license_expiration') },
    )
  } else if (docType === 'dea') {
    fields.push(
      { label: 'DEA Number', value: s('dea_number') },
      { label: 'Expires', value: d('dea_expiration') },
    )
  } else if (docType === 'npi') {
    fields.push({ label: 'NPI', value: s('npi_number') })
  } else if (docType === 'board_cert') {
    fields.push(
      { label: 'Certification', value: s('board_certification') },
      { label: 'Expires', value: d('board_certification_expiration') },
    )
  } else if (docType === 'malpractice') {
    fields.push(
      { label: 'Carrier', value: s('malpractice_carrier') },
      { label: 'Expires', value: d('malpractice_expiration') },
    )
  }

  const filled = fields.filter(f => f.value)
  if (filled.length === 0) return null

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 mb-2">
      <p className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider mb-1.5">Imported from HRIS</p>
      <div className="flex flex-wrap gap-x-6 gap-y-1">
        {filled.map(f => (
          <div key={f.label} className="text-xs">
            <span className="text-zinc-500">{f.label}: </span>
            <span className="text-zinc-200 font-mono">{f.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}


export function CredentialManager({ employeeId }: { employeeId: string }) {
  const {
    credentials,
    loading,
    approve, reject, reclassify, remove, download,
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
  } = useCredentialManager(employeeId)

  const documentTypeOptionsByKey = new Map<string, DocumentTypeOption>(
    Object.entries(DOC_TYPE_LABELS).map(([value, label]) => [
      value,
      { value, label, hasExpiration: value === 'food_handler_card' },
    ]),
  )
  for (const requirement of requirements) {
    documentTypeOptionsByKey.set(requirement.credential_type_key, {
      value: requirement.credential_type_key,
      label: requirement.credential_type_label,
      hasExpiration: requirement.has_expiration,
    })
  }
  for (const documentType of Object.keys(docsByType)) {
    if (!documentTypeOptionsByKey.has(documentType)) {
      documentTypeOptionsByKey.set(documentType, {
        value: documentType,
        label: documentType,
        hasExpiration: false,
      })
    }
  }
  const documentTypeOptions = Array.from(documentTypeOptionsByKey.values())

  if (loading) return <p className="text-sm text-zinc-500">Loading credentials...</p>

  return (
    <div className="space-y-6">
      {/* Expiration summary */}
      {expirations.length > 0 && (
        <Card className="p-4">
          <h4 className="text-xs font-medium text-zinc-400 uppercase tracking-wider mb-3">Credential Expirations</h4>
          <div className="flex flex-wrap gap-3">
            {expirations.map((e) => (
              <div key={e.label} className="flex items-center gap-2">
                <span className="text-xs text-zinc-300">{e.label}</span>
                <ExpirationBadge date={e.date} />
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Structured credential data summary / edit */}
      {credentials && (
        <Card className="p-4">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-xs font-medium text-zinc-400 uppercase tracking-wider">Verified Credentials</h4>
            {!editing && (
              <Button size="sm" variant="ghost" onClick={startEdit}>Edit</Button>
            )}
          </div>

          {editing ? (
            <div className="space-y-3">
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <Input label="License Type" value={editForm.license_type} onChange={(e) => setEditForm({ ...editForm, license_type: e.target.value })} />
                <Input label="License Number" value={editForm.license_number} onChange={(e) => setEditForm({ ...editForm, license_number: e.target.value })} />
                <Input label="License State" value={editForm.license_state} onChange={(e) => setEditForm({ ...editForm, license_state: e.target.value })} />
                <Input label="License Expiration" type="date" value={editForm.license_expiration} onChange={(e) => setEditForm({ ...editForm, license_expiration: e.target.value })} />
                <Input label="NPI Number" value={editForm.npi_number} onChange={(e) => setEditForm({ ...editForm, npi_number: e.target.value })} />
                <Input label="DEA Number" value={editForm.dea_number} onChange={(e) => setEditForm({ ...editForm, dea_number: e.target.value })} />
                <Input label="DEA Expiration" type="date" value={editForm.dea_expiration} onChange={(e) => setEditForm({ ...editForm, dea_expiration: e.target.value })} />
                <Input label="Board Certification" value={editForm.board_certification} onChange={(e) => setEditForm({ ...editForm, board_certification: e.target.value })} />
                <Input label="Board Cert Expiration" type="date" value={editForm.board_certification_expiration} onChange={(e) => setEditForm({ ...editForm, board_certification_expiration: e.target.value })} />
                <Input label="Malpractice Carrier" value={editForm.malpractice_carrier} onChange={(e) => setEditForm({ ...editForm, malpractice_carrier: e.target.value })} />
                <Input label="Malpractice Expiration" type="date" value={editForm.malpractice_expiration} onChange={(e) => setEditForm({ ...editForm, malpractice_expiration: e.target.value })} />
                <Input label="Clinical Specialty" value={editForm.clinical_specialty} onChange={(e) => setEditForm({ ...editForm, clinical_specialty: e.target.value })} />
              </div>
              <div className="pt-3 border-t border-zinc-800 space-y-2">
                <p className="text-xs text-amber-400">Type <span className="font-mono font-bold">confirm</span> to save credential changes:</p>
                <input
                  value={confirmWord}
                  onChange={(e) => setConfirmWord(e.target.value)}
                  placeholder="Type confirm"
                  className="bg-zinc-900 border border-zinc-700 rounded text-zinc-200 text-sm px-3 py-1.5 w-40 focus:outline-none focus:border-zinc-500"
                />
                {editError && <p className="text-xs text-red-400">{editError}</p>}
                <div className="flex gap-2">
                  <Button size="sm" onClick={saveEdit} disabled={editSaving || confirmWord.toLowerCase() !== 'confirm'}>
                    {editSaving ? 'Saving...' : 'Save Changes'}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
                </div>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {credentials.license_type && (
                <div>
                  <p className="text-[10px] text-zinc-500">License</p>
                  <p className="text-sm text-zinc-200">{credentials.license_type} · {credentials.license_state}</p>
                </div>
              )}
              {credentials.npi_number && (
                <div>
                  <p className="text-[10px] text-zinc-500">NPI</p>
                  <p className="text-sm text-zinc-200 font-mono">{credentials.npi_number}</p>
                </div>
              )}
              {credentials.dea_number && (
                <div>
                  <p className="text-[10px] text-zinc-500">DEA</p>
                  <p className="text-sm text-zinc-200 font-mono">{credentials.dea_number}</p>
                </div>
              )}
              {credentials.board_certification && (
                <div>
                  <p className="text-[10px] text-zinc-500">Board Cert</p>
                  <p className="text-sm text-zinc-200">{credentials.board_certification}</p>
                </div>
              )}
              {credentials.malpractice_carrier && (
                <div>
                  <p className="text-[10px] text-zinc-500">Malpractice</p>
                  <p className="text-sm text-zinc-200">{credentials.malpractice_carrier}</p>
                </div>
              )}
              {credentials.clinical_specialty && (
                <div>
                  <p className="text-[10px] text-zinc-500">Specialty</p>
                  <p className="text-sm text-zinc-200">{credentials.clinical_specialty}</p>
                </div>
              )}
              {!credentials.license_number && !credentials.npi_number && !credentials.dea_number && (
                <p className="text-xs text-zinc-500 col-span-full">No credentials on file. Click Edit to add or upload a document above.</p>
              )}
            </div>
          )}
        </Card>
      )}

      {/* Requirement checklist summary */}
      {hasRequirements && !reqLoading && (
        <Card className="p-4">
          <h4 className="text-xs font-medium text-zinc-400 uppercase tracking-wider mb-3">Requirement Checklist</h4>
          <div className="flex flex-wrap gap-2">
            {requirements.map(r => (
              <div key={r.id} className="flex items-center gap-1.5">
                <span className={`text-[10px] px-1.5 py-0.5 rounded ${REQUIREMENT_STATUS_COLORS[r.status]}`}>
                  {r.status}
                </span>
                <span className="text-xs text-zinc-300">{r.credential_type_label}</span>
                {!r.is_required && <span className="text-[10px] text-zinc-600">(opt)</span>}
                {r.expires_at && <ExpirationBadge date={r.expires_at} />}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Document sections by type */}
      {allTypes.map((docType) => {
        const docs = docsByType[docType] ?? []
        const currentDocuments = docs.filter((d) => d.is_current)
        const reviewDocuments = docs.filter((d) => d.review_status !== 'approved')
        const historyDocuments = docs
          .filter((d) => d.review_status === 'approved' && !d.is_current)
          .sort(byRecencyDesc)
        const hasCurrent = currentDocuments.length > 0
        const req = reqByType[docType]
        const requirementExpired = !!req?.expires_at && new Date(`${req.expires_at}T00:00:00`).getTime() < new Date().setHours(0, 0, 0, 0)
        const isVerifiedViaData = req?.status === 'verified' && !requirementExpired && docs.length === 0

        return (
          <div key={docType}>
            <div className="flex items-center gap-2 mb-2">
              <h4 className="text-xs font-medium text-zinc-300">
                {req?.credential_type_label || (DOC_TYPE_LABELS[docType] ?? docType)}
              </h4>
              {(hasCurrent || isVerifiedViaData) && !requirementExpired && <Badge variant="success">Verified</Badge>}
              {requirementExpired && <Badge variant="danger">Expired</Badge>}
              {!hasCurrent && !isVerifiedViaData && reviewDocuments.length > 0 && <Badge variant="warning">Pending Review</Badge>}
              {!hasCurrent && !isVerifiedViaData && reviewDocuments.length === 0 && <Badge variant="neutral">Not uploaded</Badge>}
              {req && !req.is_required && <span className="text-[10px] text-zinc-600">Optional</span>}
            </div>

            {/* Show inline credential data for HRIS-verified items */}
            {isVerifiedViaData && credentials && (
              <CredentialDataInline docType={docType} credentials={credentials} />
            )}

            {(currentDocuments.length > 0 || reviewDocuments.length > 0) && (
              <div className="space-y-2 mb-2">
                {currentDocuments.map((doc) => (
                  <DocumentCard
                    key={doc.id}
                    doc={doc}
                    onApprove={(expirationDate) => approve(doc.id, expirationDate)}
                    onReject={() => reject(doc.id)}
                    onReclassify={(documentType, expirationDate) => reclassify(doc.id, documentType, expirationDate)}
                    onDownload={() => download(doc.id)}
                    onDelete={() => remove(doc.id)}
                    documentTypeOptions={documentTypeOptions}
                    requiresExpiration={req?.has_expiration ?? doc.document_type === 'food_handler_card'}
                    contextLabel="Current"
                  />
                ))}
                {reviewDocuments.map((doc) => (
                  <DocumentCard
                    key={doc.id}
                    doc={doc}
                    onApprove={(expirationDate) => approve(doc.id, expirationDate)}
                    onReject={() => reject(doc.id)}
                    onReclassify={(documentType, expirationDate) => reclassify(doc.id, documentType, expirationDate)}
                    onDownload={() => download(doc.id)}
                    onDelete={() => remove(doc.id)}
                    documentTypeOptions={documentTypeOptions}
                    requiresExpiration={req?.has_expiration ?? doc.document_type === 'food_handler_card'}
                  />
                ))}
              </div>
            )}

            {historyDocuments.length > 0 && (
              <div className="mb-2">
                <p className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider mb-1.5">History</p>
                <div className="space-y-2">
                  {historyDocuments.map((doc) => (
                    <DocumentCard
                      key={doc.id}
                      doc={doc}
                      onReject={() => reject(doc.id)}
                      onReclassify={(documentType, expirationDate) => reclassify(doc.id, documentType, expirationDate)}
                      onDownload={() => download(doc.id)}
                      onDelete={() => remove(doc.id)}
                      documentTypeOptions={documentTypeOptions}
                      requiresExpiration={req?.has_expiration ?? doc.document_type === 'food_handler_card'}
                      contextLabel="History"
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Upload only where the backend accepts one: a materialized
                requirement, or a type in the server's VALID_DOCUMENT_TYPES set
                (mirrored by DOC_TYPE_LABELS). Legacy/removed types 400. */}
            {(!!req || DOC_TYPE_LABELS[docType] !== undefined) && (
              <UploadZone
                documentType={docType}
                onUpload={handleUpload}
                label={hasCurrent || isVerifiedViaData ? 'Add replacement credential' : 'Upload credential'}
              />
            )}
          </div>
        )
      })}

      {/* Upload additional / other type */}
      {!docsByType['other'] && (
        <div>
          <h4 className="text-xs font-medium text-zinc-300 mb-2">Other Document</h4>
          <UploadZone documentType="other" onUpload={handleUpload} />
        </div>
      )}
    </div>
  )
}
