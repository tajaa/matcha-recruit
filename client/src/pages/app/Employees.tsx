import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Button, Input, Select } from '../../components/ui'
import { EmployeeStatusBadge } from '../../components/employees/EmployeeStatusBadge'
import { MultiBatchModal } from '../../components/employees/MultiBatchModal'
import { BulkUploadModal } from '../../components/employees/BulkUploadModal'
import { HRISSyncModal } from '../../components/employees/HRISSyncModal'
import { useMe } from '../../hooks/useMe'
import { WageGapCard, WageGapDrawer, FlightRiskCard, FlightRiskDrawer, RetentionExplainer } from '../../components/dashboard'
import { fetchDashboardStats } from '../../api/hr/dashboard'
import { useEmployees } from '../../hooks/employees/useEmployees'
import { typeLabel } from '../../types/employee'
import { LABEL } from '../../components/ui/typography'
import type { WageGapSummary, FlightRiskWidgetSummary } from '../../types/dashboard'

export default function Employees() {
  const navigate = useNavigate()
  const { me, hasFeature } = useMe()
  // Standard Lite without an HRIS flag sees a teaser routing to the add-ons
  // section (HRIS sync is a self-serve Lite add-on; essentials has no roster).
  const showHrisUpsell =
    me?.profile?.signup_source === 'matcha_lite' &&
    !hasFeature('hris_gusto') && !hasFeature('hris_finch') && !hasFeature('hris_import')
  // One-time welcome after the Essentials → Lite upgrade redirect.
  const [searchParams, setSearchParams] = useSearchParams()
  const [showUpgradeBanner, setShowUpgradeBanner] = useState(searchParams.get('upgraded') === '1')
  function dismissUpgradeBanner() {
    setShowUpgradeBanner(false)
    searchParams.delete('upgraded')
    setSearchParams(searchParams, { replace: true })
  }
  const [status, setStatus] = useState('all')
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [department, setDepartment] = useState('')
  const [showBatch, setShowBatch] = useState(false)
  const [showUpload, setShowUpload] = useState(false)
  const [showHRIS, setShowHRIS] = useState(false)
  const [wageGap, setWageGap] = useState<WageGapSummary | null>(null)
  const [wageDrawerOpen, setWageDrawerOpen] = useState(false)
  const [flightRisk, setFlightRisk] = useState<FlightRiskWidgetSummary | null>(null)
  const [flightDrawerOpen, setFlightDrawerOpen] = useState(false)

  useEffect(() => {
    // Reuse dashboard stats endpoint — it already computes wage_gap_summary
    // and flight_risk_summary, both Redis-cached, so a second caller is cheap.
    fetchDashboardStats()
      .then((s) => {
        setWageGap(s.wage_gap_summary)
        setFlightRisk(s.flight_risk_summary)
      })
      .catch(() => { setWageGap(null); setFlightRisk(null) })
  }, [])

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
      {showUpgradeBanner && (
        <div className="mb-6 flex items-start justify-between gap-4 rounded-lg border border-emerald-500/30 bg-emerald-500/[0.07] px-4 py-3">
          <div>
            <p className="text-sm font-medium text-emerald-300">Welcome to Matcha Lite</p>
            <p className="mt-0.5 text-xs text-zinc-400">
              Import your roster to unlock OSHA logs and the full insight suite — upload a CSV or add employees below.
            </p>
          </div>
          <button
            type="button"
            onClick={dismissUpgradeBanner}
            className="text-zinc-500 hover:text-zinc-300 text-sm leading-none transition-colors"
            aria-label="Dismiss"
          >
            &times;
          </button>
        </div>
      )}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 sm:gap-0">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">
            Employees
          </h1>
          <p className={`mt-2 flex items-center gap-1.5 ${LABEL}`}>
            <span className="font-mono text-xs font-semibold normal-case tracking-normal text-emerald-400">{employees.length}</span>
            total employee{employees.length !== 1 ? 's' : ''}
          </p>
        </div>
        <div className="flex gap-2 w-full sm:w-auto flex-wrap">
          <Button variant="ghost" onClick={() => setShowUpload(true)}>Upload CSV</Button>
          {(hasFeature('hris_gusto') || hasFeature('hris_finch') || hasFeature('hris_import')) && (
            <Button variant="ghost" onClick={() => setShowHRIS(true)}>Sync from HRIS</Button>
          )}
          {showHrisUpsell && (
            <Button variant="ghost" onClick={() => navigate('/app/company#addons')}>
              Sync from HRIS
              <span className="ml-1.5 text-[8.5px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/20 leading-none">
                Add-on
              </span>
            </Button>
          )}
          <Button onClick={() => setShowBatch(true)}>Add Employees</Button>
        </div>
      </div>

      {/* Wage gap widget — moved here from Command Center because it's
          an employee-comp tool. Hidden until the backend has hourly data
          to evaluate. */}
      {(wageGap || flightRisk) && (
        <>
          <div className="mt-6 grid gap-4 md:grid-cols-2">
            {wageGap && (
              <WageGapCard
                data={wageGap}
                onOpenDetails={() => setWageDrawerOpen(true)}
              />
            )}
            {flightRisk && (
              <FlightRiskCard
                data={flightRisk}
                onOpenDetails={() => setFlightDrawerOpen(true)}
              />
            )}
          </div>
          <RetentionExplainer />
        </>
      )}
      {wageGap && (
        <WageGapDrawer
          open={wageDrawerOpen}
          onClose={() => setWageDrawerOpen(false)}
          summary={wageGap}
        />
      )}
      {flightRisk && (
        <FlightRiskDrawer
          open={flightDrawerOpen}
          onClose={() => setFlightDrawerOpen(false)}
          summary={flightRisk}
        />
      )}

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
      <HRISSyncModal
        open={showHRIS}
        onClose={() => setShowHRIS(false)}
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
          <div className="overflow-x-auto rounded-xl border border-white/[0.06] bg-zinc-950">
            <table className="w-full text-sm text-left min-w-[800px]">
              <thead>
                <tr className="border-b border-white/[0.06]">
                  <th className={`px-4 py-3 ${LABEL}`}>Name</th>
                  <th className={`px-4 py-3 ${LABEL}`}>Title</th>
                  <th className={`px-4 py-3 ${LABEL}`}>Department</th>
                  <th className={`px-4 py-3 ${LABEL}`}>Type</th>
                  <th className={`px-4 py-3 ${LABEL}`}>Status</th>
                  <th className={`px-4 py-3 ${LABEL}`}>Onboarding</th>
                  <th className={`px-4 py-3 ${LABEL}`}>Start Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.06]">
                {employees.map((e) => {
                  const progress = onboardingProgress[e.id]
                  return (
                    <tr
                      key={e.id}
                      className="text-zinc-300 hover:bg-white/[0.02] transition-colors cursor-pointer"
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
                            <div className="h-1.5 w-16 rounded-full bg-white/[0.06] overflow-hidden">
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
