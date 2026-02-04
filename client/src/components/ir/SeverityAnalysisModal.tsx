import { Modal } from '../Modal';
import type { IRSeverityAnalysis } from '../../types';

interface SeverityAnalysisModalProps {
  isOpen: boolean;
  onClose: () => void;
  analysis: IRSeverityAnalysis | null;
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'bg-red-600/20 text-red-400 border-red-600/30',
  high: 'bg-orange-600/20 text-orange-400 border-orange-600/30',
  medium: 'bg-yellow-600/20 text-yellow-400 border-yellow-600/30',
  low: 'bg-green-600/20 text-green-400 border-green-600/30',
};

const SEVERITY_DOT_COLORS: Record<string, string> = {
  critical: 'bg-red-600',
  high: 'bg-orange-500',
  medium: 'bg-yellow-500',
  low: 'bg-green-500',
};

export function SeverityAnalysisModal({
  isOpen,
  onClose,
  analysis,
}: SeverityAnalysisModalProps) {
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
    <Modal isOpen={isOpen} onClose={onClose} title="Severity Analysis">
      <div className="space-y-5">
        {/* Suggested Severity */}
        <div>
          <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-2">
            Suggested Severity
          </div>
          <div
            className={`inline-flex items-center gap-2 px-4 py-2 rounded border ${SEVERITY_COLORS[analysis.suggested_severity]}`}
          >
            <div className={`w-2.5 h-2.5 rounded-full ${SEVERITY_DOT_COLORS[analysis.suggested_severity]}`} />
            <span className="text-base font-medium capitalize">
              {analysis.suggested_severity}
            </span>
          </div>
        </div>

        {/* Contributing Factors */}
        {analysis.factors.length > 0 && (
          <div>
            <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-2">
              Contributing Factors
            </div>
            <ul className="space-y-2">
              {analysis.factors.map((factor, idx) => (
                <li key={idx} className="flex items-start gap-2 text-sm text-zinc-300">
                  <span className="text-zinc-600 mt-0.5">•</span>
                  <span>{factor}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Reasoning */}
        <div>
          <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-2">
            Detailed Reasoning
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
