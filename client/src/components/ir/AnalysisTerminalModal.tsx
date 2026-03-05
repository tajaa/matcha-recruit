import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import type {
  AnalysisStreamMessage,
  AnalysisType,
} from '../../hooks/ir/useIRAnalysisStream';
import type {
  IRRootCauseAnalysis,
  IRRecommendationsAnalysis,
  IRPrecedentAnalysis,
  IRPrecedentMatch,
  IRScoreBreakdown,
} from '../../types';

interface AnalysisTerminalModalProps {
  isOpen: boolean;
  onClose: () => void;
  messages: AnalysisStreamMessage[];
  streaming: boolean;
  result: IRRootCauseAnalysis | IRRecommendationsAnalysis | IRPrecedentAnalysis | null;
  error: string | null;
  analysisType: AnalysisType | null;
}

const TYPE_TITLES: Record<AnalysisType, string> = {
  root_cause: 'Root Cause Analysis',
  recommendations: 'Recommended Actions',
  similar: 'Precedent Analysis',
};

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

// ── Terminal Line ──
function TerminalLine({ msg, isLast, streaming }: { msg: AnalysisStreamMessage; isLast: boolean; streaming: boolean }) {
  const isActive = isLast && streaming && !msg.done;

  const iconColor = msg.type === 'error'
    ? 'text-red-400'
    : msg.type === 'cached'
    ? 'text-amber-400'
    : msg.done
    ? 'text-emerald-400'
    : 'text-cyan-400';

  const icon = msg.type === 'error'
    ? '✗'
    : msg.type === 'cached'
    ? '⚡'
    : msg.done
    ? '✓'
    : '›';

  return (
    <div className={`flex items-start gap-2 font-mono text-xs leading-relaxed ${isActive ? 'animate-pulse' : ''}`}>
      <span className="text-zinc-600 shrink-0 select-none">[{formatTime(msg.timestamp)}]</span>
      <span className={`shrink-0 w-3 text-center ${iconColor}`}>{icon}</span>
      <span className={msg.type === 'error' ? 'text-red-400' : msg.type === 'cached' ? 'text-amber-400' : 'text-zinc-300'}>
        {msg.message}
      </span>
      {isActive && (
        <span className="inline-block w-1.5 h-3.5 bg-cyan-400 ml-0.5 animate-[blink_1s_steps(1)_infinite]" />
      )}
    </div>
  );
}

// ── Result Renderers ──

