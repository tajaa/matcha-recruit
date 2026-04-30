import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Badge, Button, Input, Select } from '../../components/ui'
import { Plus, Loader2, Gavel, Settings } from 'lucide-react'
import { useDisciplineList } from '../../hooks/discipline/useDiscipline'
import IssueDisciplineModal from '../../features/discipline/IssueDisciplineModal'
import { api } from '../../api/client'
import type {
  DisciplineLevel,
  DisciplineStatus,
} from '../../api/discipline'

const LEVEL_LABEL: Record<DisciplineLevel, string> = {
  verbal_warning: 'Verbal',
  written_warning: 'Written',
  pip: 'PIP',
  final_warning: 'Final',
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

const STATUS_LABEL: Record<DisciplineStatus, string> = {
  draft: 'Draft',
  pending_meeting: 'Pending Meeting',
  pending_signature: 'Pending Signature',
  active: 'Active',
  completed: 'Completed',
  expired: 'Expired',
  escalated: 'Escalated',
}

type EmployeeRow = { id: string; first_name: string | null; last_name: string | null }

function employeeName(e: EmployeeRow | undefined, fallbackId: string): string {
  if (!e) return fallbackId.slice(0, 8)
  const n = [e.first_name || '', e.last_name || ''].join(' ').trim()
  return n || fallbackId.slice(0, 8)
}

export default function Discipline() {
  const navigate = useNavigate()
  const [statusFilter, setStatusFilter] = useState<DisciplineStatus | ''>('active')
  const [search, setSearch] = useState('')
  const [showIssue, setShowIssue] = useState(false)
  const [employees, setEmployees] = useState<Record<string, EmployeeRow>>({})

  const { records, loading, error, refetch } = useDisciplineList(
    (statusFilter || undefined) as DisciplineStatus | undefined,
  )

  useEffect(() => {
    api.get<EmployeeRow[]>('/employees')
      .then((rows) => {
        const map: Record<string, EmployeeRow> = {}
        for (const r of rows || []) map[r.id] = r
        setEmployees(map)
      })
      .catch(() => setEmployees({}))
  }, [])

  const filtered = useMemo(() => {
    const s = search.trim().toLowerCase()
    if (!s) return records
    return records.filter((r) => {
      const name = employeeName(employees[r.employee_id], r.employee_id).toLowerCase()
      return (
        name.includes(s) ||
        r.discipline_type.includes(s) ||
        (r.infraction_type || '').includes(s)
      )
    })
  }, [records, search, employees])

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-zinc-100">
            <Gavel className="w-5 h-5" />
            Performance Action
          </h1>
          <p className="text-sm text-zinc-500 mt-1">
            Issue progressive performance action records, track signatures, and manage escalation.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={() => navigate('/app/discipline-settings')}>
            <Settings className="w-4 h-4" />
            <span className="ml-2">Settings</span>
          </Button>
          <Button onClick={() => setShowIssue(true)}>
            <Plus className="w-4 h-4" />
            <span className="ml-2">New record</span>
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <Select
          label="Status"
          options={[
            { value: '', label: 'All' },
            { value: 'active', label: 'Active' },
            { value: 'pending_meeting', label: 'Pending meeting' },
            { value: 'pending_signature', label: 'Pending signature' },
            { value: 'expired', label: 'Expired' },
            { value: 'escalated', label: 'Escalated' },
            { value: 'completed', label: 'Completed' },
          ]}
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as DisciplineStatus | '')}
        />
        <Input
          label="Search"
          placeholder="Employee, infraction…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <Button variant="ghost" onClick={refetch}>Refresh</Button>
      </div>

      {error && <div className="text-sm text-red-400">{error}</div>}

      <div className="rounded-lg border border-zinc-800 bg-zinc-950 overflow-hidden">
        {loading ? (
          <div className="p-8 flex items-center justify-center text-zinc-400">
            <Loader2 className="w-5 h-5 animate-spin" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-8 text-center text-zinc-500 text-sm">
            No performance action records match the current filters.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-zinc-900 text-zinc-400 text-xs uppercase tracking-wide">
              <tr>
                <th className="text-left px-4 py-3">Employee</th>
                <th className="text-left px-4 py-3">Level</th>
                <th className="text-left px-4 py-3">Infraction</th>
                <th className="text-left px-4 py-3">Issued</th>
                <th className="text-left px-4 py-3">Expires</th>
                <th className="text-left px-4 py-3">Signature</th>
                <th className="text-left px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr
                  key={r.id}
                  className="border-t border-zinc-900 hover:bg-zinc-900/40 cursor-pointer"
                  onClick={() => navigate(`/app/discipline/${r.id}`)}
                >
                  <td className="px-4 py-3 text-zinc-200">
                    {employeeName(employees[r.employee_id], r.employee_id)}
                  </td>
                  <td className="px-4 py-3 text-zinc-300">
                    {LEVEL_LABEL[r.discipline_type]}
                    {r.override_level && (
                      <span className="ml-2 text-xs text-amber-400">override</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-zinc-400">
                    {(r.infraction_type || '').replace(/_/g, ' ')}
                  </td>
                  <td className="px-4 py-3 text-zinc-400">
                    {new Date(r.issued_date).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-zinc-500">
                    {r.expires_at ? new Date(r.expires_at).toLocaleDateString() : '—'}
                  </td>
                  <td className="px-4 py-3 text-zinc-400">{r.signature_status}</td>
                  <td className="px-4 py-3">
                    <Badge variant={STATUS_VARIANT[r.status]}>{STATUS_LABEL[r.status]}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <IssueDisciplineModal
        open={showIssue}
        onClose={() => setShowIssue(false)}
        onIssued={() => { refetch() }}
      />
    </div>
  )
}
