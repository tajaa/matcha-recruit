import { useEffect, useState } from 'react'
import { Badge, Button, Input } from '../../components/ui'
import { api } from '../../api/client'

type Employee = {
  id: string
  first_name: string
  last_name: string
  work_email: string | null
  personal_email: string | null
  job_title: string | null
  department: string | null
  employment_type: string | null
  employment_status: string | null
  start_date: string | null
}

const statusBadge = (status: string | null) => {
  switch (status) {
    case 'active': return <Badge variant="success">Active</Badge>
    case 'on_leave': return <Badge variant="warning">On Leave</Badge>
    case 'terminated':
    case 'offboarded': return <Badge variant="danger">{status === 'terminated' ? 'Terminated' : 'Offboarded'}</Badge>
    case 'suspended': return <Badge variant="danger">Suspended</Badge>
    default: return <Badge variant="neutral">{status ?? 'Active'}</Badge>
  }
}

const typeLabel = (t: string | null) => {
  switch (t) {
    case 'full_time': return 'Full-time'
    case 'part_time': return 'Part-time'
    case 'contractor': return 'Contractor'
    default: return '—'
  }
}

export default function Employees() {
  const [employees, setEmployees] = useState<Employee[]>([])
  const [filter, setFilter] = useState<'all' | 'active' | 'on_leave' | 'terminated'>('all')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    const params = filter !== 'all' ? `?employment_status=${filter}` : ''
    api.get<Employee[]>(`/employees${params}`)
      .then(setEmployees)
      .catch(() => setEmployees([]))
      .finally(() => setLoading(false))
  }, [filter])

  const filtered = employees.filter((e) => {
    const name = `${e.first_name} ${e.last_name}`.toLowerCase()
    const email = (e.work_email ?? e.personal_email ?? '').toLowerCase()
    const q = search.toLowerCase()
    return name.includes(q) || email.includes(q)
  })

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 font-[Space_Grotesk]">
            Employees
          </h1>
          <p className="mt-2 text-sm text-zinc-500">
            {employees.length} total employee{employees.length !== 1 ? 's' : ''}
          </p>
        </div>
        <Button>Add Employee</Button>
      </div>

      {/* Filters */}
      <div className="mt-6 flex items-center gap-3">
        <Input
          label=""
          placeholder="Search by name or email..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <div className="flex gap-1 ml-auto">
          {(['all', 'active', 'on_leave', 'terminated'] as const).map((s) => (
            <Button
              key={s}
              variant={filter === s ? 'primary' : 'ghost'}
              size="sm"
              onClick={() => setFilter(s)}
            >
              {s === 'on_leave' ? 'On Leave' : s.charAt(0).toUpperCase() + s.slice(1)}
            </Button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="mt-6">
        {loading ? (
          <p className="text-sm text-zinc-500">Loading...</p>
        ) : filtered.length === 0 ? (
          <p className="text-sm text-zinc-500">No employees found.</p>
        ) : (
          <div className="overflow-hidden rounded-xl border border-zinc-800">
            <table className="w-full text-sm text-left">
              <thead className="bg-zinc-900/50 text-zinc-400">
                <tr>
                  <th className="px-4 py-3 font-medium">Name</th>
                  <th className="px-4 py-3 font-medium">Title</th>
                  <th className="px-4 py-3 font-medium">Department</th>
                  <th className="px-4 py-3 font-medium">Type</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800">
                {filtered.map((e) => (
                  <tr key={e.id} className="text-zinc-300 hover:bg-zinc-900/30 transition-colors">
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
                    <td className="px-4 py-3">{typeLabel(e.employment_type)}</td>
                    <td className="px-4 py-3">{statusBadge(e.employment_status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
