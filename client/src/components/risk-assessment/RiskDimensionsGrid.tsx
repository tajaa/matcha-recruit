import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import {
  BAND_COLOR, BAND_LABEL, DIMENSION_LABELS, DIMENSION_HELP,
  formatCurrency,
  type Band, type DimensionResult, type CostOfRisk, type CostLineItem,
} from '../../types/risk-assessment'

// ─── Helpers ─────────────────────────────────────────────────────────────────

type ComplianceAlertLocation = {
  location_id: string
  location_name: string | null
  city: string | null
  state: string | null
  violation_count: number
}

type ComplianceAlertMetrics = {
  total: number
  hourly: number
  salary: number
  locations: number
  topLocations: ComplianceAlertLocation[]
}

function getComplianceAlertMetrics(dim: DimensionResult): ComplianceAlertMetrics {
  const raw = dim.raw_data
  const toNumber = (key: string) => {
    const v = raw[key]
    return typeof v === 'number' ? v : 0
  }
  const topRaw = raw.top_minimum_wage_violation_locations
  const topLocations = Array.isArray(topRaw)
    ? topRaw.flatMap((item) => {
        if (!item || typeof item !== 'object') return []
        const c = item as Record<string, unknown>
        const locationId = typeof c.location_id === 'string' ? c.location_id : null
        const violationCount = typeof c.violation_count === 'number' ? c.violation_count : null
        if (!locationId || violationCount === null) return []
        return [{
          location_id: locationId,
          location_name: typeof c.location_name === 'string' ? c.location_name : null,
          city: typeof c.city === 'string' ? c.city : null,
          state: typeof c.state === 'string' ? c.state : null,
          violation_count: violationCount,
        }]
      })
    : []
  return {
    total: toNumber('minimum_wage_violation_employee_count'),
    hourly: toNumber('hourly_minimum_wage_violation_count'),
    salary: toNumber('salary_minimum_wage_violation_count'),
    locations: toNumber('locations_with_minimum_wage_violations'),
    topLocations,
  }
}

function formatLocation(loc: ComplianceAlertLocation): string {
  if (loc.location_name?.trim()) return loc.location_name
  if (loc.city && loc.state) return `${loc.city}, ${loc.state}`
  if (loc.state) return loc.state
  return 'Unlabeled location'
}

function hasComplianceAlerts(dim: DimensionResult): boolean {
  return typeof dim.raw_data.minimum_wage_violation_employee_count === 'number'
    && dim.raw_data.minimum_wage_violation_employee_count > 0
}

