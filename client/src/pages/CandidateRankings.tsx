import { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';
import type { RankedCandidate, SignalDetail, CultureFitBreakdown } from '../types';
import { Card } from '../components/Card';
import {
  BarChart2,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  ShieldCheck,
  Loader2,
  Award,
} from 'lucide-react';

// ─── Helpers ─────────────────────────────────────────────────────────────────

function scoreColor(score: number | null) {
  if (score === null) return 'text-zinc-500';
  if (score >= 80) return 'text-emerald-400';
  if (score >= 60) return 'text-amber-400';
  return 'text-red-400';
}

function scoreBg(score: number | null) {
  if (score === null) return 'bg-zinc-800/60 border-zinc-700/50';
  if (score >= 80) return 'bg-emerald-500/10 border-emerald-500/30';
  if (score >= 60) return 'bg-amber-500/10 border-amber-500/30';
  return 'bg-red-500/10 border-red-500/30';
}

function rankBadge(rank: number) {
  if (rank === 1) return { bg: 'bg-amber-500/20 border-amber-400/40', text: 'text-amber-300', label: '#1' };
  if (rank === 2) return { bg: 'bg-zinc-400/10 border-zinc-400/30', text: 'text-zinc-300', label: '#2' };
  if (rank === 3) return { bg: 'bg-orange-700/20 border-orange-600/30', text: 'text-orange-400', label: '#3' };
  return { bg: 'bg-zinc-800/60 border-zinc-700/50', text: 'text-zinc-400', label: `#${rank}` };
}

function modeLabel(mode: string | undefined) {
  if (mode === 'full_signal') return { label: 'Full Signal', cls: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' };
  if (mode === 'partial_signal') return { label: 'Partial Signal', cls: 'bg-amber-500/15 text-amber-400 border-amber-500/30' };
  return { label: 'Resume Only', cls: 'bg-zinc-700/40 text-zinc-400 border-zinc-600/40' };
}

// ─── Sub-components ───────────────────────────────────────────────────────────

interface SignalBarProps {
  label: string;
  score: number | null;
  color: string;
  trackColor: string;
}

function SignalBar({ label, score, color, trackColor }: SignalBarProps) {
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between items-center">
        <span className="text-xs text-zinc-500 font-medium">{label}</span>
        {score !== null ? (
          <span className={`text-xs font-mono font-semibold ${scoreColor(score)}`}>
            {Math.round(score)}
          </span>
        ) : (
          <span className="text-xs text-zinc-600 italic">No data</span>
        )}
      </div>
      <div className={`h-1 ${trackColor} rounded-full overflow-hidden`}>
        {score !== null && (
          <div
            className={`h-full rounded-full ${color} transition-all duration-700`}
            style={{ width: `${Math.min(score, 100)}%` }}
          />
        )}
      </div>
    </div>
  );
}

interface RankCardProps {
  candidate: RankedCandidate;
  rank: number;
}

function RankCard({ candidate, rank }: RankCardProps) {
  const [expanded, setExpanded] = useState(false);
  const badge = rankBadge(rank);
  const mode = modeLabel(candidate.signal_breakdown?.mode);
  const sb = candidate.signal_breakdown;

  return (
    <Card>
      <div className="p-5">
        {/* Header row */}
        <div className="flex items-start gap-4">
          {/* Rank badge */}
          <div
            className={`flex-shrink-0 w-11 h-11 rounded-xl border flex items-center justify-center font-bold font-mono text-sm ${badge.bg} ${badge.text}`}
          >
            {badge.label}
          </div>

          {/* Name + badges */}
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-semibold text-zinc-100 text-base leading-tight">
                {candidate.candidate_name || 'Unknown Candidate'}
              </h3>
              {candidate.has_interview_data && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-teal-500/15 border border-teal-500/30 text-teal-400 text-xs font-medium">
                  <ShieldCheck size={11} />
                  Interview Verified
                </span>
              )}
              <span className={`inline-flex items-center px-2 py-0.5 rounded-full border text-xs font-medium ${mode.cls}`}>
                {mode.label}
              </span>
            </div>
            <p className="text-xs text-zinc-500 mt-0.5">
              Ranked {new Date(candidate.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
            </p>
          </div>

          {/* Overall score */}
          <div className={`flex-shrink-0 px-3 py-2 rounded-xl border text-right ${scoreBg(candidate.overall_rank_score)}`}>
            <div className={`text-2xl font-bold font-mono leading-none ${scoreColor(candidate.overall_rank_score)}`}>
              {Math.round(candidate.overall_rank_score)}
            </div>
            <div className="text-xs text-zinc-600 mt-0.5">/ 100</div>
          </div>
        </div>

        {/* Signal bars */}
        <div className="mt-5 grid grid-cols-1 sm:grid-cols-3 gap-3">
          <SignalBar
            label="Screening"
            score={candidate.screening_score}
            color="bg-emerald-500"
            trackColor="bg-emerald-500/15"
          />
          <SignalBar
            label="Culture Alignment"
            score={candidate.culture_alignment_score}
            color="bg-violet-500"
            trackColor="bg-violet-500/15"
          />
          <SignalBar
            label="Conversation Quality"
            score={candidate.conversation_score}
            color="bg-cyan-500"
            trackColor="bg-cyan-500/15"
          />
        </div>

        {/* Expand toggle */}
        {sb && (
          <button
            onClick={() => setExpanded((p) => !p)}
            className="mt-4 flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            {expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
            {expanded ? 'Hide breakdown' : 'Show breakdown'}
          </button>
        )}

        {/* Breakdown */}
        {expanded && sb && (
          <div className="mt-3 space-y-3 pt-3 border-t border-zinc-800">
            {sb.screening && (
              <SignalSection
                title="Screening"
                color="text-emerald-400"
                signal={sb.screening}
                subKeys={['communication_clarity', 'engagement_energy', 'critical_thinking', 'professionalism']}
                extraKey="recommendation"
              />
            )}
            {sb.culture_alignment && (
              <SignalSection
                title="Culture Alignment"
                color="text-violet-400"
                signal={sb.culture_alignment}
                subKeys={[]}
                cultureFit={sb.culture_alignment.culture_fit_breakdown}
              />
            )}
            {sb.conversation_quality && (
              <SignalSection
                title="Conversation Quality"
                color="text-cyan-400"
                signal={sb.conversation_quality}
                subKeys={['coverage_completeness', 'response_depth']}
              />
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

interface SignalSectionProps {
  title: string;
  color: string;
  signal: SignalDetail;
  subKeys: string[];
  extraKey?: string;
  cultureFit?: CultureFitBreakdown | null;
}

function SignalSection({ title, color, signal, subKeys, extraKey, cultureFit }: SignalSectionProps) {
  const formatKey = (k: string) =>
    k.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

  return (
    <div className="rounded-lg bg-zinc-900/60 border border-zinc-800/60 p-3">
      <div className="flex justify-between items-center mb-2">
        <span className={`text-xs font-semibold ${color}`}>{title}</span>
        <div className="flex items-center gap-2 text-xs text-zinc-500">
          <span>Weight {Math.round(signal.weight * 100)}%</span>
          <span>·</span>
          <span>Contributes {signal.weighted_contribution}</span>
        </div>
      </div>

      {/* Sub-scores from screening/conversation */}
      {signal.sub_scores && subKeys.length > 0 && (
        <div className="space-y-1.5">
          {subKeys.map((k) => {
            const val = signal.sub_scores![k];
            if (typeof val === 'number') {
              return (
                <div key={k} className="flex justify-between text-xs">
                  <span className="text-zinc-500">{formatKey(k)}</span>
                  <span className={scoreColor(val)}>{Math.round(val)}</span>
                </div>
              );
            }
            return null;
          })}
          {extraKey && signal.sub_scores[extraKey] && (
            <div className="flex justify-between text-xs">
              <span className="text-zinc-500">{formatKey(extraKey)}</span>
              <span className="text-zinc-300 capitalize">{String(signal.sub_scores[extraKey]).replace(/_/g, ' ')}</span>
            </div>
          )}
        </div>
      )}

      {/* Culture fit breakdown */}
      {cultureFit && (
        <div className="space-y-1.5">
          {(Object.entries(cultureFit) as [string, { score: number; reasoning?: string }][]).map(([k, v]) => (
            <div key={k} className="flex justify-between text-xs">
              <span className="text-zinc-500">{formatKey(k)}</span>
              <span className={scoreColor(v.score)}>{Math.round(v.score)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function CandidateRankings() {
  const { user, profile } = useAuth();
  const [rankings, setRankings] = useState<RankedCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const companyId: string | null =
    profile && typeof profile === 'object' && 'company_id' in profile && typeof profile.company_id === 'string'
      ? profile.company_id
      : user?.role === 'admin'
      ? null // admin needs a specific company; list will be empty until run
      : null;

  const loadRankings = useCallback(async (id: string) => {
    try {
      setError(null);
      const data = await api.rankings.list(id);
      setRankings(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load rankings');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (companyId) {
      loadRankings(companyId);
    } else {
      setLoading(false);
    }
  }, [companyId, loadRankings]);

  const handleRunRanking = async () => {
    if (!companyId) return;
    setRunning(true);
    setError(null);
    try {
      const result = await api.rankings.run(companyId);
      setRankings(result.rankings);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to run ranking');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Award size={20} className="text-matcha-500" />
            <h1 className="text-xl font-semibold text-zinc-100">Candidate Rankings</h1>
          </div>
          <p className="text-sm text-zinc-500">
            Multi-signal scoring combining interview performance and culture alignment
          </p>
        </div>
        <button
          onClick={handleRunRanking}
          disabled={running || !companyId}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-matcha-500 hover:bg-matcha-600 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors flex-shrink-0"
        >
          {running ? (
            <>
              <Loader2 size={14} className="animate-spin" />
              Running…
            </>
          ) : (
            <>
              <RefreshCw size={14} />
              Run Ranking
            </>
          )}
        </button>
      </div>

      {/* Signal legend */}
      <div className="flex flex-wrap gap-4 text-xs text-zinc-500">
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
          Screening (30%)
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-violet-500" />
          Culture Alignment (40%)
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-cyan-500" />
          Conversation Quality (30%)
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-4 flex items-start justify-between gap-3">
          <p className="text-sm text-red-400">{error}</p>
          {companyId && (
            <button
              onClick={() => loadRankings(companyId)}
              className="text-xs text-red-400 hover:text-red-300 underline flex-shrink-0"
            >
              Retry
            </button>
          )}
        </div>
      )}

      {/* No company context for admin */}
      {!companyId && user?.role === 'admin' && !loading && (
        <Card>
          <div className="p-8 text-center">
            <BarChart2 size={32} className="text-zinc-700 mx-auto mb-3" />
            <p className="text-sm text-zinc-400">
              Select a company to view rankings. Use the company detail page to run rankings per company.
            </p>
          </div>
        </Card>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-16">
          <Loader2 size={24} className="animate-spin text-zinc-600" />
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && companyId && rankings.length === 0 && (
        <Card>
          <div className="p-10 text-center space-y-3">
            <BarChart2 size={36} className="text-zinc-700 mx-auto" />
            <div>
              <p className="text-sm font-medium text-zinc-300">No rankings yet</p>
              <p className="text-xs text-zinc-500 mt-1">
                Click &ldquo;Run Ranking&rdquo; to generate multi-signal scores for your candidates.
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* Rankings list */}
      {!loading && rankings.length > 0 && (
        <div className="space-y-3">
          {rankings.map((candidate, idx) => (
            <RankCard key={candidate.id} candidate={candidate} rank={idx + 1} />
          ))}
        </div>
      )}
    </div>
  );
}
