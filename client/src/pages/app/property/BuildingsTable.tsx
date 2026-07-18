import { Fragment } from 'react'
import { Pencil, Trash2, ChevronDown, ChevronRight } from 'lucide-react'
import { Card } from '../../../components/ui'
import type { PropertyBuilding, PropertyExposure, PropertyRisk } from '../../../types/property'
import { CONSTRUCTION_LABEL, COPE_TONE, PERIL_TONE, RISK_LEVEL_TONE } from '../../../types/property'
import { fmtUsd, WORST_PERIL } from './shared'
import { PerilDetail } from './PerilDetail'

interface BuildingsTableProps {
  buildings: PropertyBuilding[]
  risk?: PropertyRisk
  exposure?: PropertyExposure
  expanded: Set<string>
  onToggle: (id: string) => void
  onEdit: (b: PropertyBuilding) => void
  onDelete: (b: PropertyBuilding) => void
}

export function BuildingsTable({ buildings, risk, exposure, expanded, onToggle, onEdit, onDelete }: BuildingsTableProps) {
  if (buildings.length === 0) {
    return (
      <Card className="p-8 text-center">
        <p className="text-sm text-zinc-400">No buildings yet.</p>
        <p className="text-xs text-zinc-600 mt-1">Add your locations' buildings to build the Statement of Values.</p>
      </Card>
    )
  }
  return (
    <Card className="p-0 overflow-hidden">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-zinc-800/60 bg-zinc-900/40 text-[11px] text-zinc-500 uppercase tracking-wider">
            <th className="px-4 py-2.5 w-6"></th>
            <th className="px-4 py-2.5">Building</th>
            <th className="px-4 py-2.5">Construction</th>
            <th className="px-4 py-2.5 text-right">TIV</th>
            <th className="px-4 py-2.5 text-center">COPE</th>
            <th className="px-4 py-2.5 text-right">ITV</th>
            <th className="px-4 py-2.5 text-center">Cat</th>
            <th className="px-4 py-2.5 text-center">Risk</th>
            <th className="px-4 py-2.5"></th>
          </tr>
        </thead>
        <tbody>
          {buildings.map((b) => {
            const worst = WORST_PERIL(b)
            const itv = b.itv_ratio != null ? Math.round(b.itv_ratio * 100) : null
            const br = risk?.by_building[b.id]
            const isOpen = expanded.has(b.id)
            return (
              <Fragment key={b.id}>
                <tr className="border-b border-zinc-800/30 last:border-0 hover:bg-zinc-900/30">
                  <td className="px-4 py-3">
                    <button onClick={() => onToggle(b.id)} className="text-zinc-600 hover:text-zinc-300" aria-label="Toggle catastrophe detail">
                      {isOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <div className="text-zinc-100">{b.name || '(unnamed)'}</div>
                    <div className="text-[11px] text-zinc-600">{[b.city, b.state].filter(Boolean).join(', ') || '—'}</div>
                  </td>
                  <td className="px-4 py-3 text-zinc-400 text-xs">{b.construction_type ? CONSTRUCTION_LABEL[b.construction_type] : '—'}{b.sprinklered && <span className="ml-1 text-emerald-500">·spr</span>}</td>
                  <td className="px-4 py-3 text-right font-mono text-zinc-300">{fmtUsd(b.tiv)}</td>
                  <td className="px-4 py-3 text-center"><span className={`font-mono font-semibold ${COPE_TONE[b.cope_grade] ?? 'text-zinc-400'}`}>{b.cope_grade}</span></td>
                  <td className={`px-4 py-3 text-right font-mono ${itv == null ? 'text-zinc-600' : itv < 90 ? 'text-amber-400' : 'text-emerald-400'}`}>{itv != null ? `${itv}%` : '—'}</td>
                  <td className="px-4 py-3 text-center text-xs">
                    {worst ? <span className={`uppercase font-semibold ${PERIL_TONE[worst] ?? 'text-zinc-400'}`}>{worst}</span>
                      : <span className="text-zinc-600">{b.geocoded_at ? '—' : 'pending'}</span>}
                  </td>
                  <td className="px-4 py-3 text-center">
                    {br?.grade
                      ? <span className={`font-mono font-semibold ${COPE_TONE[br.grade] ?? 'text-zinc-400'}`} title={`${br.score}/100 · ${br.risk_level} risk`}>{br.grade}</span>
                      : <span className="text-zinc-600">—</span>}
                  </td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    <button onClick={() => onEdit(b)} className="text-zinc-500 hover:text-zinc-200 mr-2"><Pencil className="h-3.5 w-3.5 inline" /></button>
                    <button onClick={() => onDelete(b)} className="text-zinc-600 hover:text-red-400"><Trash2 className="h-3.5 w-3.5 inline" /></button>
                  </td>
                </tr>
                {isOpen && (
                  <tr className="bg-zinc-900/40 border-b border-zinc-800/30">
                    <td></td>
                    <td colSpan={8} className="px-4 py-3">
                      {br && br.score != null && (
                        <div className="mb-2.5 text-[11px]">
                          <span className="text-zinc-500">Risk score </span>
                          <span className={`font-mono font-semibold ${COPE_TONE[br.grade ?? ''] ?? 'text-zinc-300'}`}>{br.score}/100</span>
                          <span className={`ml-1.5 uppercase ${RISK_LEVEL_TONE[br.risk_level ?? ''] ?? 'text-zinc-500'}`}>{br.risk_level} risk</span>
                          {br.drivers.filter((d) => d.delta < 0).length > 0 && (
                            <span className="text-zinc-600"> — {br.drivers.filter((d) => d.delta < 0).map((d) => `${d.detail} (${d.delta})`).join(', ')}</span>
                          )}
                        </div>
                      )}
                      {exposure?.buildings[b.id] && (
                        <div className="mb-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-zinc-500">
                          <span>AAL <span className="font-mono text-zinc-300">{fmtUsd(exposure.buildings[b.id].aal)}</span></span>
                          <span>worst PML <span className="font-mono text-amber-400">{fmtUsd(exposure.buildings[b.id].worst_pml)}</span></span>
                          {exposure.buildings[b.id].coinsurance_shortfall > 0 && (
                            <span>coinsurance shortfall <span className="font-mono text-amber-400">{fmtUsd(exposure.buildings[b.id].coinsurance_shortfall)}</span></span>
                          )}
                          <span className="text-zinc-700">directional</span>
                        </div>
                      )}
                      <PerilDetail b={b} />
                    </td>
                  </tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </Card>
  )
}
