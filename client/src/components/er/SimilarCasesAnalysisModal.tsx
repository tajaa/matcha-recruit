import { Link } from 'react-router-dom';
import { Modal } from '../Modal';
import type { ERSimilarCasesAnalysis, ERSimilarCaseMatch } from '../../types';

interface SimilarCasesAnalysisModalProps {
  isOpen: boolean;
  onClose: () => void;
  analysis: ERSimilarCasesAnalysis | null;
  streaming?: boolean;
  messages?: { type: string; message: string; done?: boolean }[];
  error?: string | null;
  onRetry?: () => void;
  onRefresh?: () => void;
}

const CATEGORY_LABELS: Record<string, string> = {
  harassment: 'Harassment',
  discrimination: 'Discrimination',
  safety: 'Safety',
  retaliation: 'Retaliation',
  policy_violation: 'Policy Violation',
  misconduct: 'Misconduct',
  wage_hour: 'Wage & Hour',
  other: 'Other',
};

const CATEGORY_COLORS: Record<string, string> = {
  harassment: 'bg-red-600/20 text-red-400 border-red-600/30',
  discrimination: 'bg-purple-600/20 text-purple-400 border-purple-600/30',
  safety: 'bg-orange-600/20 text-orange-400 border-orange-600/30',
  retaliation: 'bg-amber-600/20 text-amber-400 border-amber-600/30',
  policy_violation: 'bg-blue-600/20 text-blue-400 border-blue-600/30',
  misconduct: 'bg-rose-600/20 text-rose-400 border-rose-600/30',
  wage_hour: 'bg-emerald-600/20 text-emerald-400 border-emerald-600/30',
  other: 'bg-zinc-600/20 text-zinc-400 border-zinc-600/30',
};

const OUTCOME_LABELS: Record<string, string> = {
  termination: 'Termination',
  disciplinary_action: 'Disciplinary Action',
  retraining: 'Retraining',
  no_action: 'No Action',
  resignation: 'Resignation',
  other: 'Other',
};

const OUTCOME_COLORS: Record<string, string> = {
  termination: 'text-red-400',
  disciplinary_action: 'text-orange-400',
  retraining: 'text-yellow-400',
  no_action: 'text-green-400',
  resignation: 'text-blue-400',
  other: 'text-zinc-400',
};

const OUTCOME_BAR_COLORS: Record<string, string> = {
  termination: 'bg-red-500',
  disciplinary_action: 'bg-orange-500',
  retraining: 'bg-yellow-500',
  no_action: 'bg-green-500',
  resignation: 'bg-blue-500',
  other: 'bg-zinc-500',
};

const STATUS_LABELS: Record<string, string> = {
  open: 'Open',
  in_review: 'In Review',
  pending_determination: 'Pending',
  closed: 'Closed',
};

const STATUS_DOT: Record<string, string> = {
  open: 'bg-blue-400',
  in_review: 'bg-yellow-400',
  pending_determination: 'bg-orange-400',
  closed: 'bg-zinc-500',
};

