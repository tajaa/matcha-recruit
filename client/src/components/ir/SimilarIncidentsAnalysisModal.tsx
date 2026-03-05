import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Modal } from '../Modal';
import type { IRPrecedentAnalysis, IRPrecedentMatch, IRScoreBreakdown } from '../../types';
import { FeatureGuideTrigger } from '../../features/feature-guides';

interface SimilarIncidentsAnalysisModalProps {
  isOpen: boolean;
  onClose: () => void;
  analysis: IRPrecedentAnalysis | null;
}

const TYPE_LABELS: Record<string, string> = {
  safety: 'Safety',
  behavioral: 'Behavioral',
  property: 'Property',
  near_miss: 'Near Miss',
  other: 'Other',
};

const TYPE_COLORS: Record<string, string> = {
  safety: 'bg-red-600/20 text-red-400 border-red-600/30',
  behavioral: 'bg-amber-600/20 text-amber-400 border-amber-600/30',
  property: 'bg-blue-600/20 text-blue-400 border-blue-600/30',
  near_miss: 'bg-yellow-600/20 text-yellow-400 border-yellow-600/30',
  other: 'bg-zinc-600/20 text-zinc-400 border-zinc-600/30',
};

const STATUS_LABELS: Record<string, string> = {
  reported: 'Reported',
  investigating: 'Investigating',
  action_required: 'Action Required',
  resolved: 'Resolved',
  closed: 'Closed',
};

const STATUS_DOT: Record<string, string> = {
  reported: 'bg-blue-400',
  investigating: 'bg-yellow-400',
  action_required: 'bg-orange-400',
  resolved: 'bg-green-400',
  closed: 'bg-zinc-500',
};

const DIMENSION_LABELS: Record<keyof IRScoreBreakdown, string> = {
  type_match: 'Type',
  severity_proximity: 'Severity',
  category_overlap: 'Category',
  location_similarity: 'Location',
  temporal_pattern: 'Temporal',
  text_similarity: 'Text',
  root_cause_similarity: 'Root Cause',
};

const DIMENSION_COLORS: Record<keyof IRScoreBreakdown, string> = {
  type_match: 'bg-violet-500',
  severity_proximity: 'bg-orange-500',
  category_overlap: 'bg-cyan-500',
  location_similarity: 'bg-emerald-500',
  temporal_pattern: 'bg-pink-500',
  text_similarity: 'bg-blue-500',
  root_cause_similarity: 'bg-amber-500',
};

function ScoreBar({ label, score, color }: { label: string; score: number; color: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] text-zinc-600 w-16 shrink-0">{label}</span>
      <div className="flex-1 bg-zinc-800 h-1.5 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${color}`}
          style={{ width: `${Math.max(score * 100, 1)}%` }}
        />
      </div>
      <span className="text-[10px] text-zinc-500 w-7 text-right">{(score * 100).toFixed(0)}%</span>
    </div>
  );
}

