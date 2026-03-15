import { useState, useEffect } from 'react';
import { irIncidents } from '../../api/client';
import type { IRPolicyMappingAnalysis } from '../../types';
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
  btnGhost: 'text-stone-500 hover:text-stone-700',
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
  btnGhost: 'text-zinc-500 hover:text-zinc-300',
} as const;

const relevanceLabels: Record<string, string> = {
  violated: 'Violated',
  bent: 'Bent',
  related: 'Related',
};

interface PolicyMappingPanelProps {
  incidentId: string;
}

export function PolicyMappingPanel({ incidentId }: PolicyMappingPanelProps) {
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;

  const [data, setData] = useState<IRPolicyMappingAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setFailed(false);

    irIncidents
      .getPolicyMapping(incidentId)
      .then((res) => {
        if (!cancelled) {
          setData(res);
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
  }, [incidentId]);

  const handleRefresh = () => {
    setRefreshing(true);
    irIncidents
      .refreshPolicyMapping(incidentId)
      .then((res) => {
        setData(res);
        setRefreshing(false);
      })
      .catch(() => {
        setRefreshing(false);
      });
  };

  if (failed) return null;

  if (loading) {
    return (
      <div className={`${t.card} p-6`}>
        <div className={`${t.label} mb-4`}>Policy Mapping</div>
        <div className={`text-xs ${t.textFaint} animate-pulse`}>Mapping policies...</div>
      </div>
    );
  }

  if (!data) return null;

  if (data.no_matching_policies) {
    return (
      <div className={`${t.card} p-6`}>
        <div className={`${t.label} mb-4`}>Policy Mapping</div>
        <div className={`text-xs ${t.textMuted}`}>No active policies for this company.</div>
      </div>
    );
  }

  if (data.matches.length === 0) {
    return (
      <div className={`${t.card} p-6`}>
        <div className="flex justify-between items-center mb-4">
          <div className={t.label}>Policy Mapping</div>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className={`text-[9px] ${t.btnGhost} uppercase tracking-wider font-bold disabled:opacity-50`}
          >
            {refreshing ? '...' : 'Refresh'}
          </button>
        </div>
        <div className={`text-xs ${t.textMuted}`}>No matching policies found.</div>
      </div>
    );
  }

  return (
    <div className={`${t.card} p-6`}>
      <div className="flex justify-between items-center mb-4">
        <div className={t.label}>
          Policy Mapping
          {data.from_cache && <span className={`ml-2 ${t.textFaint}`}>Cached</span>}
        </div>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className={`text-[9px] ${t.btnGhost} uppercase tracking-wider font-bold disabled:opacity-50`}
        >
          {refreshing ? '...' : 'Refresh'}
        </button>
      </div>

      <div className="space-y-4 mb-4">
        {data.matches.map((match) => (
          <div key={match.policy_id}>
            <div className="flex justify-between items-baseline mb-1">
              <span className={`text-xs ${t.textSecondary} font-medium`}>{match.policy_title}</span>
              <span className={`text-[9px] ${t.textMuted} uppercase tracking-wider`}>
                {relevanceLabels[match.relevance] || match.relevance}
              </span>
            </div>
            <div className={`h-1 ${t.barTrack} rounded-full overflow-hidden mb-1.5`}>
              <div
                className={`h-full ${t.barFill} rounded-full transition-all`}
                style={{ width: `${Math.round(match.confidence * 100)}%` }}
              />
            </div>
            <div className={`text-[10px] ${t.textMuted} italic leading-relaxed`}>
              {match.reasoning}
            </div>
          </div>
        ))}
      </div>

      {data.summary && (
        <div className={`text-[10px] ${t.textMuted} leading-relaxed mb-2`}>
          {data.summary}
        </div>
      )}
    </div>
  );
}
