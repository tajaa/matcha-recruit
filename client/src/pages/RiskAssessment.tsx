import { useState, useEffect, useCallback } from 'react';
import { RefreshCw } from 'lucide-react';
import type { RiskAssessmentResult, DimensionResult, RiskRecommendation } from '../types';
import { riskAssessment } from '../api/client';
import { useAuth } from '../context/AuthContext';

type Band = 'low' | 'moderate' | 'high' | 'critical';

const BAND_COLOR: Record<Band, { text: string; dot: string; badge: string; bar: string }> = {
  low:      { text: 'text-emerald-400', dot: 'bg-emerald-500',                          badge: 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20', bar: 'bg-emerald-500' },
  moderate: { text: 'text-amber-400',   dot: 'bg-amber-500',                            badge: 'bg-amber-500/10  text-amber-400  border border-amber-500/20',  bar: 'bg-amber-500'   },
  high:     { text: 'text-orange-400',  dot: 'bg-orange-500',                           badge: 'bg-orange-500/10 text-orange-400 border border-orange-500/20', bar: 'bg-orange-500'  },
  critical: { text: 'text-red-400',     dot: 'bg-red-500 animate-pulse',                badge: 'bg-red-500/10    text-red-400    border border-red-500/20',    bar: 'bg-red-500'     },
};

const BAND_LABEL: Record<Band, string> = {
  low: 'Low', moderate: 'Moderate', high: 'High', critical: 'Critical',
};

const DIMENSION_META: Record<string, { label: string; weight: string }> = {
  compliance:  { label: 'Compliance',  weight: '30%' },
  incidents:   { label: 'Incidents',   weight: '25%' },
  er_cases:    { label: 'ER Cases',    weight: '25%' },
  workforce:   { label: 'Workforce',   weight: '15%' },
  legislative: { label: 'Legislative', weight: '5%'  },
};

const DIMENSION_ORDER = ['compliance', 'incidents', 'er_cases', 'workforce', 'legislative'] as const;

const PRIORITY_COLOR: Record<string, { badge: string }> = {
  critical: { badge: 'bg-red-500/10 text-red-400 border border-red-500/20' },
  high:     { badge: 'bg-orange-500/10 text-orange-400 border border-orange-500/20' },
  medium:   { badge: 'bg-amber-500/10 text-amber-400 border border-amber-500/20' },
  low:      { badge: 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' },
};

function BandBadge({ band }: { band: Band }) {
  const c = BAND_COLOR[band];
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest ${c.badge}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
      {BAND_LABEL[band]}
    </span>
  );
}

function ScoreBar({ score, band }: { score: number; band: Band }) {
  return (
    <div className="h-px w-full bg-white/10 relative overflow-hidden">
      <div
        className={`absolute inset-y-0 left-0 ${BAND_COLOR[band].bar} transition-all duration-700`}
        style={{ width: `${Math.min(100, Math.max(0, score))}%` }}
      />
    </div>
  );
}

function DimensionCard({ dimensionKey, dim }: { dimensionKey: string; dim: DimensionResult }) {
  const meta = DIMENSION_META[dimensionKey] ?? { label: dimensionKey, weight: '' };
  const c = BAND_COLOR[dim.band];

  return (
    <div className="bg-zinc-900 border border-white/10 p-6 flex flex-col gap-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">{meta.label}</div>
          <div className="text-[9px] text-zinc-600 uppercase tracking-widest mt-0.5">{meta.weight} weight</div>
        </div>
        <BandBadge band={dim.band} />
      </div>

      {/* Score */}
      <div className="flex items-end gap-2">
        <span className={`text-4xl font-light font-mono ${c.text}`}>{dim.score}</span>
        <span className="text-sm text-zinc-600 mb-1 font-mono">/ 100</span>
      </div>

      <ScoreBar score={dim.score} band={dim.band} />

      {/* Factors */}
      <div className="flex flex-col gap-1.5">
        {dim.factors.map((factor, i) => (
          <div key={i} className="flex items-start gap-2 text-[11px] text-zinc-500">
            <span className="mt-1.5 w-1 h-1 rounded-full bg-zinc-700 shrink-0" />
            {factor}
          </div>
        ))}
      </div>
    </div>
  );
}

function isEmptyResult(data: RiskAssessmentResult): boolean {
  if (data.overall_score !== 0) return false;
  return DIMENSION_ORDER.every(k => data.dimensions[k].score === 0);
}

export default function RiskAssessment() {
  const { user } = useAuth();
  const [data, setData] = useState<RiskAssessmentResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      setData(await riskAssessment.get());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load risk assessment.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Computing risk assessment…</div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-12">

      {/* Header */}
      <div className="flex justify-between items-start border-b border-white/10 pb-8">
        <div>
          <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">Risk Assessment</h1>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">Live exposure analysis across all platform data</p>
        </div>
        <button
          onClick={() => fetchData(true)}
          disabled={refreshing}
          className="flex items-center gap-2 px-4 py-2 text-xs text-zinc-500 hover:text-white uppercase tracking-wider transition-colors border border-white/10 disabled:opacity-40"
        >
          <RefreshCw size={12} className={refreshing ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="border border-red-500/20 bg-red-500/5 px-4 py-3 text-xs text-red-400 uppercase tracking-wider">
          {error}
        </div>
      )}

      {!error && data && isEmptyResult(data) && (
        <div className="border border-white/10 p-12 text-center">
          <div className="text-xs text-zinc-500 uppercase tracking-wider">No risk data yet</div>
          <div className="text-[10px] text-zinc-600 mt-2 font-mono">Add locations, employees, or run a compliance check to see your risk profile.</div>
        </div>
      )}

      {!error && data && !isEmptyResult(data) && (
        <>
          {/* Overall score */}
          <div className="grid grid-cols-5 gap-px bg-white/10 border border-white/10">
            {/* Big number */}
            <div className="col-span-2 bg-zinc-950 p-8 flex flex-col justify-between">
              <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Overall Risk Score</div>
              <div className="flex items-end gap-4 mt-4">
                <span className={`text-8xl font-light font-mono ${BAND_COLOR[data.overall_band].text}`}>
                  {data.overall_score}
                </span>
                <div className="mb-2 flex flex-col gap-2">
                  <BandBadge band={data.overall_band} />
                  <span className="text-[9px] text-zinc-600 font-mono">/100</span>
                </div>
              </div>
              <div className="mt-6">
                <ScoreBar score={data.overall_score} band={data.overall_band} />
              </div>
            </div>

            {/* Dimension mini-stats */}
            {DIMENSION_ORDER.map(key => {
              const dim = data.dimensions[key];
              const meta = DIMENSION_META[key];
              const c = BAND_COLOR[dim.band];
              return (
                <div key={key} className="bg-zinc-950 p-6 flex flex-col justify-between">
                  <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">{meta.label}</div>
                  <div className={`text-3xl font-light font-mono mt-2 ${c.text}`}>{dim.score}</div>
                  <div className="mt-3 space-y-2">
                    <div className="text-[9px] text-zinc-600 uppercase tracking-widest">{meta.weight} weight</div>
                    <BandBadge band={dim.band} />
                  </div>
                </div>
              );
            })}
          </div>

          {/* Timestamp */}
          <div className="text-[10px] text-zinc-600 font-mono uppercase tracking-wider -mt-8">
            Computed {new Date(data.computed_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
          </div>

          {/* Dimension detail cards */}
          <div>
            <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-4">Dimension Breakdown</div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-px bg-white/10 border border-white/10">
              {DIMENSION_ORDER.map(key => (
                <DimensionCard key={key} dimensionKey={key} dim={data.dimensions[key]} />
              ))}
            </div>
          </div>

          {/* Admin recommendations */}
          {data.recommendations && data.recommendations.length > 0 && (
            <div>
              <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-4">Recommendations</div>
              <div className="border border-white/10 divide-y divide-white/10">
                {data.recommendations.map((rec, i) => (
                  <div key={i} className="bg-zinc-950 px-6 py-4 flex items-start gap-4">
                    <span className={`shrink-0 inline-flex items-center px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest ${PRIORITY_COLOR[rec.priority]?.badge ?? ''}`}>
                      {rec.priority}
                    </span>
                    <div className="flex flex-col gap-1 min-w-0">
                      <span className="text-[10px] text-zinc-600 uppercase tracking-widest font-bold">
                        {DIMENSION_META[rec.dimension]?.label ?? rec.dimension}
                      </span>
                      <span className="text-sm text-zinc-200 font-medium">{rec.title}</span>
                      <span className="text-xs text-zinc-400 mt-1">{rec.guidance}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Score bands legend */}
          <div className="border border-white/10 p-6">
            <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-4">Score Bands</div>
            <div className="grid grid-cols-4 gap-px bg-white/10">
              {(['low', 'moderate', 'high', 'critical'] as Band[]).map(band => (
                <div key={band} className="bg-zinc-950 px-4 py-3">
                  <div className={`text-[10px] font-bold uppercase tracking-widest ${BAND_COLOR[band].text}`}>{BAND_LABEL[band]}</div>
                  <div className="text-[9px] text-zinc-600 mt-1 font-mono">
                    {band === 'low' ? '0 – 25' : band === 'moderate' ? '26 – 50' : band === 'high' ? '51 – 75' : '76 – 100'}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
