import { AlertTriangle, Building2 } from 'lucide-react'
import { Card } from '../../../components/ui'
import type { BrokerClientDetailResponse } from '../../../types/broker'
import { severityColors } from './shared'

export function IRERTab({
  ir,
  er,
}: {
  ir: BrokerClientDetailResponse['ir_summary']
  er: BrokerClientDetailResponse['er_summary']
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {/* Incidents */}
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-4">
          <AlertTriangle className="h-4 w-4 text-zinc-500" />
          <h3 className="text-sm font-medium text-zinc-200 tracking-wide">Incidents</h3>
        </div>
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-zinc-500">Total Open</span>
            <span className="text-sm font-medium text-zinc-200">{ir.total_open}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs text-zinc-500">Last 30 Days</span>
            <span className="text-sm font-medium text-zinc-200">{ir.recent_30_days}</span>
          </div>
          {Object.keys(ir.by_severity).length > 0 && (
            <div className="pt-2 border-t border-zinc-800/40">
              <p className="text-[11px] text-zinc-500 uppercase tracking-wider mb-2">By Severity</p>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(ir.by_severity).map(([sev, count]) => (
                  <span
                    key={sev}
                    className={`inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full ${
                      severityColors[sev] ?? 'bg-zinc-700 text-zinc-300'
                    }`}
                  >
                    {sev}: <span className="">{count}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </Card>

      {/* ER Cases */}
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-4">
          <Building2 className="h-4 w-4 text-zinc-500" />
          <h3 className="text-sm font-medium text-zinc-200 tracking-wide">ER Cases</h3>
        </div>
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-zinc-500">Total Open</span>
            <span className="text-sm font-medium text-zinc-200">{er.total_open}</span>
          </div>
          {Object.keys(er.by_status).length > 0 && (
            <div className="pt-2 border-t border-zinc-800/40">
              <p className="text-[11px] text-zinc-500 uppercase tracking-wider mb-2">By Status</p>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(er.by_status).map(([status, count]) => (
                  <span
                    key={status}
                    className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-300"
                  >
                    {status}: <span className="">{count}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}
