import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sparkles, ChevronUp, ChevronDown } from 'lucide-react'
import { DeltaPill } from '../DeltaPill'
import { RenewalPill } from '../RenewalPill'
import { HelpHint } from '../HelpHint'
import { LABEL } from '../../ui/typography'
import { fmtMoney, fmtDate, daysUntilDate, compareRenewal } from '../../../utils/broker/brokerFormat'
import type { BrokerCompanyMetric, WcPortfolioRow } from '../../../types/broker'

const PANEL = 'rounded-2xl border border-white/[0.06] bg-zinc-950 p-5'

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

type SortKey = 'account' | 'renewal'
type SortDir = 'asc' | 'desc'

interface ClientTableProps {
  companies: BrokerCompanyMetric[]
  /** Per-company WC metrics (TRIR / DART / premium), keyed by company_id.
   *  Companies absent from the map render "—" for safety columns. */
  wcByCompany?: Map<string, WcPortfolioRow>
  /** Opens the consultative outreach drawer for a client. */
  onOutreach?: (companyId: string, companyName: string) => void
  /** Persist a broker-set renewal date. null clears it back to the derived fallback. */
  onSetRenewal?: (companyId: string, date: string | null) => void
}

export function ClientTable({ companies, wcByCompany, onOutreach, onSetRenewal }: ClientTableProps) {
  const navigate = useNavigate()
  const [sortKey, setSortKey] = useState<SortKey>('account')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [editingRenewal, setEditingRenewal] = useState<string | null>(null)

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  const SortIcon = ({ col }: { col: SortKey }) => {
    if (sortKey !== col) return <ChevronUp size={10} className="text-zinc-700" />
    return sortDir === 'asc' ? <ChevronUp size={10} /> : <ChevronDown size={10} />
  }

  if (companies.length === 0) {
    return (
      <div className={PANEL}>
        <h3 className={`${LABEL} mb-4 flex items-center gap-1.5 normal-case`}>Accounts <HelpHint text="Every client with their key risk signals. Click a client to open their full WC + EPL detail, or start an AI-grounded outreach to them." /></h3>
        <p className="text-sm text-zinc-500">No linked clients yet.</p>
      </div>
    )
  }

  const rows = [...companies].sort((a, b) => {
    if (sortKey === 'renewal') return compareRenewal(a.renewal_date, b.renewal_date, sortDir)
    const cmp = a.company_name.localeCompare(b.company_name)
    return sortDir === 'desc' ? -cmp : cmp
  })

  return (
    <div className={PANEL}>
      <h3 className={`${LABEL} mb-4`}>Accounts</h3>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-white/[0.06]">
              <th className={`pb-2 pr-4 ${LABEL}`}>
                <button type="button" onClick={() => toggleSort('account')} className="inline-flex items-center gap-1 hover:text-zinc-300">
                  Account <SortIcon col="account" />
                </button>
              </th>
              <th className={`pb-2 pr-4 ${LABEL}`}>Status</th>
              <th className={`pb-2 pr-4 ${LABEL}`}>
                <button type="button" onClick={() => toggleSort('renewal')} className="inline-flex items-center gap-1 hover:text-zinc-300">
                  Renewal <SortIcon col="renewal" />
                </button>
              </th>
              <th className={`pb-2 pr-4 text-right ${LABEL}`}>FTE</th>
              <th className={`pb-2 pr-4 text-right ${LABEL}`}>TRIR / DART</th>
              <th className={`pb-2 text-right ${LABEL}`}>Premium Δ</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => {
              const wc = wcByCompany?.get(c.company_id)
              const trirRatio = wc?.benchmark && wc?.trir ? `${(wc.trir / wc.benchmark.trir).toFixed(1)}×` : null
              const isEditingRenewal = editingRenewal === c.company_id
              return (
                <tr
                  key={c.company_id}
                  className="border-b border-white/[0.04] last:border-0 cursor-pointer hover:bg-white/[0.03] transition-colors"
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
                  {/* Renewal: countdown badge + date, click-to-edit */}
                  <td className="py-2.5 pr-4" onClick={(e) => e.stopPropagation()}>
                    {isEditingRenewal ? (
                      <input
                        type="date"
                        autoFocus
                        // Blank, not the derived coverage-line date — prefilling it would
                        // let an open/close-with-no-edit silently write it as a broker
                        // override and stop it tracking the coverage line.
                        defaultValue={c.renewal_date_source === 'broker' ? c.renewal_date ?? '' : ''}
                        onBlur={(e) => {
                          setEditingRenewal(null)
                          const original = c.renewal_date_source === 'broker' ? c.renewal_date ?? '' : ''
                          if (e.target.value === original) return   // no-op: don't write on a plain open/close
                          onSetRenewal?.(c.company_id, e.target.value || null)
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') e.currentTarget.blur()
                          if (e.key === 'Escape') setEditingRenewal(null)
                        }}
                        className="bg-zinc-900 border border-white/10 rounded px-1.5 py-0.5 text-[11px] text-zinc-200"
                      />
                    ) : (
                      <button
                        type="button"
                        onClick={() => onSetRenewal && setEditingRenewal(c.company_id)}
                        className="text-left"
                      >
                        <RenewalPill
                          days={daysUntilDate(c.renewal_date)}
                          derived={c.renewal_date_source === 'coverage'}
                        />
                        {c.renewal_date && (
                          <div className="text-[9px] text-zinc-600 font-mono">{fmtDate(c.renewal_date)}</div>
                        )}
                      </button>
                    )}
                  </td>
                  <td className="py-2.5 pr-4 text-right text-zinc-300 tabular-nums">
                    {wc?.headcount ?? c.active_employee_count}
                  </td>
                  {/* TRIR / DART: value + ×bench + delta */}
                  <td className="py-2.5 pr-4 text-right">
                    {wc?.trir != null ? (
                      <>
                        <div className="font-mono text-[13px] text-zinc-100 tabular-nums">
                          {wc.trir.toFixed(2)} / {wc.dart_rate != null ? wc.dart_rate.toFixed(2) : '—'}
                        </div>
                        {trirRatio && <div className="text-[9px] text-zinc-600 font-mono">{trirRatio} bench</div>}
                        <DeltaPill pct={wc.trir_delta_pct} />
                      </>
                    ) : (
                      <span className="text-zinc-700">—</span>
                    )}
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
    </div>
  )
}
