import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, ShieldAlert } from 'lucide-react';
import type { RiskAssessmentResult, DimensionResult } from '../types';
import { riskAssessment } from '../api/client';

type Band = 'low' | 'moderate' | 'high' | 'critical';

const BAND_COLORS: Record<Band, { text: string; bg: string; border: string; bar: string }> = {
  low: {
    text: 'text-green-400',
    bg: 'bg-green-500/10',
    border: 'border-green-500/30',
    bar: 'bg-green-500',
  },
  moderate: {
    text: 'text-yellow-400',
    bg: 'bg-yellow-500/10',
    border: 'border-yellow-500/30',
    bar: 'bg-yellow-500',
  },
  high: {
    text: 'text-orange-400',
    bg: 'bg-orange-500/10',
    border: 'border-orange-500/30',
    bar: 'bg-orange-500',
  },
  critical: {
    text: 'text-red-400',
    bg: 'bg-red-500/10',
    border: 'border-red-500/30',
    bar: 'bg-red-500',
  },
};

const BAND_LABELS: Record<Band, string> = {
  low: 'Low',
  moderate: 'Moderate',
  high: 'High',
  critical: 'Critical',
};

const DIMENSION_LABELS: Record<string, string> = {
  compliance: 'Compliance',
  incidents: 'Incidents',
  er_cases: 'ER Cases',
  workforce: 'Workforce',
  legislative: 'Legislative',
};

const DIMENSION_WEIGHTS: Record<string, string> = {
  compliance: '30% weight',
  incidents: '25% weight',
  er_cases: '25% weight',
  workforce: '15% weight',
  legislative: '5% weight',
};

const DIMENSION_ORDER: Array<keyof RiskAssessmentResult['dimensions']> = [
  'compliance',
  'incidents',
  'er_cases',
  'workforce',
  'legislative',
];

