import { Card } from '../../../components/ui'
import type { BrokerClientDetailResponse } from '../../../types/broker'
import { complianceColor } from './shared'

export function PoliciesTab({
  policies,
  handbooks,
}: {
  policies: BrokerClientDetailResponse['policies']
  handbooks: BrokerClientDetailResponse['handbooks']
}) {
  return (
    <div className="space-y-6">
      {/* Policy table */}
      <Card className="p-5">
        <h3 className="text-sm font-medium text-zinc-200 tracking-wide mb-4">Policies</h3>
        {policies.items.length === 0 ? (
          <p className="text-sm text-zinc-500">No policies configured.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-800/60">
                  <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider">Title</th>
                  <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider">Category</th>
                  <th className="pb-2 pr-4 text-[11px] font-medium text-zinc-500 uppercase tracking-wider text-right">Signatures</th>
                  <th className="pb-2 text-[11px] font-medium text-zinc-500 uppercase tracking-wider text-right">Rate</th>
                </tr>
              </thead>
              <tbody>
                {policies.items.map((p) => (
                  <tr key={p.id} className="border-b border-zinc-800/30 last:border-0">
                    <td className="py-2.5 pr-4 text-zinc-200 font-medium">{p.title}</td>
                    <td className="py-2.5 pr-4 text-zinc-400 text-xs">{p.category ?? '—'}</td>
                    <td className="py-2.5 pr-4 text-right text-zinc-300 tabular-nums">
                      {p.signed_count}/{p.total_count}
                    </td>
                    <td className="py-2.5 text-right">
                      <span className={`tabular-nums ${complianceColor(p.signature_rate)}`}>
                        {Math.round(p.signature_rate)}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Handbook coverage */}
      <Card className="p-5">
        <h3 className="text-sm font-medium text-zinc-200 tracking-wide mb-4">Handbook Coverage</h3>
        {handbooks.length === 0 ? (
          <p className="text-sm text-zinc-500">No handbooks found.</p>
        ) : (
          <div className="space-y-3">
            {handbooks.map((h) => {
              const strengthColor =
                h.strength_label === 'Strong' ? 'text-zinc-100' :
                h.strength_label === 'Moderate' ? 'text-zinc-400' : 'text-zinc-600'
              return (
                <div key={h.handbook_id} className="flex items-center justify-between py-2 border-b border-zinc-800/30 last:border-0">
                  <div>
                    <p className="text-sm text-zinc-200">{h.handbook_title}</p>
                    <p className="text-xs text-zinc-500 mt-0.5">{h.total_sections} sections, {h.state_count} states</p>
                  </div>
                  <div className="text-right">
                    <p className={`text-sm font-medium ${strengthColor}`}>
                      {Math.round(h.strength_score)}%
                    </p>
                    <p className={`text-xs ${strengthColor}`}>{h.strength_label}</p>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </Card>
    </div>
  )
}
