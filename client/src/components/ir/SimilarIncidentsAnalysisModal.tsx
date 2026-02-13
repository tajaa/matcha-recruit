import { Link } from 'react-router-dom';
import { Modal } from '../Modal';
import type { IRSimilarIncidentsAnalysis } from '../../types';
import { FeatureGuideTrigger } from '../../features/feature-guides';

interface SimilarIncidentsAnalysisModalProps {
  isOpen: boolean;
  onClose: () => void;
  analysis: IRSimilarIncidentsAnalysis | null;
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

  const getSimilarityColor = (score: number): string => {
    if (score >= 0.8) return 'text-green-400';
    if (score >= 0.6) return 'text-yellow-400';
    return 'text-orange-400';
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Similar Incidents">
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

        {/* Similar Incidents */}
        <div data-tour="ir-sim-cards">
          <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-3">
            Similar Incidents ({analysis.similar_incidents.length})
          </div>
          {analysis.similar_incidents.length === 0 ? (
            <div className="text-sm text-zinc-500 italic">
              No similar incidents found
            </div>
          ) : (
            <div className="space-y-4">
              {analysis.similar_incidents.map((incident) => (
                <div
                  key={incident.incident_id}
                  className="bg-zinc-800/30 border border-zinc-800 rounded p-4 space-y-3"
                >
                  {/* Header */}
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <Link
                        to={`/app/ir/incidents/${incident.incident_id}`}
                        className="text-sm text-blue-400 hover:text-blue-300 font-mono transition-colors"
                        onClick={onClose}
                      >
                        {incident.incident_number}
                      </Link>
                      <div className="text-sm text-white mt-1 line-clamp-2">
                        {incident.title}
                      </div>
                    </div>
                    <div
                      className={`inline-flex items-center px-2 py-0.5 rounded border text-[10px] ${TYPE_COLORS[incident.incident_type]}`}
                    >
                      {TYPE_LABELS[incident.incident_type]}
                    </div>
                  </div>

                  {/* Similarity Score */}
                  <div>
                    <div className="text-[10px] text-zinc-600 mb-1">Similarity</div>
                    <div className="flex items-center gap-3">
                      <div className="flex-1 bg-zinc-800 h-2 rounded-full overflow-hidden">
                        <div
                          className={`h-full transition-all ${
                            incident.similarity_score >= 0.8
                              ? 'bg-green-500'
                              : incident.similarity_score >= 0.6
                              ? 'bg-yellow-500'
                              : 'bg-orange-500'
                          }`}
                          style={{ width: `${incident.similarity_score * 100}%` }}
                        />
                      </div>
                      <span
                        className={`text-sm font-medium ${getSimilarityColor(incident.similarity_score)}`}
                      >
                        {(incident.similarity_score * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>

                  {/* Common Factors */}
                  {incident.common_factors.length > 0 && (
                    <div>
                      <div className="text-[10px] text-zinc-600 mb-2">Common Factors</div>
                      <ul className="space-y-1">
                        {incident.common_factors.map((factor, factorIdx) => (
                          <li
                            key={factorIdx}
                            className="flex items-start gap-2 text-xs text-zinc-400"
                          >
                            <span className="text-zinc-600 mt-0.5">•</span>
                            <span>{factor}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
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
