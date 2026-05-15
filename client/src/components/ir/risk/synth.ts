import type { IRRiskMatrix, IRRiskInsights, IRIncidentType } from '../../../types/ir'

export type IRDimension = {
  key: IRIncidentType
  label: string
  count: number
  severity_avg: number
  flagged_locations: number
  factors: string[]
}

export type IRSyntheticAssessment = {
  dimensions: Record<IRIncidentType, IRDimension>
  computed_at: string
  report?: string
  total_incidents: number
  flagged_count: number
  critical_themes: number
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
  safety: 'Safety incidents — injuries, hazards, OSHA-reportable events.',
  behavioral: 'Behavioral incidents — harassment, conflict, conduct violations.',
  property: 'Property incidents — damage, theft, equipment loss.',
  near_miss: 'Near-miss reports — events that almost caused harm. High counts indicate a strong reporting culture.',
  other: 'Incidents not fitting standard categories.',
}

export function synthesizeAssessment(
  matrix: IRRiskMatrix | null,
  insights: IRRiskInsights | null,
): IRSyntheticAssessment | null {
  if (!matrix) return null

  const totalsByType: Record<IRIncidentType, { count: number; severity_weighted_sum: number; flagged: number }> = {
    safety: { count: 0, severity_weighted_sum: 0, flagged: 0 },
    behavioral: { count: 0, severity_weighted_sum: 0, flagged: 0 },
    property: { count: 0, severity_weighted_sum: 0, flagged: 0 },
    near_miss: { count: 0, severity_weighted_sum: 0, flagged: 0 },
    other: { count: 0, severity_weighted_sum: 0, flagged: 0 },
  }
  const hotspotsByType: Record<IRIncidentType, Array<{ name: string; count: number; deviation: number; flagged: boolean }>> = {
    safety: [], behavioral: [], property: [], near_miss: [], other: [],
  }
  let flaggedCount = 0

  for (const row of matrix.rows) {
    for (const cell of row.cells) {
      if (cell.count === 0) continue
      const t = totalsByType[cell.incident_type]
      t.count += cell.count
      // cell.severity_score is already a per-cell average — weight by count for true overall avg.
      t.severity_weighted_sum += cell.severity_score * cell.count
      if (cell.flagged) {
        t.flagged += 1
        flaggedCount += 1
      }
      hotspotsByType[cell.incident_type].push({
        name: row.location_name,
        count: cell.count,
        deviation: cell.deviation_ratio,
        flagged: cell.flagged,
      })
    }
  }

  const dimensions = {} as Record<IRIncidentType, IRDimension>
  let totalIncidents = 0

  for (const key of IR_DIMENSION_ORDER) {
    const t = totalsByType[key]
    const sevAvg = t.count > 0 ? t.severity_weighted_sum / t.count : 0

    const factors: string[] = []
    if (t.count > 0) {
      factors.push(`${t.count} incident${t.count === 1 ? '' : 's'} · avg severity ${sevAvg.toFixed(1)}`)
      if (t.flagged > 0) {
        factors.push(`${t.flagged} location${t.flagged === 1 ? '' : 's'} flagged ≥2× baseline`)
      }
    } else {
      factors.push('No incidents reported in this window.')
    }
    const top = [...hotspotsByType[key]]
      .sort((a, b) => (Number(b.flagged) - Number(a.flagged)) || (b.count - a.count))
      .slice(0, 2)
    for (const h of top) {
      const devTxt = h.deviation >= 2 ? ` · ${h.deviation.toFixed(1)}× baseline` : ''
      factors.push(`${h.name} — ${h.count}${devTxt}`)
    }

    dimensions[key] = {
      key,
      label: IR_DIMENSION_LABELS[key],
      count: t.count,
      severity_avg: sevAvg,
      flagged_locations: t.flagged,
      factors,
    }

    totalIncidents += t.count
  }

  const criticalThemes = insights?.themes?.filter((t) => t.severity === 'critical').length ?? 0

  const report = insights?.themes && insights.themes.length > 0
    ? insights.themes[0].insight
    : undefined

  return {
    dimensions,
    computed_at: matrix.generated_at,
    report,
    total_incidents: totalIncidents,
    flagged_count: flaggedCount,
    critical_themes: criticalThemes,
  }
}
