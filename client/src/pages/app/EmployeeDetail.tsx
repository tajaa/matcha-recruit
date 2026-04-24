import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Badge, Button, Card, Input, Select } from '../../components/ui'
import { EmployeeStatusBadge } from '../../components/employees/EmployeeStatusBadge'
import { OnboardingTaskList } from '../../components/employees/OnboardingTaskList'
import { CredentialManager } from '../../components/employees/CredentialManager'
import { useEmployeeDetail } from '../../hooks/employees/useEmployeeDetail'
import { typeLabel, statusLabel } from '../../types/employee'

const STATUS_OPTIONS = Object.entries(statusLabel).map(([value, label]) => ({ value, label }))

type Tab = 'profile' | 'onboarding' | 'credentials'

type FieldOption = { value: string; label: string }
type ProfileField = { key: string; label: string; type?: string; options?: FieldOption[] }

const PAY_CLASSIFICATION_OPTIONS: FieldOption[] = [
  { value: 'hourly', label: 'Hourly' },
  { value: 'exempt', label: 'Exempt (Salary)' },
]

const PROFILE_FIELDS: ProfileField[] = [
  { key: 'first_name', label: 'First Name' },
  { key: 'last_name', label: 'Last Name' },
  { key: 'work_email', label: 'Work Email', type: 'email' },
  { key: 'personal_email', label: 'Personal Email', type: 'email' },
  { key: 'phone', label: 'Phone', type: 'tel' },
  { key: 'job_title', label: 'Job Title' },
  { key: 'department', label: 'Department' },
  { key: 'work_state', label: 'Work State' },
  { key: 'work_city', label: 'Work City' },
  { key: 'pay_classification', label: 'Pay Classification', type: 'select', options: PAY_CLASSIFICATION_OPTIONS },
  { key: 'pay_rate', label: 'Pay Rate' },
  { key: 'start_date', label: 'Start Date', type: 'date' },
  { key: 'address', label: 'Address' },
]

function getFieldValue(employee: Record<string, unknown>, key: string): string {
  const v = employee[key]
  if (v == null) return ''
  return String(v)
}

export default function EmployeeDetail() {
  const { employeeId } = useParams<{ employeeId: string }>()
  const navigate = useNavigate()
  const {
    employee, loading, error,
    updateEmployee, updateStatus, deleteEmployee,
  } = useEmployeeDetail(employeeId!)
  const [tab, setTab] = useState<Tab>('profile')
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')

  if (loading) return <p className="text-sm text-zinc-500">Loading employee...</p>
  if (error) return <p className="text-sm text-red-400">{error}</p>
  if (!employee) return <p className="text-sm text-zinc-500">Employee not found.</p>

  function startEditing() {
    const initial: Record<string, string> = {}
    for (const f of PROFILE_FIELDS) {
      initial[f.key] = getFieldValue(employee as unknown as Record<string, unknown>, f.key)
    }
    setDraft(initial)
    setSaveError('')
    setEditing(true)
  }

  function cancelEditing() {
    setDraft({})
    setSaveError('')
    setEditing(false)
  }

  async function handleSave() {
    const changes: Record<string, string | null> = {}
    for (const f of PROFILE_FIELDS) {
      const original = getFieldValue(employee as unknown as Record<string, unknown>, f.key)
      const edited = (draft[f.key] ?? '').trim()
      if (edited !== original) {
        changes[f.key] = edited || null
      }
    }
    if (Object.keys(changes).length === 0) {
      setEditing(false)
      return
    }
    setSaving(true)
    setSaveError('')
    try {
      await updateEmployee(changes)
      setEditing(false)
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <Link to="/app/employees" className="text-zinc-500 hover:text-zinc-300 transition-colors">
          &larr;
        </Link>
        <h1 className="text-xl font-semibold text-zinc-100">
          {employee.first_name} {employee.last_name}
        </h1>
        <EmployeeStatusBadge status={employee.employment_status} />
        {employee.employment_type && (
          <Badge variant="neutral">
            {typeLabel[employee.employment_type] ?? employee.employment_type}
          </Badge>
        )}
        {!editing && tab === 'profile' && (
          <Button variant="ghost" size="sm" onClick={startEditing}>
            Edit Profile
          </Button>
        )}
      </div>

      {/* Layout: 2/3 main + 1/3 sidebar */}
      <div className="grid grid-cols-3 gap-6">
        {/* Main column */}
        <div className="col-span-2">
          {/* Tabs */}
          <div className="flex gap-1 mb-4">
            {(['profile', 'onboarding', 'credentials'] as const).map((t) => (
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
              <>
                <div className="grid grid-cols-2 gap-x-8 gap-y-4">
                  {PROFILE_FIELDS.map((f) => {
                    const value = getFieldValue(employee as unknown as Record<string, unknown>, f.key)
                    if (editing) {
                      if (f.type === 'select' && f.options) {
                        return (
                          <div key={f.key}>
                            <Select
                              label={f.label}
                              options={f.options}
                              placeholder="— Select —"
                              value={draft[f.key] ?? ''}
                              onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))}
                              className="text-sm"
                            />
                          </div>
                        )
                      }
                      return (
                        <div key={f.key}>
                          <Input
                            label={f.label}
                            type={f.type ?? 'text'}
                            value={draft[f.key] ?? ''}
                            onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))}
                            className="text-sm"
                          />
                        </div>
                      )
                    }
                    const displayValue = f.options?.find((o) => o.value === value)?.label ?? value
                    return (
                      <div key={f.key}>
                        <dt className="text-zinc-500 text-xs">{f.label}</dt>
                        <dd className="text-zinc-200 text-sm mt-0.5">
                          {displayValue || <span className="text-zinc-600 italic">Not set</span>}
                        </dd>
                      </div>
                    )
                  })}
                </div>
                {editing && (
                  <div className="flex items-center gap-3 mt-6 pt-4 border-t border-zinc-800">
                    {saveError && <p className="text-sm text-red-400 mr-auto">{saveError}</p>}
                    <div className="ml-auto flex gap-2">
                      <Button variant="ghost" size="sm" onClick={cancelEditing} disabled={saving}>
                        Cancel
                      </Button>
                      <Button variant="primary" size="sm" onClick={handleSave} disabled={saving}>
                        {saving ? 'Saving...' : 'Save Changes'}
                      </Button>
                    </div>
                  </div>
                )}
              </>
            )}
            {tab === 'onboarding' && (
              <OnboardingTaskList employeeId={employeeId!} />
            )}
            {tab === 'credentials' && (
              <CredentialManager employeeId={employeeId!} />
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
