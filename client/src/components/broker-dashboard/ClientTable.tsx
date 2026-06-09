import { useNavigate } from 'react-router-dom'
import { Sparkles } from 'lucide-react'
import { Card } from '../ui'
import { DeltaPill } from '../broker/DeltaPill'
import { fmtMoney } from '../../utils/brokerFormat'
import type { BrokerCompanyMetric, WcPortfolioRow } from '../../types/broker'

const riskColors: Record<string, string> = {
  healthy: 'bg-emerald-500',
  watch: 'bg-amber-500',
  at_risk: 'bg-red-500',
}

const riskLabels: Record<string, string> = {
  healthy: 'Healthy',
  watch: 'Watch',
  at_risk: 'At Risk',
}

interface ClientTableProps {
  companies: BrokerCompanyMetric[]
  /** Per-company WC metrics (TRIR / DART / premium), keyed by company_id.
   *  Companies absent from the map render "—" for safety columns. */
  wcByCompany?: Map<string, WcPortfolioRow>
  /** Opens the consultative outreach drawer for a client. */
  onOutreach?: (companyId: string, companyName: string) => void
}

export function ClientTable({ companies, wcByCompany, onOutreach }: ClientTableProps) {
  const navigate = useNavigate()
  if (companies.length === 0) {
    return (
      <Card className="p-5">
        <h3 className="text-sm font-medium text-zinc-200 tracking-wide mb-4">Accounts</h3>
        <p className="text-sm text-zinc-500">No linked clients yet.</p>
      </Card>
    )
  }

  return (
    <Card className="p-5">
      <h3 className="text-sm font-medium text-zinc-200 tracking-wide mb-4">Accounts</h3>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-zinc-800/60">
              <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider">Account</th>
              <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider">Status</th>
              <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider text-right">FTE</th>
              <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider text-right">TRIR</th>
              <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider text-right">DART</th>
              <th className="pb-2 text-[11px] font-medium text-zinc-500 uppercase tracking-wider text-right">Premium Δ</th>
            </tr>
          </thead>
          <tbody>
            {companies.map((c) => {
              const wc = wcByCompany?.get(c.company_id)
              const trirRatio = wc?.benchmark && wc?.trir ? `${(wc.trir / wc.benchmark.trir).toFixed(1)}×` : null
              return (
                <tr
                  key={c.company_id}
                  className="border-b border-zinc-800/30 last:border-0 cursor-pointer hover:bg-zinc-800/50 transition-colors"
                  onClick={() => navigate(`/broker/clients/${c.company_id}`)}
                >
                  {/* Identity: name + industry */}
                  <td className="py-2.5 pr-4">
                    <div className="flex items-center gap-1.5">
                      <span className="text-zinc-200 font-medium">{c.company_name}</span>
                      {onOutreach && (
                        <button
                          type="button"
                          title="Outreach ideas"
                          onClick={(e) => { e.stopPropagation(); onOutreach(c.company_id, c.company_name) }}
                          className="text-zinc-700 hover:text-emerald-400 transition-colors"
                        >
                          <Sparkles className="w-3 h-3" />
                        </button>
                      )}
                    </div>
                    {(wc?.industry ?? wc?.benchmark?.label) && (
                      <div className="text-[11px] text-zinc-600">{wc?.benchmark?.label ?? wc?.industry}</div>
                    )}
                  </td>
                  <td className="py-2.5 pr-4">
                    <span className="inline-flex items-center gap-1.5 text-xs text-zinc-400">
                      <span className={`h-2 w-2 rounded-full ${riskColors[c.risk_signal] ?? 'bg-zinc-600'}`} />
                      {riskLabels[c.risk_signal] ?? c.risk_signal}
                    </span>
                  </td>
                  <td className="py-2.5 pr-4 text-right text-zinc-300 tabular-nums">
                    {wc?.headcount ?? c.active_employee_count}
                  </td>
                  {/* TRIR: value + ×bench + delta */}
                  <td className="py-2.5 pr-4 text-right">
                    {wc?.trir != null ? (
                      <>
                        <div className="font-mono text-[13px] text-zinc-100 tabular-nums">{wc.trir.toFixed(2)}</div>
                        {trirRatio && <div className="text-[9px] text-zinc-600 font-mono">{trirRatio} bench</div>}
                        <DeltaPill pct={wc.trir_delta_pct} />
                      </>
                    ) : (
                      <span className="text-zinc-700">—</span>
                    )}
                  </td>
                  {/* DART */}
                  <td className="py-2.5 pr-4 text-right font-mono text-[13px] text-zinc-300 tabular-nums">
                    {wc?.dart_rate != null ? wc.dart_rate.toFixed(2) : <span className="text-zinc-700">—</span>}
                  </td>
                  {/* Premium trajectory (directional $) */}
                  <td className="py-2.5 text-right">
                    {wc?.premium_impact ? (
                      <span className={`font-mono text-[12px] ${
                        wc.premium_impact.direction === 'increase' ? 'text-red-400'
                        : wc.premium_impact.direction === 'decrease' ? 'text-emerald-400'
                        : 'text-zinc-500'
                      }`}>
                        {wc.premium_impact.annual_impact_dollars > 0 ? '+' : ''}{fmtMoney(wc.premium_impact.annual_impact_dollars)}
                      </span>
                    ) : (
                      <span className="text-zinc-700">—</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