function RootCauseResult({ analysis }: { analysis: IRRootCauseAnalysis }) {
  return (
    <div className="space-y-4">
      <div>
        <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-2">Primary Cause</div>
        <div className="bg-zinc-800/50 border border-zinc-700 rounded px-4 py-3">
          <p className="text-sm text-white leading-relaxed">{analysis.primary_cause}</p>
        </div>
      </div>

      {analysis.contributing_factors.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-2">Contributing Factors</div>
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

      {analysis.prevention_suggestions.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-2">Prevention Suggestions</div>
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

      <div>
        <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-2">Detailed Analysis</div>
        <div className="text-sm text-zinc-300 leading-relaxed whitespace-pre-wrap">{analysis.reasoning}</div>
      </div>
    </div>
  );
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

function RecommendationsResult({ analysis }: { analysis: IRRecommendationsAnalysis }) {
  return (
    <div className="space-y-4">
      {analysis.summary && (
        <div>
          <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-2">Summary</div>
          <div className="text-sm text-zinc-300 leading-relaxed">{analysis.summary}</div>
        </div>
      )}

      <div>
        <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-3">
          Recommended Actions ({analysis.recommendations.length})
        </div>
        <div className="space-y-4">
          {analysis.recommendations.map((rec, idx) => (
            <div key={idx} className="bg-zinc-800/30 border border-zinc-800 rounded p-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-zinc-600 text-xs">Action {idx + 1}</span>
                <span className={`inline-flex items-center px-2 py-0.5 rounded border text-[10px] uppercase tracking-wider ${PRIORITY_COLORS[rec.priority]}`}>
                  {PRIORITY_LABELS[rec.priority]}
                </span>
              </div>
              <div className="text-sm text-white leading-relaxed">{rec.action}</div>
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
    </div>
  );
}

// Precedent score bar dimensions and labels
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
const TYPE_COLORS: Record<string, string> = {
  safety: 'bg-red-600/20 text-red-400 border-red-600/30',
  behavioral: 'bg-amber-600/20 text-amber-400 border-amber-600/30',
  property: 'bg-blue-600/20 text-blue-400 border-blue-600/30',
  near_miss: 'bg-yellow-600/20 text-yellow-400 border-yellow-600/30',
  other: 'bg-zinc-600/20 text-zinc-400 border-zinc-600/30',
};
const TYPE_LABELS: Record<string, string> = {
  safety: 'Safety',
  behavioral: 'Behavioral',
  property: 'Property',
  near_miss: 'Near Miss',
  other: 'Other',
};
const STATUS_DOT: Record<string, string> = {
  reported: 'bg-blue-400',
  investigating: 'bg-yellow-400',
  action_required: 'bg-orange-400',
  resolved: 'bg-green-400',
  closed: 'bg-zinc-500',
};
const STATUS_LABELS: Record<string, string> = {
  reported: 'Reported',
  investigating: 'Investigating',
  action_required: 'Action Required',
  resolved: 'Resolved',
  closed: 'Closed',
};

function PrecedentCardInline({ precedent, onClose }: { precedent: IRPrecedentMatch; onClose: () => void }) {
  const [expanded, setExpanded] = useState(false);

  const getBarColor = (score: number) => score >= 0.7 ? 'bg-green-500' : score >= 0.5 ? 'bg-yellow-500' : 'bg-orange-500';
  const getTextColor = (score: number) => score >= 0.7 ? 'text-green-400' : score >= 0.5 ? 'text-yellow-400' : 'text-orange-400';

  const formatDate = (dateStr: string) =>
    new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });

  return (
    <div className="bg-zinc-800/30 border border-zinc-800 rounded p-4 space-y-3">
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

      <div className="flex items-center gap-3">
        <div className="flex-1 bg-zinc-800 h-2 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${getBarColor(precedent.similarity_score)}`}
            style={{ width: `${precedent.similarity_score * 100}%` }}
          />
        </div>
        <span className={`text-sm font-medium ${getTextColor(precedent.similarity_score)}`}>
          {(precedent.similarity_score * 100).toFixed(0)}%
        </span>
      </div>

      {precedent.common_factors.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {precedent.common_factors.map((factor, i) => (
            <span key={i} className="text-[10px] text-zinc-400 bg-zinc-800 px-2 py-0.5 rounded">{factor}</span>
          ))}
        </div>
      )}

      {(precedent.root_cause || precedent.corrective_actions || precedent.resolution_days !== null) && (
        <div className="border-t border-zinc-800/50 pt-3 space-y-2">
          <div className="flex items-center gap-3 text-[10px]">
            {precedent.resolution_days !== null && (
              <span className="text-zinc-500">Resolved in <span className="text-zinc-300">{precedent.resolution_days}d</span></span>
            )}
            {precedent.resolution_effective !== null && (
              <span className={precedent.resolution_effective ? 'text-green-500' : 'text-red-400'}>
                {precedent.resolution_effective ? 'Effective' : 'Recurred'}
              </span>
            )}
            {precedent.occurred_at && <span className="text-zinc-600">{formatDate(precedent.occurred_at)}</span>}
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

      <button onClick={() => setExpanded(!expanded)} className="text-[10px] text-zinc-600 hover:text-zinc-400 transition-colors">
        {expanded ? 'Hide' : 'Show'} score breakdown
      </button>
      {expanded && (
        <div className="space-y-1.5 pt-1">
          {(Object.keys(DIMENSION_LABELS) as (keyof IRScoreBreakdown)[]).map((dim) => (
            <div key={dim} className="flex items-center gap-2">
              <span className="text-[10px] text-zinc-600 w-16 shrink-0">{DIMENSION_LABELS[dim]}</span>
              <div className="flex-1 bg-zinc-800 h-1.5 rounded-full overflow-hidden">
                <div className={`h-full rounded-full ${DIMENSION_COLORS[dim]}`} style={{ width: `${Math.max(precedent.score_breakdown[dim] * 100, 1)}%` }} />
              </div>
              <span className="text-[10px] text-zinc-500 w-7 text-right">{(precedent.score_breakdown[dim] * 100).toFixed(0)}%</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function PrecedentsResult({ analysis, onClose }: { analysis: IRPrecedentAnalysis; onClose: () => void }) {
  return (
    <div className="space-y-4">
      {analysis.pattern_summary && (
        <div>
          <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-2">Pattern Summary</div>
          <div className="text-sm text-zinc-300 leading-relaxed">{analysis.pattern_summary}</div>
        </div>
      )}

      <div>
        <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-3">
          Precedents ({analysis.precedents.length})
        </div>
        {analysis.precedents.length === 0 ? (
          <div className="text-sm text-zinc-500 italic">No precedent incidents found</div>
        ) : (
          <div className="space-y-4">
            {analysis.precedents.map((p) => (
              <PrecedentCardInline key={p.incident_id} precedent={p} onClose={onClose} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main Modal ──

export function AnalysisTerminalModal({
  isOpen,
  onClose,
  messages,
  streaming,
  result,
  error,
  analysisType,
}: AnalysisTerminalModalProps) {
  const terminalRef = useRef<HTMLDivElement>(null);

  // Auto-scroll terminal
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [messages]);

  // Escape to close
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !streaming) onClose();
    };
    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = '';
    };
  }, [isOpen, onClose, streaming]);

  if (!isOpen) return null;

  const title = analysisType ? TYPE_TITLES[analysisType] : 'Analysis';
  const isCached = result && 'from_cache' in result && result.from_cache;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={streaming ? undefined : onClose} />
      <div className="relative bg-zinc-950 border border-zinc-800 rounded-lg w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800/50">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <div className={`w-2.5 h-2.5 rounded-full ${streaming ? 'bg-green-500 animate-pulse' : error ? 'bg-red-500' : 'bg-emerald-500'}`} />
              <div className="w-2.5 h-2.5 rounded-full bg-zinc-700" />
              <div className="w-2.5 h-2.5 rounded-full bg-zinc-700" />
            </div>
            <span className="text-xs text-zinc-400 font-mono">{title}</span>
          </div>
          {!streaming && (
            <button onClick={onClose} className="text-zinc-600 hover:text-zinc-400 text-xs font-mono">
              [ESC]
            </button>
          )}
        </div>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto min-h-0">
          {/* Terminal */}
          <div ref={terminalRef} className="bg-zinc-950 px-4 py-3 space-y-1">
            {messages.map((msg, idx) => (
              <TerminalLine
                key={idx}
                msg={msg}
                isLast={idx === messages.length - 1}
                streaming={streaming}
              />
            ))}
            {messages.length === 0 && streaming && (
              <div className="text-xs text-zinc-600 font-mono animate-pulse">Initializing...</div>
            )}
          </div>

          {/* Results */}
          {result && !streaming && (
            <div className="border-t border-zinc-800 px-4 py-4">
              {isCached && (
                <div className="flex items-center gap-2 text-amber-500/70 text-[10px] mb-4">
                  <span>⚠</span>
                  <span>Cached result</span>
                </div>
              )}

              {analysisType === 'root_cause' && (
                <RootCauseResult analysis={result as IRRootCauseAnalysis} />
              )}
              {analysisType === 'recommendations' && (
                <RecommendationsResult analysis={result as IRRecommendationsAnalysis} />
              )}
              {analysisType === 'similar' && (
                <PrecedentsResult analysis={result as IRPrecedentAnalysis} onClose={onClose} />
              )}
            </div>
          )}

          {/* Error state */}
          {error && !streaming && !result && (
            <div className="border-t border-zinc-800 px-4 py-4">
              <div className="text-sm text-red-400">{error}</div>
            </div>
          )}
        </div>

        {/* Footer */}
        {!streaming && result && (
          <div className="border-t border-zinc-800/50 px-4 py-2 flex justify-end">
            <button onClick={onClose} className="text-xs text-zinc-500 hover:text-white uppercase tracking-wider">
              Close
            </button>
          </div>
        )}
      </div>

      <style>{`
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
      `}</style>
    </div>
  );
}