function BandBadge({ band }: { band: Band }) {
  const colors = BAND_COLORS[band];
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${colors.bg} ${colors.text} border ${colors.border}`}
    >
      {BAND_LABELS[band]}
    </span>
  );
}

function ScoreBar({ score, band }: { score: number; band: Band }) {
  const colors = BAND_COLORS[band];
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-700/50">
      <div
        className={`h-full rounded-full transition-all duration-500 ${colors.bar}`}
        style={{ width: `${Math.min(100, Math.max(0, score))}%` }}
      />
    </div>
  );
}

function DimensionCard({
  dimensionKey,
  dimension,
}: {
  dimensionKey: string;
  dimension: DimensionResult;
}) {
  const colors = BAND_COLORS[dimension.band];
  const label = DIMENSION_LABELS[dimensionKey] ?? dimensionKey;
  const weight = DIMENSION_WEIGHTS[dimensionKey];

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-zinc-800 bg-zinc-900 p-6">
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-col gap-1">
          <span className="text-sm font-medium text-zinc-300">{label}</span>
          {weight && (
            <span className="text-xs text-zinc-500">{weight}</span>
          )}
        </div>
        <BandBadge band={dimension.band} />
      </div>

      <div className="flex items-end gap-2">
        <span className={`text-4xl font-bold tabular-nums ${colors.text}`}>
          {dimension.score}
        </span>
        <span className="mb-1 text-sm text-zinc-500">/ 100</span>
      </div>

      <ScoreBar score={dimension.score} band={dimension.band} />

      {dimension.factors.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium uppercase tracking-wider text-zinc-500">
            Contributing Factors
          </span>
          <ul className="flex flex-col gap-1">
            {dimension.factors.map((factor, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-zinc-400">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-zinc-500" />
                {factor}
              </li>
            ))}
          </ul>
        </div>
      )}

      {dimension.factors.length === 0 && (
        <p className="text-xs text-zinc-600">No contributing factors identified.</p>
      )}
    </div>
  );
}

function isEmptyResult(data: RiskAssessmentResult): boolean {
  if (data.overall_score !== 0) return false;
  return DIMENSION_ORDER.every((key) => data.dimensions[key].score === 0);
}

export default function RiskAssessment() {
  const [data, setData] = useState<RiskAssessmentResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      const result = await riskAssessment.get();
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load risk assessment data.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const overallColors = data ? BAND_COLORS[data.overall_band] : null;
  const computedAt = data
    ? new Date(data.computed_at).toLocaleString(undefined, {
        dateStyle: 'medium',
        timeStyle: 'short',
      })
    : null;

  const empty = data ? isEmptyResult(data) : false;

  return (
    <div className="min-h-screen bg-zinc-950 text-white">
      <div className="mx-auto max-w-6xl px-6 py-10">

        {/* Page header */}
        <div className="mb-8 flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-zinc-800">
              <ShieldAlert className="h-4 w-4 text-zinc-400" />
            </div>
            <h1 className="text-2xl font-semibold text-white">Risk Assessment</h1>
          </div>

          <button
            onClick={() => fetchData(true)}
            disabled={loading || refreshing}
            className="flex items-center gap-2 rounded-lg border border-zinc-700/50 bg-zinc-800 px-3 py-2 text-sm font-medium text-zinc-300 transition-colors hover:bg-zinc-700 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>

        {/* Loading state */}
        {loading && (
          <div className="flex flex-col items-center justify-center py-32 gap-4">
            <RefreshCw className="h-6 w-6 animate-spin text-zinc-500" />
            <p className="text-sm text-zinc-500">Loading risk assessment…</p>
          </div>
        )}

        {/* Error state */}
        {!loading && error && (
          <div className="flex flex-col items-center justify-center py-32 gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-red-500/10">
              <ShieldAlert className="h-5 w-5 text-red-400" />
            </div>
            <div className="text-center">
              <p className="text-sm font-medium text-white">Failed to load risk data</p>
              <p className="mt-1 text-xs text-zinc-500">{error}</p>
            </div>
            <button
              onClick={() => fetchData()}
              className="rounded-lg border border-zinc-700/50 bg-zinc-800 px-4 py-2 text-sm font-medium text-zinc-300 transition-colors hover:bg-zinc-700 hover:text-white"
            >
              Try again
            </button>
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && data && empty && (
          <div className="flex flex-col items-center justify-center py-32 gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-zinc-800">
              <ShieldAlert className="h-5 w-5 text-zinc-500" />
            </div>
            <div className="text-center">
              <p className="text-sm font-medium text-white">No risk data yet</p>
              <p className="mt-1 max-w-sm text-xs text-zinc-500">
                Add locations, employees, or run a compliance check to see your risk profile.
              </p>
            </div>
          </div>
        )}

        {/* Data */}
        {!loading && !error && data && !empty && (
          <div className="flex flex-col gap-8">

            {/* Overall score card */}
            <div className="flex flex-col gap-6 rounded-xl border border-zinc-800 bg-zinc-900 p-8">
              <div className="flex flex-col gap-1">
                <span className="text-xs font-medium uppercase tracking-wider text-zinc-500">
                  Overall Risk Score
                </span>
              </div>

              <div className="flex flex-wrap items-end gap-4">
                <span
                  className={`text-7xl font-bold tabular-nums leading-none ${overallColors?.text}`}
                >
                  {data.overall_score}
                </span>

                <div className="mb-2 flex flex-col gap-2">
                  <BandBadge band={data.overall_band} />
                  {computedAt && (
                    <span className="text-xs text-zinc-500">as of {computedAt}</span>
                  )}
                </div>
              </div>

              <ScoreBar score={data.overall_score} band={data.overall_band} />
            </div>

            {/* Dimension cards grid */}
            <div>
              <h2 className="mb-4 text-sm font-medium uppercase tracking-wider text-zinc-500">
                Dimensions
              </h2>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {DIMENSION_ORDER.map((key) => (
                  <DimensionCard
                    key={key}
                    dimensionKey={key}
                    dimension={data.dimensions[key]}
                  />
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
