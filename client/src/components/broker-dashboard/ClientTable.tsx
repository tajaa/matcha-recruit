import { useNavigate } from 'react-router-dom'
import { Card } from '../ui'
import type { BrokerCompanyMetric } from '../../types/broker'

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
}

export function ClientTable({ companies }: ClientTableProps) {
  const navigate = useNavigate()
  if (companies.length === 0) {
    return (
      <Card className="p-5">
        <h3 className="text-sm font-medium text-zinc-200 tracking-wide mb-4">Clients</h3>
        <p className="text-sm text-zinc-500">No linked clients yet.</p>
      </Card>
    )
  }

  return (
    <Card className="p-5">
      <h3 className="text-sm font-medium text-zinc-200 tracking-wide mb-4">Clients</h3>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-zinc-800/60">
              <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider">Company</th>
              <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider">Status</th>
              <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider text-right">Employees</th>
              <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider text-right">Compliance</th>
              <th className="pb-2 text-[11px] font-medium text-zinc-500 uppercase tracking-wider text-right">Open Actions</th>
            </tr>
          </thead>
          <tbody>
            {companies.map((c) => (
              <tr
                key={c.company_id}
                className="border-b border-zinc-800/30 last:border-0 cursor-pointer hover:bg-zinc-800/50 transition-colors"
                onClick={() => navigate(`/broker/clients/${c.company_id}`)}
              >
                <td className="py-2.5 pr-4 text-zinc-200 font-medium">{c.company_name}</td>
                <td className="py-2.5 pr-4">
                  <span className="inline-flex items-center gap-1.5 text-xs text-zinc-400">
                    <span className={`h-2 w-2 rounded-full ${riskColors[c.risk_signal] ?? 'bg-zinc-600'}`} />
                    {riskLabels[c.risk_signal] ?? c.risk_signal}
                  </span>
                </td>
                <td className="py-2.5 pr-4 text-right text-zinc-300 tabular-nums font-[Space_Grotesk]">
                  {c.active_employee_count}
                </td>
                <td className="py-2.5 pr-4 text-right">
                  <span className={`tabular-nums font-[Space_Grotesk] ${
                    c.policy_compliance_rate >= 80 ? 'text-emerald-400' :
                    c.policy_compliance_rate >= 50 ? 'text-amber-400' : 'text-red-400'
                  }`}>
                    {Math.round(c.policy_compliance_rate)}%
                  </span>
                </td>
                <td className={`py-2.5 text-right tabular-nums font-[Space_Grotesk] ${
                  c.open_action_items > 0 ? 'text-amber-400' : 'text-zinc-500'
                }`}>
                  {c.open_action_items}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