function OutcomeDistributionBar({ distribution }: { distribution: Record<string, number> }) {
  const total = Object.values(distribution).reduce((sum, n) => sum + n, 0);
  if (total === 0) return null;

  const entries = Object.entries(distribution).filter(([, count]) => count > 0);

  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-2">
        Outcome Distribution
      </div>
      <div className="flex h-3 rounded-full overflow-hidden bg-zinc-800">
        {entries.map(([outcome, count]) => (
          <div
            key={outcome}
            className={`${OUTCOME_BAR_COLORS[outcome] || 'bg-zinc-600'} transition-all`}
            style={{ width: `${(count / total) * 100}%` }}
            title={`${OUTCOME_LABELS[outcome] || outcome}: ${count}`}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
        {entries.map(([outcome, count]) => (
          <div key={outcome} className="flex items-center gap-1.5">
            <div className={`w-2 h-2 rounded-full ${OUTCOME_BAR_COLORS[outcome] || 'bg-zinc-600'}`} />
            <span className="text-[10px] text-zinc-500">
              {OUTCOME_LABELS[outcome] || outcome} ({count})
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function SimilarCaseCard({ match, onClose }: { match: ERSimilarCaseMatch; onClose: () => void }) {
  const formatDate = (dateStr: string) =>
    new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });

  return (
    <div className="bg-zinc-800/30 border border-zinc-800 rounded p-4 space-y-3">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <Link
              to={`/app/er/cases/${match.case_id}`}
              className="text-sm text-blue-400 hover:text-blue-300 font-mono transition-colors"
              onClick={onClose}
            >
              {match.case_number}
            </Link>
            <div className={`w-1.5 h-1.5 rounded-full ${STATUS_DOT[match.status] || 'bg-zinc-500'}`} />
            <span className="text-[10px] text-zinc-600">{STATUS_LABELS[match.status] || match.status}</span>
          </div>
          <div className="text-sm text-white mt-1 line-clamp-2">{match.title}</div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {match.category && (
            <div className={`inline-flex items-center px-2 py-0.5 rounded border text-[10px] ${CATEGORY_COLORS[match.category] || CATEGORY_COLORS.other}`}>
              {CATEGORY_LABELS[match.category] || match.category}
            </div>
          )}
          {match.outcome && (
            <span className={`text-[10px] font-medium ${OUTCOME_COLORS[match.outcome] || 'text-zinc-400'}`}>
              {OUTCOME_LABELS[match.outcome] || match.outcome}
            </span>
          )}
        </div>
      </div>

      {/* Common Factors */}
      {match.common_factors.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {match.common_factors.map((factor, i) => (
            <span key={i} className="text-[10px] text-zinc-400 bg-zinc-800 px-2 py-0.5 rounded">
              {factor}
            </span>
          ))}
        </div>
      )}

      {/* Relevance Note */}
      {match.relevance_note && (
        <div className="text-xs text-zinc-400 italic">{match.relevance_note}</div>
      )}

      {/* Resolution Details */}
      {(match.resolution_days !== null || match.outcome_effective !== null || match.closed_at) && (
        <div className="border-t border-zinc-800/50 pt-3">
          <div className="flex items-center gap-3 text-[10px]">
            {match.resolution_days !== null && (
              <span className="text-zinc-500">
                Resolved in <span className="text-zinc-300">{match.resolution_days}d</span>
              </span>
            )}
            {match.outcome_effective !== null && (
              <span className={match.outcome_effective ? 'text-green-500' : 'text-red-400'}>
                {match.outcome_effective ? 'Effective' : 'Recurred'}
              </span>
            )}
            {match.created_at && (
              <span className="text-zinc-600">{formatDate(match.created_at)}</span>
            )}
          </div>
        </div>
      )}

    </div>
  );
}

export function SimilarCasesAnalysisModal({
  isOpen,
  onClose,
  analysis,
  streaming,
  messages,
  error,
  onRetry,
  onRefresh,
}: SimilarCasesAnalysisModalProps) {
  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  // Show error state
  if (error && !streaming) {
    return (
      <Modal isOpen={isOpen} onClose={onClose} title="Similar Cases Analysis">
        <div className="space-y-4">
          <div className="bg-red-950/40 border border-red-800/50 rounded-md px-4 py-3">
            <div className="text-xs text-red-400 font-medium mb-1">Analysis Failed</div>
            <div className="text-xs text-red-300/70">{error}</div>
          </div>
          {onRetry && (
            <button
              onClick={onRetry}
              className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
            >
              Retry analysis
            </button>
          )}
        </div>
      </Modal>
    );
  }

  // Show streaming state when no analysis yet
  if (!analysis && streaming) {
    return (
      <Modal isOpen={isOpen} onClose={onClose} title="Similar Cases Analysis">
        <div className="space-y-4">
          <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-2">
            Analyzing...
          </div>
          <div className="space-y-2">
            {messages?.map((msg, i) => (
              <div key={i} className="flex items-center gap-2">
                {!msg.done ? (
                  <div className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
                ) : msg.type === 'error' ? (
                  <div className="w-2 h-2 rounded-full bg-red-400" />
                ) : (
                  <div className="w-2 h-2 rounded-full bg-green-400" />
                )}
                <span className={`text-xs ${msg.type === 'error' ? 'text-red-400' : 'text-zinc-400'}`}>
                  {msg.message}
                </span>
              </div>
            ))}
          </div>
        </div>
      </Modal>
    );
  }

  if (!analysis) return null;

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Similar Cases Analysis">
      <div className="space-y-5">
        {/* Pattern Summary */}
        {analysis.pattern_summary && (
          <div>
            <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-2">
              Pattern Summary
            </div>
            <div className="text-sm text-zinc-300 leading-relaxed">
              {analysis.pattern_summary}
            </div>
          </div>
        )}

        {/* Outcome Distribution */}
        {Object.keys(analysis.outcome_distribution).length > 0 && (
          <OutcomeDistributionBar distribution={analysis.outcome_distribution} />
        )}

        {/* Similar Case Matches */}
        <div>
          {(() => {
            const filteredMatches = analysis.matches.filter(m => m.similarity_score >= 0.5);
            return (
              <>
                <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-3">
                  Matches ({filteredMatches.length})
                </div>
                {filteredMatches.length === 0 ? (
                  <div className="text-sm text-zinc-500 italic">
                    No similar cases found
                  </div>
                ) : (
                  <div className="space-y-4">
                    {filteredMatches.map((match) => (
                      <SimilarCaseCard key={match.case_id} match={match} onClose={onClose} />
                    ))}
                  </div>
                )}
              </>
            );
          })()}
        </div>

        {/* Metadata */}
        <div className="pt-4 border-t border-zinc-800 space-y-2 text-[10px]">
          <div className="flex justify-between">
            <span className="text-zinc-600">Generated</span>
            <span className="text-zinc-400">{formatDate(analysis.generated_at)}</span>
          </div>
          {analysis.from_cache && (
            <div className="flex items-start gap-2 text-amber-500/70">
              <span>!</span>
              <div>
                <div>Cached result</div>
                {analysis.cache_reason && (
                  <div className="text-amber-500/50 mt-0.5">{analysis.cache_reason}</div>
                )}
              </div>
            </div>
          )}
          {onRefresh && (
            <button
              onClick={onRefresh}
              disabled={streaming}
              className="text-xs text-blue-400 hover:text-blue-300 disabled:text-zinc-600 transition-colors"
            >
              {streaming ? 'Refreshing...' : 'Refresh analysis'}
            </button>
          )}
        </div>
      </div>
    </Modal>
  );
}