function getCostOfRisk(dim: DimensionResult): CostOfRisk | null {
  const cost = dim.raw_data?.cost_of_risk as CostOfRisk | undefined
  if (!cost?.line_items?.length) return null
  return cost
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function HelpTooltip({ text }: { text: string }) {
  return (
    <span className="relative group/help inline-flex">
      <span className="text-[8px] text-zinc-600 opacity-0 group-hover:opacity-100 transition-opacity cursor-help">?</span>
      <span className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-56 px-3 py-2 text-[10px] leading-relaxed text-zinc-300 bg-zinc-900 border border-white/10 shadow-xl opacity-0 group-hover/help:opacity-100 transition-opacity z-50">
        {text}
      </span>
    </span>
  )
}

function ScoreBar({ score, band }: { score: number; band: Band }) {
  return (
    <div className="h-px w-full bg-white/10 relative overflow-hidden">
      <div
        className={`absolute inset-y-0 left-0 ${BAND_COLOR[band].bar} transition-all duration-700`}
        style={{ width: `${Math.min(100, Math.max(0, score))}%` }}
      />
    </div>
  )
}

function BandBadge({ band }: { band: Band }) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest ${BAND_COLOR[band].badge}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${BAND_COLOR[band].dot}`} />
      {BAND_LABEL[band]}
    </span>
  )
}

function CostLineItemDetail({ label, text }: { label: string; text: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="text-[8px] text-zinc-600 uppercase tracking-widest font-bold">{label}</div>
      <div className="text-[10px] text-zinc-500 leading-relaxed">{text}</div>
    </div>
  )
}

function CostLineItemRow({ item, barWidth = 0, lowPct = 0 }: { item: CostLineItem; barWidth?: number; lowPct?: number }) {
  const [expanded, setExpanded] = useState(false)
  const hasDetails = item.formula || item.statute || item.risk_context || item.benchmark

  return (
    <div className="flex flex-col">
      <button
        type="button"
        onClick={() => hasDetails && setExpanded(!expanded)}
        className={`flex flex-col gap-1.5 text-left ${hasDetails ? 'cursor-pointer hover:bg-white/[0.02] -mx-2 px-2 py-1 rounded-lg transition-colors' : 'cursor-default'}`}
      >
        <div className="flex items-center justify-between gap-3">
          <span className="text-[11px] text-zinc-300 flex items-center gap-1.5 font-medium">
            {hasDetails && (
              expanded
                ? <ChevronDown className="w-3 h-3 text-zinc-500" />
                : <ChevronRight className="w-3 h-3 text-zinc-500" />
            )}
            {item.label}
          </span>
          <span className="text-[11px] font-mono text-red-400/90 shrink-0 tabular-nums">
            {formatCurrency(item.low)} – {formatCurrency(item.high)}
          </span>
        </div>
        {barWidth > 0 && (
          <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
            <div className="h-full rounded-full relative" style={{ width: `${barWidth}%` }}>
              <div className="absolute inset-0 bg-red-500/20 rounded-full" />
              <div className="absolute inset-y-0 left-0 bg-red-500/50 rounded-full" style={{ width: `${barWidth > 0 ? (lowPct / barWidth) * 100 : 0}%` }} />
            </div>
          </div>
        )}
        <div className="flex items-center gap-3 text-[9px] text-zinc-600">
          <span className="truncate">{item.basis}</span>
          <span className="font-mono shrink-0 text-zinc-500">{item.affected_count} affected</span>
        </div>
      </button>
      {expanded && (
        <div className="mt-2 ml-4 pl-3 border-l border-white/5 flex flex-col gap-2.5 pb-1">
          {item.formula && <CostLineItemDetail label="Calculation" text={item.formula} />}
          {item.statute && <CostLineItemDetail label="Legal basis" text={item.statute} />}
          {item.risk_context && <CostLineItemDetail label="Risk context" text={item.risk_context} />}
          {item.benchmark && <CostLineItemDetail label="Benchmarks" text={item.benchmark} />}
        </div>
      )}
    </div>
  )
}

function CostOfRiskCard({ cost }: { cost: CostOfRisk }) {
  const maxHigh = Math.max(...cost.line_items.map(i => i.high), 1)
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-baseline justify-between gap-4">
        <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Estimated Exposure</div>
        <div className="flex items-baseline gap-1.5">
          <span className="text-lg font-mono font-light text-red-400">{formatCurrency(cost.total_low)}</span>
          <span className="text-[10px] text-zinc-600">to</span>
          <span className="text-lg font-mono font-light text-red-400">{formatCurrency(cost.total_high)}</span>
        </div>
      </div>
      <div className="flex flex-col gap-3">
        {cost.line_items.map((item) => {
          const bw = Math.min((item.high / maxHigh) * 100, 100)
          const lp = Math.min((item.low / maxHigh) * 100, 100)
          return <CostLineItemRow key={item.key} item={item} barWidth={bw} lowPct={lp} />
        })}
      </div>
    </div>
  )
}

// ─── Main Component ──────────────────────────────────────────────────────────

type Props = {
  dimensions: Record<string, DimensionResult>
  weights?: Record<string, number>
}

export function RiskDimensionsGrid({ dimensions, weights }: Props) {
  return (
    <div>
      <h2 className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-4">
        Dimension Breakdown
      </h2>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {Object.entries(dimensions).map(([key, dim]) => {
          const b = dim.band as Band
          const complianceMetrics = key === 'compliance' ? getComplianceAlertMetrics(dim) : null
          const costOfRisk = getCostOfRisk(dim)
          const weight = weights?.[key] != null ? `${Math.round(weights[key] * 100)}%` : undefined

          return (
            <div key={key} className="bg-zinc-900 border border-white/10 rounded-2xl overflow-hidden">
              {/* Top section: score + factors side by side */}
              <div className="flex">
                {/* Left: score block */}
                <div className="w-32 shrink-0 p-5 flex flex-col items-center justify-center border-r border-white/5">
                  <span className={`text-5xl font-light font-mono ${BAND_COLOR[b].text}`}>{dim.score}</span>
                  <div className="mt-2 w-full">
                    <ScoreBar score={dim.score} band={b} />
                  </div>
                  <BandBadge band={b} />
                  {weight && <div className="text-[9px] text-zinc-700 uppercase tracking-widest mt-1">{weight}</div>}
                </div>

                {/* Right: header + factors */}
                <div className="flex-1 p-5 min-w-0">
                  <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-3 flex items-center gap-1.5">
                    {DIMENSION_LABELS[key] ?? key}
                    {DIMENSION_HELP[key] && <HelpTooltip text={DIMENSION_HELP[key]} />}
                  </div>
                  <div className="flex flex-col gap-1.5">
                    {dim.factors.map((factor, i) => (
                      <div key={i} className="flex items-start gap-2 text-[11px] text-zinc-400 leading-snug">
                        <span className="mt-1.5 w-1 h-1 rounded-full bg-zinc-600 shrink-0" />
                        {factor}
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Compliance metrics */}
              {complianceMetrics && hasComplianceAlerts(dim) && (
                <div className="border-t border-white/5 px-5 py-4">
                  <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold mb-3">Employee Compliance Alerts</div>
                  <div className="grid grid-cols-4 gap-px bg-white/10 rounded-lg overflow-hidden">
                    {[
                      { label: 'Below Min Wage', value: complianceMetrics.total, tone: complianceMetrics.total > 0 ? 'text-red-400' : 'text-zinc-300' },
                      { label: 'Hourly', value: complianceMetrics.hourly, tone: complianceMetrics.hourly > 0 ? 'text-red-400' : 'text-zinc-300' },
                      { label: 'Salary', value: complianceMetrics.salary, tone: complianceMetrics.salary > 0 ? 'text-red-400' : 'text-zinc-300' },
                      { label: 'Locations', value: complianceMetrics.locations, tone: complianceMetrics.locations > 0 ? 'text-amber-400' : 'text-zinc-300' },
                    ].map((m) => (
                      <div key={m.label} className="bg-zinc-950 px-3 py-2">
                        <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">{m.label}</div>
                        <div className={`mt-1 text-xl font-light font-mono ${m.tone}`}>{m.value}</div>
                      </div>
                    ))}
                  </div>
                  {complianceMetrics.topLocations.length > 0 && (
                    <div className="flex flex-col gap-1 mt-3">
                      {complianceMetrics.topLocations.map((loc) => (
                        <div key={loc.location_id} className="flex items-center justify-between gap-3 text-[10px] text-zinc-400">
                          <span className="truncate">{formatLocation(loc)}</span>
                          <span className="font-mono text-red-400">{loc.violation_count}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Cost of risk */}
              {costOfRisk && (
                <div className="border-t border-white/5 px-5 py-4">
                  <CostOfRiskCard cost={costOfRisk} />
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
