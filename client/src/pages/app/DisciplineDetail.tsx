import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Badge, Button, Card } from '../../components/ui'
import { ArrowLeft, Loader2, FileText } from 'lucide-react'
import { useDisciplineRecord } from '../../hooks/discipline/useDiscipline'
import SignatureWorkflow from '../../features/discipline/SignatureWorkflow'
import { api } from '../../api/client'
import type {
  DisciplineLevel,
  DisciplineStatus,
} from '../../api/discipline'

const LEVEL_LABEL: Record<DisciplineLevel, string> = {
  verbal_warning: 'Verbal Warning',
  written_warning: 'Written Warning',
  pip: 'Performance Improvement Plan',
  final_warning: 'Final Warning',
  suspension: 'Suspension',
}

const STATUS_VARIANT: Record<DisciplineStatus, 'success' | 'warning' | 'danger' | 'neutral'> = {
  draft: 'neutral',
  pending_meeting: 'warning',
  pending_signature: 'warning',
  active: 'success',
  completed: 'neutral',
  expired: 'neutral',
  escalated: 'danger',
}

type EmployeeRow = {
  id: string
  first_name: string | null
  last_name: string | null
  email: string
  job_title: string | null
}

function employeeFullName(e: EmployeeRow | null): string {
  if (!e) return 'Employee'
  const n = [e.first_name || '', e.last_name || ''].join(' ').trim()
  return n || 'Employee'
}

export default function DisciplineDetail() {
  const { recordId } = useParams<{ recordId: string }>()
  const navigate = useNavigate()
  const {
    record,
    auditLog,
    loading,
    error,
    markMeetingHeld,
    requestSignature,
    refuse,
    uploadPhysical,
    downloadLetter,
  } = useDisciplineRecord(recordId)

  const [employee, setEmployee] = useState<EmployeeRow | null>(null)

  useEffect(() => {
    if (!record?.employee_id) return
    api.get<EmployeeRow>(`/employees/${record.employee_id}`)
      .then(setEmployee)
      .catch(() => setEmployee(null))
  }, [record?.employee_id])

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center">
        <Loader2 className="w-5 h-5 animate-spin text-zinc-400" />
      </div>
    )
  }
  if (error || !record) {
    return (
      <div className="p-6">
        <Button variant="ghost" onClick={() => navigate('/app/discipline')}>
          <ArrowLeft className="w-4 h-4" />
          <span className="ml-2">Back</span>
        </Button>
        <div className="mt-4 text-sm text-red-400">{error || 'Record not found'}</div>
      </div>
    )
  }

  return (
    <div className="space-y-6 p-6">
      <Button variant="ghost" onClick={() => navigate('/app/discipline')}>
        <ArrowLeft className="w-4 h-4" />
        <span className="ml-2">Back to discipline</span>
      </Button>

      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">
            {LEVEL_LABEL[record.discipline_type]}
            {record.override_level && (
              <span className="ml-2 text-sm font-normal text-amber-400">override</span>
            )}
          </h1>
          <div className="text-sm text-zinc-500 mt-1">
            {employeeFullName(employee)} · {record.infraction_type.replace(/_/g, ' ')} ·{' '}
            severity {record.severity}
          </div>
        </div>
        <Badge variant={STATUS_VARIANT[record.status]}>{record.status.replace(/_/g, ' ')}</Badge>
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2 p-5 space-y-4">
          <Section label="Description">
            <p className="text-sm text-zinc-300 whitespace-pre-wrap">
              {record.description || <span className="text-zinc-500">No description recorded.</span>}
            </p>
          </Section>

          <Section label="Expected improvement">
            <p className="text-sm text-zinc-300 whitespace-pre-wrap">
              {record.expected_improvement || (
                <span className="text-zinc-500">No specific improvement plan attached.</span>
              )}
            </p>
          </Section>

          {record.override_level && (
            <Section label="Override reason">
              <p className="text-sm text-amber-300">{record.override_reason || '—'}</p>
            </Section>
          )}

          <SignatureWorkflow
            record={record}
            employeeName={employeeFullName(employee)}
            onMeetingHeld={markMeetingHeld}
            onRequestSignature={requestSignature}
            onRefuse={refuse}
            onUploadPhysical={uploadPhysical}
            onDownloadLetter={downloadLetter}
          />

          {record.signed_pdf_storage_path && (
            <div className="flex items-center gap-2 text-sm text-zinc-300">
              <FileText className="w-4 h-4" />
              <a
                href={record.signed_pdf_storage_path}
                target="_blank"
                rel="noreferrer"
                className="text-emerald-400 hover:text-emerald-300"
              >
                View signed PDF
              </a>
            </div>
          )}
        </Card>

        <Card className="p-5 space-y-4">
          <Section label="Issued">
            <div className="text-sm text-zinc-300">
              {new Date(record.issued_date).toLocaleDateString()}
            </div>
          </Section>
          <Section label="Active until">
            <div className="text-sm text-zinc-300">
              {record.expires_at ? new Date(record.expires_at).toLocaleDateString() : '—'}
              <span className="text-xs text-zinc-500 ml-2">
                ({record.lookback_months} mo lookback)
              </span>
            </div>
          </Section>
          <Section label="Review date">
            <div className="text-sm text-zinc-300">
              {record.review_date ? new Date(record.review_date).toLocaleDateString() : '—'}
            </div>
          </Section>
          {record.escalated_from_id && (
            <Section label="Escalated from">
              <a
                className="text-sm text-emerald-400 hover:text-emerald-300"
                onClick={() => navigate(`/app/discipline/${record.escalated_from_id}`)}
              >
                View prior record
              </a>
            </Section>
          )}

          <div className="border-t border-zinc-800 pt-4">
            <div className="text-xs uppercase text-zinc-500 mb-2">Audit log</div>
            <ul className="space-y-2 text-xs">
              {auditLog.length === 0 && (
                <li className="text-zinc-500">No audit entries yet.</li>
              )}
              {auditLog.map((e) => (
                <li key={e.id}>
                  <div className="text-zinc-300">
                    <span className="font-medium">{e.action.replace(/_/g, ' ')}</span>
                  </div>
                  <div className="text-zinc-500">
                    {new Date(e.created_at).toLocaleString()}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </Card>
      </div>
    </div>
  )
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1.5">{label}</div>
      {children}
    </div>
  )
}
