import { Modal } from '../Modal';
import type { IRRecommendationsAnalysis } from '../../types';
import { FeatureGuideTrigger } from '../../features/feature-guides';

interface RecommendationsAnalysisModalProps {
  isOpen: boolean;
  onClose: () => void;
  analysis: IRRecommendationsAnalysis | null;
}

const PRIORITY_COLORS: Record<string, string> = {
  immediate: 'bg-red-600/20 text-red-400 border-red-600/30',
  short_term: 'bg-orange-600/20 text-orange-400 border-orange-600/30',
  long_term: 'bg-blue-600/20 text-blue-400 border-blue-600/30',
};

const PRIORITY_LABELS: Record<string, string> = {
  immediate: 'Immediate',
  short_term: 'Short Term',
  long_term: 'Long Term',
};

export function RecommendationsAnalysisModal({
  isOpen,
  onClose,
  analysis,
}: RecommendationsAnalysisModalProps) {
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
    <Modal isOpen={isOpen} onClose={onClose} title="Recommended Actions">
      <div className="space-y-5">
        <FeatureGuideTrigger guideId="ir-recommendations" />
        {/* Summary */}
        {analysis.summary && (
          <div data-tour="ir-rec-summary">
            <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-2">
              Summary
            </div>
            <div className="text-sm text-zinc-300 leading-relaxed">
              {analysis.summary}
            </div>
          </div>
        )}

        {/* Recommendations */}
        <div data-tour="ir-rec-cards">
          <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-3">
            Recommended Actions ({analysis.recommendations.length})
          </div>
          <div className="space-y-4">
            {analysis.recommendations.map((rec, idx) => (
              <div
                key={idx}
                className="bg-zinc-800/30 border border-zinc-800 rounded p-4 space-y-3"
              >
                {/* Priority Badge */}
                <div className="flex items-center justify-between">
                  <span className="text-zinc-600 text-xs">Action {idx + 1}</span>
                  <span
                    className={`inline-flex items-center px-2 py-0.5 rounded border text-[10px] uppercase tracking-wider ${PRIORITY_COLORS[rec.priority]}`}
                  >
                    {PRIORITY_LABELS[rec.priority]}
                  </span>
                </div>

                {/* Action Description */}
                <div className="text-sm text-white leading-relaxed">{rec.action}</div>

                {/* Additional Details */}
                <div className="grid grid-cols-2 gap-3 pt-2 border-t border-zinc-800/50 text-xs">
                  {rec.responsible_party && (
                    <div>
                      <div className="text-[10px] text-zinc-600 mb-1">Responsible Party</div>
                      <div className="text-zinc-400">{rec.responsible_party}</div>
                    </div>
                  )}
                  {rec.estimated_effort && (
                    <div>
                      <div className="text-[10px] text-zinc-600 mb-1">Estimated Effort</div>
                      <div className="text-zinc-400">{rec.estimated_effort}</div>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Metadata */}
        <div data-tour="ir-rec-meta" className="pt-4 border-t border-zinc-800 space-y-2 text-[10px]">
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
