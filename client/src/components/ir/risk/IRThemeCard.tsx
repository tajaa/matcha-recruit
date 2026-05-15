import { Badge } from '../../ui'
import {
  SEVERITY_BADGE,
  severityLabel,
  type IRRiskTheme,
} from '../../../types/ir'

export function IRThemeCard({
  theme,
  onNavigateIncident,
}: {
  theme: IRRiskTheme
  onNavigateIncident?: (id: string) => void
}) {
  const variant = SEVERITY_BADGE[theme.severity] ?? 'neutral'
  return (
    <div className="bg-zinc-900 border border-white/10 rounded-2xl p-5 space-y-2.5">
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-sm font-medium text-zinc-100">{theme.label}</h3>
        <Badge variant={variant}>{severityLabel(theme.severity)}</Badge>
      </div>
      <p className="text-[11px] text-zinc-500 uppercase tracking-wider font-mono">
        {theme.incident_count} incident{theme.incident_count === 1 ? '' : 's'}
        {theme.location_name ? ` · ${theme.location_name}` : ' · multi-location'}
      </p>
      <p className="text-sm text-zinc-300 leading-relaxed">{theme.insight}</p>
      <div className="pt-2 border-t border-white/5">
        <p className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-1.5">Suggested</p>
        <p className="text-[12px] text-zinc-400 leading-relaxed">{theme.recommendation}</p>
      </div>
      {theme.evidence_incident_ids.length > 0 && (
        <div className="pt-2 border-t border-white/5 flex flex-wrap gap-1.5">
          {theme.evidence_incident_ids.map((id) => (
            <button
              key={id}
              onClick={() => onNavigateIncident?.(id)}
              className="text-[10px] font-mono text-emerald-400 hover:text-emerald-300 underline underline-offset-2"
            >
              {id.slice(0, 8)}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
