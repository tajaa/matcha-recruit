import type { IRRiskMatrix, IRRiskInsights, IRIncidentType } from '../../../types/ir'
import { getBandForScore, type Band } from '../../../types/risk-assessment'

export type IRDimension = {
  key: IRIncidentType
  label: string
  score: number
  band: Band
  count: number
  severity_avg: number
  factors: string[]
}

export type IRSyntheticAssessment = {
  overall_score: number
  overall_band: Band
  dimensions: Record<IRIncidentType, IRDimension>
  computed_at: string
  report?: string
  total_incidents: number
}

export const IR_DIMENSION_ORDER: IRIncidentType[] = [
  'safety',
  'behavioral',
  'property',
  'near_miss',
  'other',
]

export const IR_DIMENSION_LABELS: Record<IRIncidentType, string> = {
  safety: 'Safety',
  behavioral: 'Behavioral',
  property: 'Property',
  near_miss: 'Near Miss',
  other: 'Other',
}

export const IR_DIMENSION_HELP: Record<IRIncidentType, string> = {
  safety: 'Safety incidents — injuries, hazards, OSHA-reportable events. Higher score = more incidents in window, weighted by severity.',
  behavioral: 'Behavioral incidents — harassment, conflict, conduct violations. Higher score = more incidents in window, weighted by severity.',
  property: 'Property incidents — damage, theft, equipment loss.',
  near_miss: 'Near-miss reports — events that almost caused harm. High counts indicate strong reporting culture but underlying risk.',
  other: 'Incidents not fitting standard categories.',
}

const SCALING = 5  // 10 incidents/period → ~50 score (before severity bump)

function scoreFromCount(count: number, severityAvg: number): number {
  if (count === 0) return 0
  const base = Math.min(100, count * SCALING)
  // Severity tilt: avg severity 1=low, 4=critical. Push up to +25 for critical-heavy.
  const severityBump = Math.max(0, (severityAvg - 1) / 3) * 25
  return Math.min(100, Math.round(base + severityBump))
}

export function synthesizeAssessment(
  matrix: IRRiskMatrix | null,
  insights: IRRiskInsights | null,
): IRSyntheticAssessment | null {
  if (!matrix) return null

  const totalsByType: Record<IRIncidentType, { count: number; severity_sum: number }> = {
    safety: { count: 0, severity_sum: 0 },
    behavioral: { count: 0, severity_sum: 0 },
    property: { count: 0, severity_sum: 0 },
    near_miss: { count: 0, severity_sum: 0 },
    other: { count: 0, severity_sum: 0 },
  }
  const hotspotsByType: Record<IRIncidentType, Array<{ name: string; count: number; deviation: number }>> = {
    safety: [], behavioral: [], property: [], near_miss: [], other: [],
  }

  for (const row of matrix.rows) {
    for (const cell of row.cells) {
      if (cell.count === 0) continue
      totalsByType[cell.incident_type].count += cell.count
      totalsByType[cell.incident_type].severity_sum += cell.severity_score * cell.count
      hotspotsByType[cell.incident_type].push({
        name: row.location_name,
        count: cell.count,
        deviation: cell.deviation_ratio,
      })
    }
  }

  const dimensions = {} as Record<IRIncidentType, IRDimension>
  let weightedSum = 0
  let weightTotal = 0
  let totalIncidents = 0

  for (const key of IR_DIMENSION_ORDER) {
    const t = totalsByType[key]
    const sevAvg = t.count > 0 ? t.severity_sum / t.count : 0
    const score = scoreFromCount(t.count, sevAvg)
    const band = getBandForScore(score)

    const factors: string[] = []
    if (t.count > 0) {
      factors.push(`${t.count} incident${t.count === 1 ? '' : 's'} this window · avg severity ${sevAvg.toFixed(1)}`)
    } else {
      factors.push('No incidents reported in this window.')
    }
    const top = [...hotspotsByType[key]]
      .sort((a, b) => b.count - a.count)
      .slice(0, 2)
    for (const h of top) {
      const devTxt = h.deviation >= 2 ? ` · ${h.deviation.toFixed(1)}× baseline` : ''
      factors.push(`${h.name} — ${h.count}${devTxt}`)
    }

    dimensions[key] = {
      key,
      label: IR_DIMENSION_LABELS[key],
      score,
      band,
      count: t.count,
      severity_avg: sevAvg,
      factors,
    }

    if (t.count > 0) {
      weightedSum += score * Math.max(1, t.count)
      weightTotal += Math.max(1, t.count)
    }
    totalIncidents += t.count
  }

  let overall = weightTotal > 0 ? Math.round(weightedSum / weightTotal) : 0
  // Critical-theme bump.
  if (insights?.themes?.some((t) => t.severity === 'critical')) {
    overall = Math.min(100, overall + 10)
  }

  const report = insights?.themes && insights.themes.length > 0
    ? insights.themes[0].insight
    : undefined

  return {
    overall_score: overall,
    overall_band: getBandForScore(overall),
    dimensions,
    computed_at: matrix.generated_at,
    report,
    total_incidents: totalIncidents,
  }
}
