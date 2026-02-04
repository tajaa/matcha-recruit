import { Modal } from '../Modal';
import type { IRCategorizationAnalysis } from '../../types';

interface CategorizationAnalysisModalProps {
  isOpen: boolean;
  onClose: () => void;
  analysis: IRCategorizationAnalysis | null;
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

export function CategorizationAnalysisModal({
  isOpen,
  onClose,
  analysis,
}: CategorizationAnalysisModalProps) {
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

  const confidencePercent = (analysis.confidence * 100).toFixed(0);

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Category Analysis">
      <div className="space-y-5">
        {/* Suggested Type */}
        <div>
          <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-2">
            Suggested Type
          </div>
          <div
            className={`inline-flex items-center gap-2 px-3 py-1.5 rounded border ${TYPE_COLORS[analysis.suggested_type]}`}
          >
            <span className="text-sm font-medium">
              {TYPE_LABELS[analysis.suggested_type]}
            </span>
          </div>
        </div>

        {/* Confidence */}
        <div>
          <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-2">
            Confidence
          </div>
          <div className="flex items-center gap-3">
            <div className="flex-1 bg-zinc-800 h-2 rounded-full overflow-hidden">
              <div
                className="bg-blue-500 h-full transition-all"
                style={{ width: `${confidencePercent}%` }}
              />
            </div>
            <span className="text-sm text-white font-medium">{confidencePercent}%</span>
          </div>
        </div>

        {/* Reasoning */}
        <div>
          <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-2">
            Reasoning
          </div>
          <div className="text-sm text-zinc-300 leading-relaxed whitespace-pre-wrap">
            {analysis.reasoning}
          </div>
        </div>

        {/* Metadata */}
        <div className="pt-4 border-t border-zinc-800 space-y-2 text-[10px]">
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
