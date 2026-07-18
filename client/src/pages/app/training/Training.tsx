import { useState } from 'react'
import { Link } from 'react-router-dom'
import { GraduationCap, AlertTriangle, CheckCircle2, Loader2, Users } from 'lucide-react'
import { Card, Button, Badge } from '../../../components/ui'
import { useTrainingCompliance } from '../../../hooks/training/useTrainingCompliance'
import { trainingApi, type TrainingRequirement } from '../../../api/hr/training'

function variantLabel(applies_to: TrainingRequirement['applies_to']): string {
  if (applies_to === 'supervisor') return 'Supervisors'
  if (applies_to === 'nonsupervisor') return 'Employees'
  return 'All staff'
}

function jurisdictionLabel(j: string | null): string {
  return j ? j.toUpperCase() : '—'
}

export default function Training() {
  const { compliance, overdue, requirements, loading, error, refetch } = useTrainingCompliance()
  const [assigning, setAssigning] = useState<string | null>(null)
  const [assignResult, setAssignResult] = useState<{ id: string; count: number } | null>(null)
  const [assignError, setAssignError] = useState<string | null>(null)

  async function handleAssign(req_id: string) {
    setAssigning(req_id)
    setAssignError(null)
    try {
      const res = await trainingApi.bulkAssign(req_id)
      setAssignResult({ id: req_id, count: res.assigned_count })
      void refetch()
    } catch (e) {
      setAssignError(e instanceof Error ? e.message : 'Assignment failed')
    } finally {
      setAssigning(null)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-zinc-500">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading training data…
      </div>
    )
  }

  if (error) {
    return <p className="text-sm text-red-400">{error}</p>
  }

  // Build a map of requirement_id → compliance summary
  const byReq = new Map(compliance.map((c) => [c.requirement_id, c]))

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-zinc-800 border border-zinc-700 flex items-center justify-center">
          <GraduationCap className="w-5 h-5 text-zinc-300" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">Training</h1>
          <p className="text-xs text-zinc-500">
            Required workforce trainings — assign, track, and store certifications.
          </p>
        </div>
      </div>

      {assignResult && (
        <Card className="p-4 mb-4 bg-emerald-500/5 border-emerald-500/20">
          <div className="flex items-center gap-2 text-sm text-emerald-300">
            <CheckCircle2 className="w-4 h-4" />
            Assigned to {assignResult.count} matching employee(s).
          </div>
        </Card>
      )}
      {assignError && (
        <Card className="p-4 mb-4 bg-red-500/5 border-red-500/20">
          <div className="flex items-center gap-2 text-sm text-red-300">
            <AlertTriangle className="w-4 h-4" />
            {assignError}
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <Card className="p-4">
          <div className="text-xs text-zinc-500 uppercase tracking-wider">Requirements</div>
          <div className="text-2xl font-semibold text-zinc-100 mt-1">{requirements.length}</div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-zinc-500 uppercase tracking-wider">Active assignments</div>
          <div className="text-2xl font-semibold text-zinc-100 mt-1">
            {compliance.reduce((acc, c) => acc + (c.total_assigned - c.completed), 0)}
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-zinc-500 uppercase tracking-wider">Overdue</div>
          <div className="text-2xl font-semibold text-amber-400 mt-1">{overdue.length}</div>
        </Card>
      </div>

      <h2 className="text-sm font-semibold text-zinc-300 mb-3">Required trainings</h2>
      <div className="space-y-3 mb-8">
        {requirements.length === 0 && (
          <Card className="p-6 text-sm text-zinc-500">
            No training requirements yet. Matcha-Lite tenants get CA SB 1343
            harassment-prevention requirements seeded automatically once the
            content templates are generated. Run{' '}
            <code className="bg-zinc-800 px-1 rounded">
              python -m scripts.generate_training_templates
            </code>{' '}
            to seed.
          </Card>
        )}
        {requirements.map((req) => {
          const summary = byReq.get(req.id)
          const total = summary?.total_assigned ?? 0
          const completed = summary?.completed ?? 0
          const overdueCount = summary?.overdue ?? 0
          return (
            <Card key={req.id} className="p-5">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <Link
                      to={`/app/training/${req.id}`}
                      className="text-base font-medium text-zinc-100 hover:text-emerald-400"
                    >
                      {req.title}
                    </Link>
                    <Badge variant="neutral">{jurisdictionLabel(req.jurisdiction)}</Badge>
                    <Badge variant="neutral">{variantLabel(req.applies_to)}</Badge>
                    {req.frequency_months ? (
                      <Badge variant="neutral">Every {Math.round(req.frequency_months / 12)} yr</Badge>
                    ) : null}
                  </div>
                  <div className="flex items-center gap-4 text-xs text-zinc-500">
                    <span className="flex items-center gap-1">
                      <Users className="w-3 h-3" /> {total} assigned
                    </span>
                    <span>{completed} completed</span>
                    {overdueCount > 0 && (
                      <span className="text-amber-400">{overdueCount} overdue</span>
                    )}
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={assigning === req.id}
                  onClick={() => handleAssign(req.id)}
                >
                  {assigning === req.id ? 'Assigning…' : 'Assign to matching employees'}
                </Button>
              </div>
            </Card>
          )
        })}
      </div>

      {overdue.length > 0 && (
        <>
          <h2 className="text-sm font-semibold text-zinc-300 mb-3 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400" />
            Overdue
          </h2>
          <Card className="overflow-x-auto">
            <table className="w-full text-sm min-w-[500px]">
              <thead className="bg-zinc-900/50 text-xs uppercase text-zinc-500">
                <tr>
                  <th className="text-left px-4 py-2 font-medium">Employee</th>
                  <th className="text-left px-4 py-2 font-medium">Training</th>
                  <th className="text-left px-4 py-2 font-medium">Due</th>
                  <th className="text-left px-4 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800">
                {overdue.map((row) => (
                  <tr key={row.record_id}>
                    <td className="px-4 py-2 text-zinc-200">
                      {row.first_name} {row.last_name}
                      <div className="text-xs text-zinc-500">{row.email}</div>
                    </td>
                    <td className="px-4 py-2 text-zinc-200">{row.training_title}</td>
                    <td className="px-4 py-2 text-zinc-400">{row.due_date}</td>
                    <td className="px-4 py-2">
                      <Badge variant="warning">{row.status}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </div>
  )
}
