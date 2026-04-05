import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Input, Select } from '../../components/ui'
import { EmployeeStatusBadge } from '../../components/employees/EmployeeStatusBadge'
import { MultiBatchModal } from '../../components/employees/MultiBatchModal'
import { BulkUploadModal } from '../../components/employees/BulkUploadModal'
import { useEmployees } from '../../hooks/employees/useEmployees'
import { typeLabel } from '../../types/employee'

export default function Employees() {
  const navigate = useNavigate()
  const [status, setStatus] = useState('all')
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [department, setDepartment] = useState('')
  const [showBatch, setShowBatch] = useState(false)
  const [showUpload, setShowUpload] = useState(false)

  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  useEffect(() => {
    debounceRef.current = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(debounceRef.current)
  }, [search])

  const { employees, departments, onboardingProgress, loading, error, refetch } = useEmployees({
    status,
    search: debouncedSearch || undefined,
    department: department || undefined,
  })

  const deptOptions = [
    { value: '', label: 'All Departments' },
    ...departments.map((d) => ({ value: d, label: d })),
  ]

  return (
    <div>
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 sm:gap-0">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">
            Employees
          </h1>
          <p className="mt-2 text-sm text-zinc-500">
            {employees.length} total employee{employees.length !== 1 ? 's' : ''}
          </p>
        </div>
        <div className="flex gap-2 w-full sm:w-auto">
          <Button variant="ghost" onClick={() => setShowUpload(true)}>Upload CSV</Button>
          <Button onClick={() => setShowBatch(true)}>Add Employees</Button>
        </div>
      </div>

      <MultiBatchModal
        open={showBatch}
        onClose={() => setShowBatch(false)}
        onSuccess={refetch}
        departments={departments}
      />
      <BulkUploadModal
        open={showUpload}
        onClose={() => setShowUpload(false)}
        onSuccess={refetch}
      />

      {/* Filters */}
      <div className="mt-6 flex flex-col sm:flex-row items-start sm:items-center gap-3 sm:gap-4 flex-wrap">
        <Input
          label=""
          placeholder="Search by name or email..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        {departments.length > 0 && (
          <Select
            label=""
            options={deptOptions}
            value={department}
            onChange={(e) => setDepartment(e.target.value)}
            className="w-44"
          />
        )}
        <div className="flex gap-1 w-full sm:w-auto sm:ml-auto overflow-x-auto pb-2 sm:pb-0">
          {(['all', 'active', 'on_leave', 'terminated'] as const).map((s) => (
            <Button
              key={s}
              variant={status === s ? 'primary' : 'ghost'}
              size="sm"
              onClick={() => setStatus(s)}
            >
              {s === 'on_leave' ? 'On Leave' : s.charAt(0).toUpperCase() + s.slice(1)}
            </Button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="mt-6">
        {error ? (
          <p className="text-sm text-red-400">{error}</p>
        ) : loading ? (
          <p className="text-sm text-zinc-500">Loading...</p>
        ) : employees.length === 0 ? (
          <p className="text-sm text-zinc-500">No employees found.</p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-zinc-800">
            <table className="w-full text-sm text-left min-w-[800px]">
              <thead className="bg-zinc-900/50 text-zinc-400">
                <tr>
                  <th className="px-4 py-3 font-medium">Name</th>
                  <th className="px-4 py-3 font-medium">Title</th>
                  <th className="px-4 py-3 font-medium">Department</th>
                  <th className="px-4 py-3 font-medium">Type</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Onboarding</th>
                  <th className="px-4 py-3 font-medium">Start Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800">
                {employees.map((e) => {
                  const progress = onboardingProgress[e.id]
                  return (
                    <tr
                      key={e.id}
                      className="text-zinc-300 hover:bg-zinc-900/30 transition-colors cursor-pointer"
                      onClick={() => navigate(`/app/employees/${e.id}`)}
                    >
                      <td className="px-4 py-3">
                        <p className="font-medium text-zinc-100">
                          {e.first_name} {e.last_name}
                        </p>
                        <p className="text-xs text-zinc-500">
                          {e.work_email ?? e.personal_email ?? '—'}
                        </p>
                      </td>
                      <td className="px-4 py-3">{e.job_title ?? '—'}</td>
                      <td className="px-4 py-3">{e.department ?? '—'}</td>
                      <td className="px-4 py-3">{typeLabel[e.employment_type ?? ''] ?? '—'}</td>
                      <td className="px-4 py-3">
                        <EmployeeStatusBadge status={e.employment_status} />
                      </td>
                      <td className="px-4 py-3">
                        {progress?.has_onboarding ? (
                          <div className="flex items-center gap-2">
                            <div className="h-1.5 w-16 rounded-full bg-zinc-800 overflow-hidden">
                              <div
                                className="h-full rounded-full bg-emerald-500"
                                style={{ width: `${progress.total ? (progress.completed / progress.total) * 100 : 0}%` }}
                              />
                            </div>
                            <span className="text-xs text-zinc-500">
                              {progress.completed}/{progress.total}
                            </span>
                          </div>
                        ) : (
                          <span className="text-xs text-zinc-600">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-zinc-500">
                        {e.start_date ? new Date(e.start_date).toLocaleDateString() : '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
