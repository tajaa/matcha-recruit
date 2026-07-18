import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { RefreshCw, MapPin, Loader2 } from 'lucide-react'
import { adminOnboarding, type EnrichRosterResponse } from '../../../api/adminOnboarding'

export function EmployeeSyncPanel({ companyId }: { companyId: string }) {
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<EnrichRosterResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function run() {
    setBusy(true)
    setError(null)
    try {
      setResult(await adminOnboarding.enrichFromRoster(companyId))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Employee sync failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 mt-2">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <RefreshCw className="w-4 h-4 text-emerald-400" />
            <h3 className="text-sm font-medium text-zinc-200">Sync Employees → Gap Analysis</h3>
          </div>
          <p className="text-[11px] text-zinc-500 mt-1 max-w-md">
            Pull this company's employee work locations + roles, fill any new jurisdictions
            into the compliance engine, and re-scope. New locations are tracked weekly.
          </p>
        </div>
        <div className="shrink-0 flex items-center gap-2">
          <button
            onClick={() => navigate(`/admin/gap-analysis/company/${companyId}`)}
            className="text-xs px-3 py-2 rounded-lg border border-zinc-700 text-zinc-200 font-medium hover:bg-zinc-800 transition-colors"
          >
            Open Gap Dashboard →
          </button>
          <button
            onClick={run}
            disabled={busy}
            className="text-xs px-4 py-2 rounded-lg bg-emerald-600 text-white font-medium hover:bg-emerald-500 disabled:opacity-40 transition-colors inline-flex items-center gap-2"
          >
            {busy ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Syncing…</> : 'Sync Employees'}
          </button>
        </div>
      </div>

      {error && <p className="text-xs text-red-400 mt-3">{error}</p>}

      {result && (
        <div className="mt-4 border-t border-zinc-800 pt-4 space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              ['New jurisdictions', result.locations_filled, 'text-emerald-400'],
              ['Roles detected', result.employee_roles.length, 'text-blue-400'],
              ['Covered now', result.covered_count, 'text-zinc-100'],
              ['Gaps to research', result.missing_count, result.missing_count > 0 ? 'text-amber-400' : 'text-zinc-100'],
            ].map(([label, value, color]) => (
              <div key={label as string} className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3">
                <div className="text-[10px] text-zinc-500 uppercase tracking-wider">{label}</div>
                <div className={`text-xl font-semibold mt-1 ${color}`}>{value}</div>
              </div>
            ))}
          </div>

          {result.new_jurisdictions.length > 0 && (
            <div className="flex items-start gap-2 text-[11px] text-zinc-400">
              <MapPin className="w-3.5 h-3.5 text-emerald-400 mt-0.5 shrink-0" />
              <span>
                Added:{' '}
                {result.new_jurisdictions
                  .map((j) => `${j.city ? `${j.city}, ` : ''}${j.state}`)
                  .join(' · ')}
              </span>
            </div>
          )}
          {result.employee_roles.length > 0 && (
            <p className="text-[11px] text-zinc-500">Roles: {result.employee_roles.join(', ')}</p>
          )}

          <button
            onClick={() => navigate(`/admin/gap-analysis/company/${companyId}`)}
            className="text-[11px] font-medium text-emerald-400 hover:text-emerald-300"
          >
            Open gap dashboard →
          </button>
        </div>
      )}
    </div>
  )
}
