import type { PropertyRollup, PropertyExposure, PropertyReadiness, PropertyPlan, PropertyRisk } from '../../../types/property'
import { COPE_TONE, READINESS_TONE, FIX_SEVERITY_TONE, RISK_LEVEL_TONE } from '../../../types/property'
import { Card } from '../../../components/ui'
import { fmtUsd } from './shared'

// Composite property risk score (underwriting headline)
export function RiskScoreCard({ risk }: { risk: PropertyRisk }) {
  return (
    <Card className="p-5">
      <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Property risk score</div>
      <div className="flex items-baseline gap-3 mt-1">
        <span className={`text-4xl font-light font-mono ${COPE_TONE[risk.grade ?? ''] ?? 'text-zinc-100'}`}>
          {risk.score}<span className="text-lg text-zinc-600">/100</span>
        </span>
        <span className={`text-sm font-semibold uppercase ${RISK_LEVEL_TONE[risk.risk_level ?? ''] ?? 'text-zinc-400'}`}>
          {risk.risk_level} risk · grade {risk.grade}
        </span>
      </div>
      <div className="text-[11px] text-zinc-600 mt-1">TIV-weighted COPE quality, adjusted for insurance-to-value + catastrophe exposure · {risk.rated} buildings scored.</div>
      {risk.top_risks.length > 0 && (
        <div className="mt-3 pt-3 border-t border-white/[0.06]">
          <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold mb-1.5">Top risk contributors</div>
          <ul className="space-y-1">
            {risk.top_risks.slice(0, 3).map((t) => (
              <li key={t.building_id} className="text-[12px] flex items-center gap-2">
                <span className={`font-mono font-semibold w-4 ${COPE_TONE[t.grade] ?? 'text-zinc-400'}`}>{t.grade}</span>
                <span className="text-zinc-300">{t.name || '(unnamed)'}</span>
                <span className="text-zinc-600">{t.drivers.map((d) => d.detail).join(' · ') || 'COPE-limited'}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  )
}

// Rollup metric cards
export function RollupCards({ rollup: r }: { rollup: PropertyRollup }) {
  const itvPct = r.itv.portfolio_ratio != null ? Math.round(r.itv.portfolio_ratio * 100) : null
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <Card className="p-4">
        <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Total insured value</div>
        <div className="text-3xl font-light font-mono mt-1 text-zinc-100">{fmtUsd(r.tiv)}</div>
        <div className="text-[10px] text-zinc-600">building + contents + BI</div>
      </Card>
      <Card className="p-4">
        <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Buildings</div>
        <div className="text-3xl font-light font-mono mt-1 text-zinc-200">{r.building_count}</div>
        <div className="text-[10px] text-zinc-600">on the SOV</div>
      </Card>
      <Card className="p-4">
        <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">COPE quality</div>
        <div className={`text-3xl font-light font-mono mt-1 ${r.worst_cope_grade ? COPE_TONE[r.worst_cope_grade] ?? 'text-zinc-200' : 'text-zinc-600'}`}>
          {r.avg_cope_score ?? '—'}
        </div>
        <div className="text-[10px] text-zinc-600">avg score · worst grade {r.worst_cope_grade ?? '—'}</div>
      </Card>
      <Card className="p-4">
        <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Insurance-to-value</div>
        <div className={`text-3xl font-light font-mono mt-1 ${itvPct == null ? 'text-zinc-600' : itvPct < 90 ? 'text-amber-400' : 'text-emerald-400'}`}>
          {itvPct != null ? `${itvPct}%` : '—'}
        </div>
        <div className="text-[10px] text-zinc-600">{r.itv.under_count} under-insured of {r.itv.rated_count}</div>
      </Card>
    </div>
  )
}

// Modeled $ exposure (directional)
export function ExposureCard({ exposure }: { exposure: PropertyExposure }) {
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Modeled exposure</span>
        <span className="text-[10px] text-zinc-600">directional estimate · not a cat model</span>
      </div>
      <div className="grid grid-cols-3 gap-4">
        <div>
          <div className="text-2xl font-light font-mono text-zinc-100">{fmtUsd(exposure.total_aal)}</div>
          <div className="text-[10px] text-zinc-600 uppercase tracking-wider mt-0.5">Avg annual loss</div>
        </div>
        <div>
          <div className="text-2xl font-light font-mono text-amber-400">{fmtUsd(exposure.worst_pml)}</div>
          <div className="text-[10px] text-zinc-600 uppercase tracking-wider mt-0.5">Worst PML{exposure.worst_pml_peril ? ` · ${exposure.worst_pml_peril}` : ''}</div>
        </div>
        <div>
          <div className={`text-2xl font-light font-mono ${exposure.coinsurance_shortfall > 0 ? 'text-amber-400' : 'text-emerald-400'}`}>{fmtUsd(exposure.coinsurance_shortfall)}</div>
          <div className="text-[10px] text-zinc-600 uppercase tracking-wider mt-0.5">Coinsurance shortfall</div>
        </div>
      </div>
      <p className="text-[10px] text-zinc-600 mt-3">AAL = expected loss per year · PML = worst single catastrophe event (peril accumulated across buildings) · shortfall = added insured value to meet a 90% coinsurance clause.</p>
    </Card>
  )
}

// Submission readiness
export function ReadinessCard({ readiness }: { readiness: PropertyReadiness }) {
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Property submission readiness</span>
        <span className={`text-sm font-semibold ${READINESS_TONE[readiness.band] ?? 'text-zinc-300'}`}>
          {readiness.score}/100 · {readiness.band}
        </span>
      </div>
      {readiness.top_fixes.length > 0 && (
        <ul className="space-y-0.5">
          {readiness.top_fixes.map((f) => (
            <li key={f} className="text-[12px] text-zinc-400 flex items-start gap-1.5"><span className="text-zinc-600 mt-px">•</span>{f}</li>
          ))}
        </ul>
      )}
    </Card>
  )
}

// Risk-improvement plan
export function PlanCard({ plan }: { plan: PropertyPlan }) {
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Risk-improvement plan</span>
        <span className="text-[10px] text-zinc-600">{plan.summary.total} item{plan.summary.total === 1 ? '' : 's'} · prioritized</span>
      </div>
      <ul className="space-y-2.5">
        {plan.fixes.map((f, i) => (
          <li key={f.key + i} className="flex items-start gap-2.5">
            <span className={`mt-0.5 shrink-0 text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded ${FIX_SEVERITY_TONE[f.severity] ?? 'bg-zinc-800 text-zinc-400'}`}>{f.severity}</span>
            <div className="min-w-0">
              <div className="text-[13px] text-zinc-200">
                {f.label}
                {f.impact && <span className="ml-2 text-[11px] font-mono text-emerald-400">{f.impact}</span>}
              </div>
              <div className="text-[11px] text-zinc-500">{f.detail}</div>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  )
}
