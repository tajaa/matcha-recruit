import { Modal } from '../Modal';
import type { IRRootCauseAnalysis } from '../../types';

interface RootCauseAnalysisModalProps {
  isOpen: boolean;
  onClose: () => void;
  analysis: IRRootCauseAnalysis | null;
}

export function RootCauseAnalysisModal({
  isOpen,
  onClose,
  analysis,
}: RootCauseAnalysisModalProps) {
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
    <Modal isOpen={isOpen} onClose={onClose} title="Root Cause Analysis">
      <div className="space-y-5">
        {/* Primary Cause */}
        <div>
          <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-2">
            Primary Cause
          </div>
          <div className="bg-zinc-800/50 border border-zinc-700 rounded px-4 py-3">
            <p className="text-sm text-white leading-relaxed">{analysis.primary_cause}</p>
          </div>
        </div>

        {/* Contributing Factors */}
        {analysis.contributing_factors.length > 0 && (
          <div>
            <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-2">
              Contributing Factors
            </div>
            <ul className="space-y-2">
              {analysis.contributing_factors.map((factor, idx) => (
                <li key={idx} className="flex items-start gap-2 text-sm text-zinc-300">
                  <span className="text-zinc-600 mt-0.5">•</span>
                  <span>{factor}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Prevention Suggestions */}
        {analysis.prevention_suggestions.length > 0 && (
          <div>
            <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-2">
              Prevention Suggestions
            </div>
            <ul className="space-y-2">
              {analysis.prevention_suggestions.map((suggestion, idx) => (
                <li key={idx} className="flex items-start gap-2 text-sm text-zinc-300">
                  <span className="text-green-600 mt-0.5">→</span>
                  <span>{suggestion}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Detailed Reasoning */}
        <div>
          <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-2">
            Detailed Analysis
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
