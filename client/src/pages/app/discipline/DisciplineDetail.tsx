import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Badge, Button, Card, Textarea, useToast } from '../../../components/ui'
import { ArrowLeft, Loader2, FileText, ShieldCheck, ShieldX } from 'lucide-react'
import { useDisciplineRecord } from '../../../hooks/discipline/useDiscipline'
import SignatureWorkflow from '../../../components/discipline/SignatureWorkflow'
import { api, ApiError } from '../../../api/client'
import type {
  DisciplineLevel,
  DisciplineStatus,
} from '../../../api/discipline/discipline'

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
  denied: 'danger',
}

const MIN_DENIAL_REASON_CHARS = 20

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
    approve,
    deny,
  } = useDisciplineRecord(recordId)
  const { toast } = useToast()

  const [employee, setEmployee] = useState<EmployeeRow | null>(null)
  const [showDenyForm, setShowDenyForm] = useState(false)
  const [denyReason, setDenyReason] = useState('')
  const [decisionBusy, setDecisionBusy] = useState(false)

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

  async function handleApprove() {
    setDecisionBusy(true)
    try {
      await approve()
      toast('Approved — moving to a meeting.', 'success')
    } catch (e) {
      toast(e instanceof ApiError ? e.message : 'Failed to approve', 'error')
    } finally {
      setDecisionBusy(false)
    }
  }

  async function handleDeny() {
    if (denyReason.trim().length < MIN_DENIAL_REASON_CHARS) return
    setDecisionBusy(true)
    try {
      await deny(denyReason.trim())
      toast('Denied.', 'success')
      setShowDenyForm(false)
      setDenyReason('')
    } catch (e) {
      toast(e instanceof ApiError ? e.message : 'Failed to deny', 'error')
    } finally {
      setDecisionBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <Button variant="ghost" onClick={() => navigate('/app/discipline')}>
        <ArrowLeft className="w-4 h-4" />
        <span className="ml-2">Back to performance action</span>
      </Button>

      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
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

      {record.approval_status === 'pending' && (
        <Card className="p-4 border-amber-800 bg-amber-950/20">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-sm font-medium text-amber-300">Awaiting HR approval</div>
              <p className="text-xs text-zinc-400 mt-1">
                This record was drafted from an incident and has not been issued. Approving
                schedules the meeting step; denying is terminal — a later decision needs a new
                record.
              </p>
            </div>
            <div className="flex gap-2 shrink-0">
              <Button size="sm" onClick={handleApprove} disabled={decisionBusy}>
                <ShieldCheck className="w-4 h-4" />
                <span className="ml-1.5">Approve</span>
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setShowDenyForm((v) => !v)}
                disabled={decisionBusy}
              >
                <ShieldX className="w-4 h-4" />
                <span className="ml-1.5">Deny</span>
              </Button>
            </div>
          </div>
          {showDenyForm && (
            <div className="mt-3 space-y-2">
              <Textarea
                label="Reason for denial (required, min 20 characters)"
                value={denyReason}
                onChange={(e) => setDenyReason(e.target.value)}
                rows={3}
              />
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  className="bg-red-700 hover:bg-red-600 text-white"
                  disabled={decisionBusy || denyReason.trim().length < MIN_DENIAL_REASON_CHARS}
                  onClick={handleDeny}
                >
                  Confirm denial
                </Button>
                <span className="text-xs text-zinc-500">
                  {denyReason.trim().length}/{MIN_DENIAL_REASON_CHARS}
                </span>
              </div>
            </div>
          )}
        </Card>
      )}

      {record.approval_status === 'denied' && (
        <Card className="p-4 border-red-900 bg-red-950/20">
          <div className="text-sm font-medium text-red-300">Denied</div>
          <p className="text-sm text-zinc-300 mt-1 whitespace-pre-wrap">
            {record.denial_reason || 'No reason recorded.'}
          </p>
        </Card>
      )}

      {record.approval_status === 'approved' && (
        <Card className="p-3 border-emerald-900 bg-emerald-950/10">
          <div className="flex items-center gap-2 text-sm text-emerald-300">
            <ShieldCheck className="w-4 h-4" />
            Approved
            {record.approval_decided_at && (
              <span className="text-zinc-500">
                on {new Date(record.approval_decided_at).toLocaleDateString()}
              </span>
            )}
          </div>
        </Card>
      )}

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

          {record.remedial_training && (
            <Section label="Remedial training">
              <div className="flex items-center gap-2 text-sm">
                <Badge variant={record.remedial_training.status === 'completed' ? 'success' : 'warning'}>
                  {record.remedial_training.status.replace(/_/g, ' ')}
                </Badge>
                {record.remedial_training.completed_date ? (
                  <span className="text-zinc-400">
                    Completed {new Date(record.remedial_training.completed_date).toLocaleDateString()}
                  </span>
                ) : record.remedial_training.due_date ? (
                  <span className="text-zinc-400">
                    Due {new Date(record.remedial_training.due_date).toLocaleDateString()}
                  </span>
                ) : null}
              </div>
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
