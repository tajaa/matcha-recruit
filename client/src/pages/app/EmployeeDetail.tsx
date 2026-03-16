import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Badge, Button, Card, Input, Select } from '../../components/ui'
import { EmployeeStatusBadge } from '../../components/employees/EmployeeStatusBadge'
import { OnboardingTaskList } from '../../components/employees/OnboardingTaskList'
import { useEmployeeDetail } from '../../hooks/employees/useEmployeeDetail'
import { typeLabel, statusLabel } from '../../types/employee'

const STATUS_OPTIONS = Object.entries(statusLabel).map(([value, label]) => ({ value, label }))

type Tab = 'profile' | 'onboarding'

type EditableFieldProps = {
  label: string
  value: string | null
  onSave: (value: string) => Promise<void> | void
  type?: string
}

function EditableField({ label, value, onSave, type = 'text' }: EditableFieldProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value ?? '')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')

  async function handleBlur() {
    const trimmed = draft.trim()
    if (trimmed === (value ?? '')) {
      setEditing(false)
      return
    }
    setSaving(true)
    setSaveError('')
    try {
      await onSave(trimmed)
      setEditing(false)
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  if (editing) {
    return (
      <div>
        <dt className="text-zinc-500 text-xs">{label}</dt>
        <dd className="mt-1">
          <Input
            label=""
            type={type}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={handleBlur}
            onKeyDown={(e) => { if (e.key === 'Enter') handleBlur() }}
            autoFocus
            disabled={saving}
            className="!py-1 text-sm"
          />
          {saveError && <p className="text-[10px] text-red-400 mt-0.5">{saveError}</p>}
        </dd>
      </div>
    )
  }

  return (
    <div className="cursor-pointer group" onClick={() => { setDraft(value ?? ''); setEditing(true) }}>
      <dt className="text-zinc-500 text-xs">{label}</dt>
      <dd className="text-zinc-200 text-sm mt-0.5 group-hover:text-emerald-400 transition-colors">
        {value || <span className="text-zinc-600">—</span>}
      </dd>
    </div>
  )
}

export default function EmployeeDetail() {
  const { employeeId } = useParams<{ employeeId: string }>()
  const navigate = useNavigate()
  const {
    employee, loading, error,
    updateEmployee, updateStatus, deleteEmployee, sendInvite,
  } = useEmployeeDetail(employeeId!)
  const [tab, setTab] = useState<Tab>('profile')
  const [inviting, setInviting] = useState(false)

  if (loading) return <p className="text-sm text-zinc-500">Loading employee...</p>
  if (error) return <p className="text-sm text-red-400">{error}</p>
  if (!employee) return <p className="text-sm text-zinc-500">Employee not found.</p>

  async function handleFieldSave(field: string, value: string) {
    await updateEmployee({ [field]: value || null })
  }

  async function handleInvite() {
    setInviting(true)
    try { await sendInvite() } finally { setInviting(false) }
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <Link to="/app/employees" className="text-zinc-500 hover:text-zinc-300 transition-colors">
          &larr;
        </Link>
        <h1 className="text-xl font-semibold text-zinc-100 font-[Space_Grotesk]">
          {employee.first_name} {employee.last_name}
        </h1>
        <EmployeeStatusBadge status={employee.employment_status} />
        {employee.employment_type && (
          <Badge variant="neutral">
            {typeLabel[employee.employment_type] ?? employee.employment_type}
          </Badge>
        )}
      </div>

      {/* Layout: 2/3 main + 1/3 sidebar */}
      <div className="grid grid-cols-3 gap-6">
        {/* Main column */}
        <div className="col-span-2">
          {/* Tabs */}
          <div className="flex gap-1 mb-4">
            {(['profile', 'onboarding'] as const).map((t) => (
              <Button
                key={t}
                variant={tab === t ? 'primary' : 'ghost'}
                size="sm"
                onClick={() => setTab(t)}
              >
                {t.charAt(0).toUpperCase() + t.slice(1)}
              </Button>
            ))}
          </div>

          <Card className="p-5">
            {tab === 'profile' && (
              <div className="grid grid-cols-2 gap-x-8 gap-y-4">
                <EditableField label="First Name" value={employee.first_name}
                  onSave={(v) => handleFieldSave('first_name', v)} />
                <EditableField label="Last Name" value={employee.last_name}
                  onSave={(v) => handleFieldSave('last_name', v)} />
                <EditableField label="Work Email" value={employee.work_email}
                  onSave={(v) => handleFieldSave('work_email', v)} type="email" />
                <EditableField label="Personal Email" value={employee.personal_email}
                  onSave={(v) => handleFieldSave('personal_email', v)} type="email" />
                <EditableField label="Phone" value={employee.phone}
                  onSave={(v) => handleFieldSave('phone', v)} type="tel" />
                <EditableField label="Job Title" value={employee.job_title}
                  onSave={(v) => handleFieldSave('job_title', v)} />
                <EditableField label="Department" value={employee.department}
                  onSave={(v) => handleFieldSave('department', v)} />
                <EditableField label="Work State" value={employee.work_state}
                  onSave={(v) => handleFieldSave('work_state', v)} />
                <EditableField label="Work City" value={employee.work_city}
                  onSave={(v) => handleFieldSave('work_city', v)} />
                <EditableField label="Pay Classification" value={employee.pay_classification}
                  onSave={(v) => handleFieldSave('pay_classification', v)} />
                <EditableField label="Pay Rate" value={employee.pay_rate?.toString() ?? null}
                  onSave={(v) => handleFieldSave('pay_rate', v)} />
                <EditableField label="Start Date" value={employee.start_date}
                  onSave={(v) => handleFieldSave('start_date', v)} type="date" />
                <EditableField label="Address" value={employee.address}
                  onSave={(v) => handleFieldSave('address', v)} />
              </div>
            )}
            {tab === 'onboarding' && (
              <OnboardingTaskList employeeId={employeeId!} />
            )}
          </Card>
        </div>

        {/* Sidebar */}
        <div>
          <Card className="p-5">
            <h3 className="text-sm font-medium text-zinc-300 mb-4">Employee Details</h3>
            <dl className="space-y-3 text-sm">
              <div>
                <dt className="text-zinc-500 text-xs">Status</dt>
                <dd className="mt-1">
                  <Select
                    label=""
                    options={STATUS_OPTIONS}
                    value={employee.employment_status ?? 'active'}
                    onChange={(e) => updateStatus(e.target.value)}
                  />
                </dd>
              </div>
              <div>
                <dt className="text-zinc-500 text-xs">Start Date</dt>
                <dd className="text-zinc-200">
                  {employee.start_date ? new Date(employee.start_date).toLocaleDateString() : '—'}
                </dd>
              </div>
              {employee.termination_date && (
                <div>
                  <dt className="text-zinc-500 text-xs">Termination Date</dt>
                  <dd className="text-zinc-200">
                    {new Date(employee.termination_date).toLocaleDateString()}
                  </dd>
                </div>
              )}
              {employee.status_changed_at && (
                <div>
                  <dt className="text-zinc-500 text-xs">Status Changed</dt>
                  <dd className="text-zinc-200">
                    {new Date(employee.status_changed_at).toLocaleDateString()}
                  </dd>
                </div>
              )}
              <div>
                <dt className="text-zinc-500 text-xs">Created</dt>
                <dd className="text-zinc-200">
                  {new Date(employee.created_at).toLocaleDateString()}
                </dd>
              </div>
              <div>
                <dt className="text-zinc-500 text-xs">Updated</dt>
                <dd className="text-zinc-200">
                  {new Date(employee.updated_at).toLocaleDateString()}
                </dd>
              </div>
              <div>
                <dt className="text-zinc-500 text-xs">Invitation</dt>
                <dd className="flex items-center gap-2 mt-1">
                  <Badge variant={
                    employee.invitation_status === 'accepted' ? 'success' :
                    employee.invitation_status === 'sent' ? 'warning' : 'neutral'
                  }>
                    {employee.invitation_status ?? 'Not sent'}
                  </Badge>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleInvite}
                    disabled={inviting}
                  >
                    {inviting ? 'Sending...' : employee.invitation_status ? 'Resend' : 'Send Invite'}
                  </Button>
                </dd>
              </div>
              {employee.manager_name && (
                <div>
                  <dt className="text-zinc-500 text-xs">Manager</dt>
                  <dd className="text-zinc-200">{employee.manager_name}</dd>
                </div>
              )}
            </dl>
          </Card>

          <div className="mt-4">
            <Button
              variant="ghost"
              size="sm"
              className="text-red-400"
              onClick={async () => {
                if (confirm('Delete this employee? This cannot be undone.')) {
                  await deleteEmployee()
                  navigate('/app/employees')
                }
              }}
            >
              Delete Employee
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