function PrecedentCard({ precedent, onClose }: { precedent: IRPrecedentMatch; onClose: () => void }) {
  const [expanded, setExpanded] = useState(false);

  const getSimilarityColor = (score: number): string => {
    if (score >= 0.7) return 'text-green-400';
    if (score >= 0.5) return 'text-yellow-400';
    return 'text-orange-400';
  };

  const getBarColor = (score: number): string => {
    if (score >= 0.7) return 'bg-green-500';
    if (score >= 0.5) return 'bg-yellow-500';
    return 'bg-orange-500';
  };

  const formatDate = (dateStr: string) =>
    new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });

  return (
    <div className="bg-zinc-800/30 border border-zinc-800 rounded p-4 space-y-3">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <Link
              to={`/app/ir/incidents/${precedent.incident_id}`}
              className="text-sm text-blue-400 hover:text-blue-300 font-mono transition-colors"
              onClick={onClose}
            >
              {precedent.incident_number}
            </Link>
            <div className={`w-1.5 h-1.5 rounded-full ${STATUS_DOT[precedent.status] || 'bg-zinc-500'}`} />
            <span className="text-[10px] text-zinc-600">{STATUS_LABELS[precedent.status] || precedent.status}</span>
          </div>
          <div className="text-sm text-white mt-1 line-clamp-2">{precedent.title}</div>
        </div>
        <div className={`inline-flex items-center px-2 py-0.5 rounded border text-[10px] shrink-0 ${TYPE_COLORS[precedent.incident_type]}`}>
          {TYPE_LABELS[precedent.incident_type]}
        </div>
      </div>

      {/* Overall Similarity Score */}
      <div>
        <div className="flex items-center gap-3">
          <div className="flex-1 bg-zinc-800 h-2 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${getBarColor(precedent.similarity_score)}`}
              style={{ width: `${precedent.similarity_score * 100}%` }}
            />
          </div>
          <span className={`text-sm font-medium ${getSimilarityColor(precedent.similarity_score)}`}>
            {(precedent.similarity_score * 100).toFixed(0)}%
          </span>
        </div>
      </div>

      {/* Common Factors */}
      {precedent.common_factors.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {precedent.common_factors.map((factor, i) => (
            <span key={i} className="text-[10px] text-zinc-400 bg-zinc-800 px-2 py-0.5 rounded">
              {factor}
            </span>
          ))}
        </div>
      )}

      {/* Resolution Details (inline) */}
      {(precedent.root_cause || precedent.corrective_actions || precedent.resolution_days !== null) && (
        <div className="border-t border-zinc-800/50 pt-3 space-y-2">
          <div className="flex items-center gap-3 text-[10px]">
            {precedent.resolution_days !== null && (
              <span className="text-zinc-500">
                Resolved in <span className="text-zinc-300">{precedent.resolution_days}d</span>
              </span>
            )}
            {precedent.resolution_effective !== null && (
              <span className={precedent.resolution_effective ? 'text-green-500' : 'text-red-400'}>
                {precedent.resolution_effective ? 'Effective' : 'Recurred'}
              </span>
            )}
            {precedent.occurred_at && (
              <span className="text-zinc-600">{formatDate(precedent.occurred_at)}</span>
            )}
          </div>
          {precedent.root_cause && (
            <div>
              <div className="text-[10px] text-zinc-600 mb-0.5">Root Cause</div>
              <div className="text-xs text-zinc-400 line-clamp-2">{precedent.root_cause}</div>
            </div>
          )}
          {precedent.corrective_actions && (
            <div>
              <div className="text-[10px] text-zinc-600 mb-0.5">Corrective Actions</div>
              <div className="text-xs text-zinc-400 line-clamp-2">{precedent.corrective_actions}</div>
            </div>
          )}
        </div>
      )}

      {/* Expandable Score Breakdown */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="text-[10px] text-zinc-600 hover:text-zinc-400 transition-colors"
      >
        {expanded ? 'Hide' : 'Show'} score breakdown
      </button>
      {expanded && (
        <div className="space-y-1.5 pt-1">
          {(Object.keys(DIMENSION_LABELS) as (keyof IRScoreBreakdown)[]).map((dim) => (
            <ScoreBar
              key={dim}
              label={DIMENSION_LABELS[dim]}
              score={precedent.score_breakdown[dim]}
              color={DIMENSION_COLORS[dim]}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function SimilarIncidentsAnalysisModal({
  isOpen,
  onClose,
  analysis,
}: SimilarIncidentsAnalysisModalProps) {
  if (!analysis) return null;

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Precedent Analysis">
      <div className="space-y-5">
        <FeatureGuideTrigger guideId="ir-similar" />

        {/* Pattern Summary */}
        {analysis.pattern_summary && (
          <div data-tour="ir-sim-pattern">
            <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-2">
              Pattern Summary
            </div>
            <div className="text-sm text-zinc-300 leading-relaxed">
              {analysis.pattern_summary}
            </div>
          </div>
        )}

        {/* Precedent Matches */}
        <div data-tour="ir-sim-cards">
          <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-3">
            Precedents ({analysis.precedents.length})
          </div>
          {analysis.precedents.length === 0 ? (
            <div className="text-sm text-zinc-500 italic">
              No precedent incidents found
            </div>
          ) : (
            <div className="space-y-4">
              {analysis.precedents.map((precedent) => (
                <PrecedentCard key={precedent.incident_id} precedent={precedent} onClose={onClose} />
              ))}
            </div>
          )}
        </div>

        {/* Metadata */}
        <div data-tour="ir-sim-meta" className="pt-4 border-t border-zinc-800 space-y-2 text-[10px]">
          <div className="flex justify-between">
            <span className="text-zinc-600">Generated</span>
            <span className="text-zinc-400">{formatDate(analysis.generated_at)}</span>
          </div>
          {analysis.from_cache && (
            <div className="flex items-start gap-2 text-amber-500/70">
              <span>⚠</span>
              <div>
                <div>Cached result</div>
                {analysis.cache_reason && (
                  <div className="text-amber-500/50 mt-0.5">{analysis.cache_reason}</div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}
