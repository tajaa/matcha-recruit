import { Button, Card, Badge } from '../ui'
import type { HandbookFreshnessCheck } from '../../types/handbook'

type Props = {
  check: HandbookFreshnessCheck | null
  running: boolean
  onRunCheck: () => void
}

export function HandbookFreshnessPanel({ check, running, onRunCheck }: Props) {
  return (
    <Card>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-zinc-300">Freshness Check</h3>
        <Button size="sm" variant="ghost" onClick={onRunCheck} disabled={running}>
          {running ? 'Running...' : 'Run Freshness Check'}
        </Button>
      </div>

      {!check ? (
        <p className="text-xs text-zinc-600">No freshness checks have been run yet.</p>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <Badge variant={check.is_outdated ? 'warning' : 'success'}>
              {check.is_outdated ? 'Outdated' : 'Up to date'}
            </Badge>
            {check.data_staleness_days != null && (
              <span className="text-xs text-zinc-500">{check.data_staleness_days} day(s) since last data update</span>
            )}
            <span className="text-xs text-zinc-600">
              Checked {new Date(check.checked_at).toLocaleString()}
            </span>
          </div>

          {check.impacted_sections > 0 && (
            <p className="text-xs text-zinc-400">
              {check.impacted_sections} section(s) impacted, {check.new_change_requests_count} new change request(s) created.
            </p>
          )}

          {check.findings.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-xs font-medium text-zinc-400">Findings</p>
              {check.findings.map((f, i) => (
                <div key={i} className="border border-zinc-800 rounded p-2 text-xs">
                  <div className="flex items-center gap-2 mb-1">
                    <Badge variant="neutral">{f.finding_type}</Badge>
                    {f.section_key && <span className="text-zinc-500">{f.section_key}</span>}
                  </div>
                  <p className="text-zinc-400">{f.summary}</p>
                  {f.effective_date && (
                    <p className="text-zinc-600 mt-0.5">Effective: {f.effective_date}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Card>
  )
}
