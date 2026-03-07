import { useState, useEffect } from 'react';
import { irIncidents } from '../../api/client';
import type { IRConsistencyGuidance } from '../../types';
import { useIsLightMode } from '../../hooks/useIsLightMode';

const LT = {
  card: 'bg-stone-100 rounded-2xl',
  label: 'text-[10px] text-stone-500 uppercase tracking-widest font-bold',
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  textSecondary: 'text-zinc-700',
  barFill: 'bg-stone-500',
  barTrack: 'bg-stone-200',
} as const;

const DK = {
  card: 'bg-zinc-900/50 border border-white/10 rounded-2xl',
  label: 'text-[10px] text-zinc-500 uppercase tracking-widest font-bold',
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  textSecondary: 'text-zinc-300',
  barFill: 'bg-zinc-700',
  barTrack: 'bg-zinc-800/20',
} as const;

function formatCategory(raw: string): string {
  return raw
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

interface ConsistencyGuidancePanelProps {
  incidentId: string;
  incidentStatus: string;
  similarAnalysisVersion?: number;
}

export function ConsistencyGuidancePanel({
  incidentId,
  incidentStatus,
  similarAnalysisVersion,
}: ConsistencyGuidancePanelProps) {
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;

  const [guidance, setGuidance] = useState<IRConsistencyGuidance | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (incidentStatus !== 'investigating' && incidentStatus !== 'action_required') return;

    let cancelled = false;
    setLoading(true);
    setFailed(false);

    irIncidents
      .getConsistencyGuidance(incidentId)
      .then((data) => {
        if (!cancelled) {
          setGuidance(data);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setFailed(true);
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [incidentId, incidentStatus, similarAnalysisVersion]);

  // Silent fail — don't render anything
  if (failed) return null;

  // Loading state
  if (loading) {
    return (
      <div className={`${t.card} p-6`}>
        <div className={`${t.label} mb-4`}>Precedent Guidance</div>
        <div className={`text-xs ${t.textFaint} animate-pulse`}>Analyzing precedents...</div>
      </div>
    );
  }

  if (!guidance) return null;

  // Unprecedented — no similar history at all
  if (guidance.unprecedented) {
    return (
      <div className={`${t.card} p-6`}>
        <div className={`${t.label} mb-4`}>Precedent Guidance</div>
        <div className={`text-xs ${t.textMuted}`}>No similar incidents in your company history.</div>
      </div>
    );
  }

  // Insufficient confidence
  if (guidance.confidence === 'insufficient') {
    return (
      <div className={`${t.card} p-6`}>
        <div className={`${t.label} mb-4`}>Precedent Guidance</div>
        <div className={`text-xs ${t.textMuted}`}>Too few similar incidents to establish a pattern.</div>
      </div>
    );
  }

  const confidenceLabel = guidance.confidence === 'strong' ? 'Strong precedent' : 'Limited precedent';

  return (
    <div className={`${t.card} p-6`}>
      <div className={`${t.label} mb-4`}>Precedent Guidance</div>

      {/* Action distribution bars */}
      {guidance.action_distribution && guidance.action_distribution.length > 0 && (
        <div className="space-y-3 mb-4">
          {guidance.action_distribution.map((action) => (
            <div key={action.category}>
              <div className="flex justify-between items-baseline mb-1">
                <span className={`text-xs ${t.textSecondary}`}>{formatCategory(action.category)}</span>
                <span className={`text-[10px] ${t.textMuted} tabular-nums`}>
                  {Math.round(action.probability * 100)}%
                </span>
              </div>
              <div className={`h-1.5 ${t.barTrack} rounded-full overflow-hidden`}>
                <div
                  className={`h-full ${t.barFill} rounded-full transition-all`}
                  style={{ width: `${Math.round(action.probability * 100)}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Stats */}
      <div className="space-y-1 mb-3">
        {guidance.weighted_avg_resolution_days != null && (
          <div className={`text-[10px] ${t.textMuted}`}>
            Avg resolution: {guidance.weighted_avg_resolution_days.toFixed(1)} days
          </div>
        )}
        {guidance.weighted_effectiveness_rate != null && (
          <div className={`text-[10px] ${t.textMuted}`}>
            Effectiveness: {Math.round(guidance.weighted_effectiveness_rate * 100)}%
          </div>
        )}
      </div>

      {/* AI insight */}
      {guidance.consistency_insight && (
        <div className={`text-[10px] ${t.textMuted} italic mb-3 leading-relaxed`}>
          "{guidance.consistency_insight}"
        </div>
      )}

      {/* Confidence footer */}
      <div className={`text-[9px] ${t.textFaint}`}>
        {confidenceLabel} &middot; {guidance.sample_size} case{guidance.sample_size !== 1 ? 's' : ''}
      </div>
    </div>
  );
}
