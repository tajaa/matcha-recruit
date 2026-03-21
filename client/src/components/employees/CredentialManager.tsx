import { useRef, useState } from 'react'
import { Badge, Button, Card } from '../ui'
import { useCredentialDocuments } from '../../hooks/employees/useCredentialDocuments'
import type { CredentialDocument } from '../../types/employee'

const DOC_TYPE_LABELS: Record<string, string> = {
  medical_license: 'Professional License',
  dea: 'DEA Registration',
  npi: 'NPI Verification',
  board_cert: 'Board Certification',
  malpractice: 'Malpractice Insurance',
  health_clearance: 'Health Clearance',
  other: 'Other Document',
}

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
  onDownload,
  onDelete,
}: {
  doc: CredentialDocument
  onApprove: () => void
  onReject: () => void
  onDownload: () => void
  onDelete: () => void
}) {
  const [confirming, setConfirming] = useState(false)

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <p className="text-sm font-medium text-zinc-200 truncate">{doc.filename}</p>
            <Badge variant={REVIEW_VARIANT[doc.review_status] ?? 'neutral'}>
              {doc.review_status}
            </Badge>
          </div>
          <p className="text-[11px] text-zinc-500">
            {DOC_TYPE_LABELS[doc.document_type] ?? doc.document_type}
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
          {doc.review_status === 'pending' && (
            <>
              <Button size="sm" variant="primary" onClick={onApprove}>Approve</Button>
              <Button size="sm" variant="ghost" onClick={onReject}>Reject</Button>
            </>
          )}
          {confirming ? (
            <Button size="sm" variant="danger" onClick={() => { onDelete(); setConfirming(false) }}>
              Confirm
            </Button>
          ) : (
            <Button size="sm" variant="ghost" onClick={() => setConfirming(true)}>Delete</Button>
          )}
        </div>
      </div>
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
}: {
  documentType: string
  onUpload: (file: File, type: string) => Promise<void>
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [dragOver, setDragOver] = useState(false)

  const handleFile = async (file: File) => {
    setUploading(true)
    try {
      await onUpload(file, documentType)
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
          Drop file or <span className="text-emerald-400 underline">browse</span>
          <span className="block text-[10px] text-zinc-600 mt-0.5">PDF, PNG, JPG up to 10MB</span>
        </p>
      )}
    </div>
  )
}

export function CredentialManager({ employeeId }: { employeeId: string }) {
  const {
    documents, credentials, loading,
    upload, approve, reject, remove, download,
  } = useCredentialDocuments(employeeId)

  if (loading) return <p className="text-sm text-zinc-500">Loading credentials...</p>

  // Group documents by type
  const docsByType: Record<string, CredentialDocument[]> = {}
  for (const doc of documents) {
    ;(docsByType[doc.document_type] ??= []).push(doc)
  }

  // All known document types (from uploaded docs + standard set)
  const allTypes = Array.from(new Set([
    ...Object.keys(DOC_TYPE_LABELS).filter((t) => t !== 'other'),
    ...Object.keys(docsByType),
  ]))

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

      {/* Structured credential data summary */}
      {credentials && (credentials.license_number || credentials.npi_number || credentials.dea_number) && (
        <Card className="p-4">
          <h4 className="text-xs font-medium text-zinc-400 uppercase tracking-wider mb-3">Verified Credentials</h4>
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
          </div>
        </Card>
      )}

      {/* Document sections by type */}
      {allTypes.map((docType) => {
        const docs = docsByType[docType] ?? []
        const hasApproved = docs.some((d) => d.review_status === 'approved')

        return (
          <div key={docType}>
            <div className="flex items-center gap-2 mb-2">
              <h4 className="text-xs font-medium text-zinc-300">
                {DOC_TYPE_LABELS[docType] ?? docType}
              </h4>
              {hasApproved && <Badge variant="success">Verified</Badge>}
              {!hasApproved && docs.length > 0 && <Badge variant="warning">Pending Review</Badge>}
              {docs.length === 0 && <Badge variant="neutral">Not uploaded</Badge>}
            </div>

            {docs.length > 0 && (
              <div className="space-y-2 mb-2">
                {docs.map((doc) => (
                  <DocumentCard
                    key={doc.id}
                    doc={doc}
                    onApprove={() => approve(doc.id)}
                    onReject={() => reject(doc.id)}
                    onDownload={() => download(doc.id)}
                    onDelete={() => remove(doc.id)}
                  />
                ))}
              </div>
            )}

            {!hasApproved && (
              <UploadZone documentType={docType} onUpload={handleUpload} />
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
