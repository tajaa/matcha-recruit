import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { tutorMetrics } from '../api/client';
import type { TutorSessionSummary, TutorMetricsAggregate, TutorProgressDataPoint, TutorVocabularyStats } from '../types';
import { Activity, BarChart2, Book, Trash2, Clock, CheckCircle2 } from 'lucide-react';

type TabValue = 'all' | 'interview_prep' | 'language_test' | 'company_tool';

const TABS: { label: string; value: TabValue }[] = [
  { label: 'All Sessions', value: 'all' },
  { label: 'User Interview Prep', value: 'interview_prep' },
  { label: 'User Language Test', value: 'language_test' },
  { label: 'Company Interviews', value: 'company_tool' },
];

const STATUS_COLORS: Record<string, string> = {
  completed: 'text-emerald-400 bg-emerald-900/20 border-emerald-900/50',
  analyzing: 'text-amber-400 bg-amber-900/20 border-amber-900/50',
  in_progress: 'text-blue-400 bg-blue-900/20 border-blue-900/50',
  pending: 'text-zinc-400 bg-zinc-800 border-zinc-700',
};

function ScoreDisplay({ score, label }: { score: number | null; label?: string }) {
  if (score === null) return <span className="text-zinc-600 font-mono">-</span>;

  const getColor = (s: number) => {
    if (s >= 80) return 'text-emerald-400';
    if (s >= 60) return 'text-amber-400';
    return 'text-red-400';
  };

  return (
    <span className={`${getColor(score)} font-mono font-bold`}>
      {label && <span className="text-zinc-500 mr-2 font-sans uppercase text-[10px] tracking-wider">{label}</span>}
      {score}
    </span>
  );
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatShortDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  });
}

function isCompanyInterviewType(type: TutorSessionSummary['interview_type']) {
  return type === 'culture' || type === 'screening' || type === 'candidate';
}

function getSessionTypeLabel(type: TutorSessionSummary['interview_type']) {
  if (type === 'tutor_interview') return 'Interview Prep';
  if (type === 'tutor_language') return 'Language Test';
  if (type === 'culture') return 'Culture Interview';
  if (type === 'screening') return 'Screening Interview';
  return 'Culture Fit Interview';
}

function getSessionContext(session: TutorSessionSummary) {
  if (session.interview_type === 'tutor_language') {
    return session.language === 'en' ? 'English' : session.language === 'es' ? 'Spanish' : '—';
  }
  if (isCompanyInterviewType(session.interview_type)) {
    return session.company_name || 'Company';
  }
  return 'User Coaching';
}

function ProgressChart({ data, title, color }: { data: TutorProgressDataPoint[]; title: string; color: string }) {
  if (!data.length) return null;

  const scores = data.map((d) => {
    if (title === 'Fluency') return d.fluency_score;
    if (title === 'Grammar') return d.grammar_score;
    if (title === 'Vocabulary') return d.vocabulary_score;
    return null;
  }).filter((s): s is number => s !== null);

  if (!scores.length) return null;

  const max = Math.max(...scores, 100);
  const min = Math.min(...scores, 0);

  return (
    <div className="bg-zinc-900/50 border border-white/5 p-4 rounded-sm">
      <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-4 font-bold">{title}</div>
      <div className="flex items-end gap-1 h-32">
        {data.map((point, idx) => {
          const score = title === 'Fluency' ? point.fluency_score
            : title === 'Grammar' ? point.grammar_score
            : point.vocabulary_score;
          if (score === null) return <div key={idx} className="flex-1" />;
          const height = ((score - min) / (max - min)) * 100;
          return (
            <div
              key={idx}
              className={`flex-1 ${color} hover:opacity-100 opacity-60 transition-opacity rounded-t-sm cursor-pointer relative group`}
              style={{ height: `${Math.max(height, 5)}%` }}
            >
              <div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 hidden group-hover:block bg-zinc-950 border border-zinc-800 p-2 text-xs whitespace-nowrap z-10 shadow-xl">
                <div className="font-bold text-white font-mono">{score}</div>
                <div className="text-zinc-500 text-[10px] uppercase tracking-wide">{formatShortDate(point.date)}</div>
              </div>
            </div>
          );
        })}
      </div>
      <div className="flex justify-between mt-2 pt-2 border-t border-white/5">
        <span className="text-[9px] text-zinc-600 uppercase font-mono">{data[0] ? formatShortDate(data[0].date) : ''}</span>
        <span className="text-[9px] text-zinc-600 uppercase font-mono">{data[data.length - 1] ? formatShortDate(data[data.length - 1].date) : ''}</span>
      </div>
    </div>
  );
}

function ProficiencyTimeline({ data }: { data: TutorProgressDataPoint[] }) {
  if (!data.length) return null;

  const levels = data.filter(d => d.proficiency_level).map(d => d.proficiency_level);
  if (!levels.length) return null;

  const levelOrder = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2'];
  const getColor = (level: string) => {
    const idx = levelOrder.indexOf(level);
    if (idx <= 1) return 'bg-red-500';
    if (idx <= 3) return 'bg-amber-500';
    return 'bg-emerald-500';
  };

  return (
    <div className="border-t border-white/10 pt-6 mt-6">
      <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-4 font-bold flex items-center gap-2">
         <Activity size={12} /> CEFR Level Progression
      </div>
      <div className="flex gap-3 items-center overflow-x-auto pb-2">
        {data.map((point, idx) => {
          if (!point.proficiency_level) return null;
          return (
            <div key={idx} className="flex flex-col items-center group cursor-default">
              <div className={`w-8 h-8 rounded bg-zinc-900 border border-zinc-800 flex items-center justify-center text-xs font-bold text-white group-hover:border-zinc-600 transition-colors relative overflow-hidden`}>
                 <div className={`absolute bottom-0 left-0 right-0 h-1 ${getColor(point.proficiency_level)}`} />
                 {point.proficiency_level}
              </div>
              <div className="text-[9px] text-zinc-600 mt-2 font-mono uppercase">{formatShortDate(point.date)}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function VocabularySection({ vocab }: { vocab: TutorVocabularyStats }) {
  return (
    <div className="bg-zinc-900 border border-white/10 p-6">
      <h3 className="text-xs font-bold text-white uppercase tracking-wider mb-6 flex items-center gap-2">
         <Book size={14} className="text-zinc-500" />
         Vocabulary Analysis <span className="text-zinc-600 ml-2 font-mono">({vocab.total_unique_words} words)</span>
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Mastered Words */}
        <div className="bg-zinc-950 border border-zinc-800 p-4">
          <div className="text-[10px] text-emerald-500 uppercase tracking-widest mb-3 font-bold">Mastered</div>
          <div className="space-y-2">
            {vocab.mastered_words.length === 0 ? (
              <div className="text-xs text-zinc-600 font-mono">No data yet</div>
            ) : (
              vocab.mastered_words.slice(0, 5).map((w, i) => (
                <div key={i} className="flex items-center justify-between text-sm group">
                  <span className="text-zinc-300 font-medium group-hover:text-white transition-colors">{w.word}</span>
                  <span className="text-zinc-600 text-xs font-mono bg-zinc-900 px-1.5 py-0.5 rounded">{w.times_used}x</span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Words to Review */}
        <div className="bg-zinc-950 border border-zinc-800 p-4">
          <div className="text-[10px] text-amber-500 uppercase tracking-widest mb-3 font-bold">Needs Review</div>
          <div className="space-y-2">
            {vocab.words_to_review.length === 0 ? (
              <div className="text-xs text-zinc-600 font-mono">No data yet</div>
            ) : (
              vocab.words_to_review.slice(0, 5).map((w, i) => (
                <div key={i} className="text-sm">
                  <div className="text-zinc-300 font-medium">{w.word}</div>
                  {w.correction && (
                    <div className="text-zinc-500 text-xs mt-0.5 flex items-center gap-1 font-mono">
                       <span className="text-amber-500/50">&rarr;</span> {w.correction}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>

        {/* Suggested Vocabulary */}
        <div className="bg-zinc-950 border border-zinc-800 p-4">
          <div className="text-[10px] text-blue-500 uppercase tracking-widest mb-3 font-bold">Suggested</div>
          <div className="space-y-2">
            {vocab.suggested_vocabulary.length === 0 ? (
              <div className="text-xs text-zinc-600 font-mono">No data yet</div>
            ) : (
              vocab.suggested_vocabulary.slice(0, 5).map((w, i) => (
                <div key={i} className="text-sm">
                  <span className="text-zinc-300 font-medium">{w.word}</span>
                  {w.meaning && (
                    <span className="text-zinc-500 text-xs block mt-0.5 ml-2 border-l border-zinc-800 pl-2">
                       {w.meaning}
                    </span>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export function TutorMetrics() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const companyId = searchParams.get('company_id');
  const [sessions, setSessions] = useState<TutorSessionSummary[]>([]);
  const [aggregate, setAggregate] = useState<TutorMetricsAggregate | null>(null);
  const [progress, setProgress] = useState<TutorProgressDataPoint[]>([]);
  const [vocabulary, setVocabulary] = useState<TutorVocabularyStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<TabValue>('all');
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const handleDelete = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent row click navigation
    if (!confirm('Are you sure you want to delete this session? This cannot be undone.')) {
      return;
    }
    setDeletingId(sessionId);
    try {
      await tutorMetrics.deleteSession(sessionId);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
    } catch (err) {
      console.error('Failed to delete session:', err);
      alert('Failed to delete session');
    } finally {
      setDeletingId(null);
    }
  };

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const mode = activeTab === 'all' ? undefined : activeTab;
      const shouldLoadLanguageInsights = (activeTab === 'all' || activeTab === 'language_test') && !companyId;
      const [sessionsData, aggregateData, progressData, vocabData] = await Promise.all([
        tutorMetrics.listSessions({ mode, company_id: companyId || undefined, limit: 100 }),
        tutorMetrics.getAggregateMetrics(companyId || undefined),
        shouldLoadLanguageInsights
          ? tutorMetrics.getProgress('es', 15)
          : Promise.resolve({ sessions: [] }),
        shouldLoadLanguageInsights
          ? tutorMetrics.getVocabularyStats('es', 10).catch(() => null)
          : Promise.resolve(null),
      ]);
      setSessions(sessionsData);
      setAggregate(aggregateData);
      setProgress(progressData.sessions ?? []);
      setVocabulary(vocabData);
    } catch (err) {
      console.error('Failed to fetch tutor metrics:', err);
    } finally {
      setLoading(false);
    }
  }, [activeTab, companyId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const filteredCompanyName = companyId && sessions.length > 0 ? sessions[0].company_name : null;

  return (
    <div className="max-w-7xl mx-auto space-y-12">
      {/* Header */}
      <div className="flex justify-between items-start border-b border-white/10 pb-8">
        <div>
          <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">Performance Metrics</h1>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">Language/User Coaching Metrics Kept Separate From Company Culture/Screening Metrics</p>
          
          {companyId && (
            <div className="mt-4 flex items-center gap-3">
              <div className="px-3 py-1 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[10px] font-bold uppercase tracking-widest rounded-sm">
                Filtered by: {filteredCompanyName || 'Company'}
              </div>
              <button 
                onClick={() => navigate('/app/admin/tutor-metrics')}
                className="text-[10px] text-zinc-500 hover:text-white uppercase tracking-widest underline underline-offset-4"
              >
                Clear Filter
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-8 border-b border-white/10 pb-px">
        {TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setActiveTab(tab.value)}
            className={`pb-3 text-[10px] font-bold uppercase tracking-widest transition-colors border-b-2 ${
              activeTab === tab.value
                ? 'border-white text-white'
                : 'border-transparent text-zinc-500 hover:text-zinc-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Aggregate Stats */}
      {aggregate && (
        <>
          {(activeTab === 'all' || activeTab === 'interview_prep' || activeTab === 'language_test') && (
            <div className="space-y-3">
              <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold">
                User Tool Metrics (Interview Prep + Language Practice)
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-px bg-white/10 border border-white/10">
                {activeTab !== 'language_test' && (
                  <>
                    <div className="bg-zinc-950 p-6">
                      <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-2">Prep Sessions</div>
                      <div className="text-3xl font-light text-white font-mono">
                        {aggregate.interview_prep.total_sessions}
                      </div>
                    </div>
                    <div className="bg-zinc-950 p-6">
                      <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-2">Avg Quality</div>
                      <div className="text-3xl font-light text-white">
                        <ScoreDisplay score={aggregate.interview_prep.avg_response_quality} />
                      </div>
                    </div>
                    <div className="bg-zinc-950 p-6">
                      <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-2">Communication</div>
                      <div className="text-3xl font-light text-white">
                        <ScoreDisplay score={aggregate.interview_prep.avg_communication_score} />
                      </div>
                    </div>
                  </>
                )}
                {activeTab !== 'interview_prep' && (
                  <>
                    <div className="bg-zinc-950 p-6">
                      <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-2">Language Sessions</div>
                      <div className="text-3xl font-light text-white font-mono">
                        {aggregate.language_test.total_sessions}
                      </div>
                    </div>
                    <div className="bg-zinc-950 p-6">
                      <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-2">Avg Fluency</div>
                      <div className="text-3xl font-light text-white">
                        <ScoreDisplay score={aggregate.language_test.avg_fluency_score} />
                      </div>
                    </div>
                    <div className="bg-zinc-950 p-6">
                      <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-2">Avg Grammar</div>
                      <div className="text-3xl font-light text-white">
                        <ScoreDisplay score={aggregate.language_test.avg_grammar_score} />
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>
          )}

          {(activeTab === 'all' || activeTab === 'company_tool') && (
            <div className="space-y-3">
              <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold">
                Company Tool Metrics (Culture + Screening + Candidate Fit)
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-px bg-white/10 border border-white/10">
                <div className="bg-zinc-950 p-6">
                  <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-3">Culture Interviews</div>
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-zinc-500">Sessions</span>
                      <span className="text-white font-mono">{aggregate.company_interviews.culture.total_sessions}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-zinc-500">Coverage</span>
                      <ScoreDisplay score={aggregate.company_interviews.culture.avg_coverage_score} />
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-zinc-500">Depth</span>
                      <ScoreDisplay score={aggregate.company_interviews.culture.avg_response_depth} />
                    </div>
                  </div>
                </div>

                <div className="bg-zinc-950 p-6">
                  <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-3">Candidate Fit Interviews</div>
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-zinc-500">Sessions</span>
                      <span className="text-white font-mono">{aggregate.company_interviews.candidate.total_sessions}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-zinc-500">Coverage</span>
                      <ScoreDisplay score={aggregate.company_interviews.candidate.avg_coverage_score} />
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-zinc-500">Depth</span>
                      <ScoreDisplay score={aggregate.company_interviews.candidate.avg_response_depth} />
                    </div>
                  </div>
                </div>

                <div className="bg-zinc-950 p-6">
                  <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-3">Screening Interviews</div>
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-zinc-500">Sessions</span>
                      <span className="text-white font-mono">{aggregate.company_interviews.screening.total_sessions}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-zinc-500">Overall</span>
                      <ScoreDisplay score={aggregate.company_interviews.screening.avg_overall_score} />
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-zinc-500">Communication</span>
                      <ScoreDisplay score={aggregate.company_interviews.screening.avg_communication_score} />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {activeTab === 'interview_prep' && aggregate?.interview_prep.common_improvement_areas.length ? (
          <div className="bg-zinc-900 border border-white/10 p-6 h-full">
            <h3 className="text-xs font-bold text-white uppercase tracking-wider mb-4 flex items-center gap-2">
              <CheckCircle2 size={14} className="text-zinc-500" />
              Interview Prep Focus Areas
            </h3>
            <div className="flex flex-wrap gap-2">
              {aggregate.interview_prep.common_improvement_areas.map((item, i) => (
                <span key={i} className="px-3 py-1 bg-zinc-950 border border-zinc-800 text-xs text-zinc-300 font-mono">
                  {item.area} <span className="text-zinc-600 ml-1">x{item.count}</span>
                </span>
              ))}
            </div>
          </div>
        ) : null}

        {activeTab === 'language_test' && aggregate?.language_test.common_grammar_errors.length ? (
          <div className="bg-zinc-900 border border-white/10 p-6 h-full">
            <h3 className="text-xs font-bold text-white uppercase tracking-wider mb-4 flex items-center gap-2">
              <Activity size={14} className="text-zinc-500" />
              Language Grammar Error Trends
            </h3>
            <div className="flex flex-wrap gap-2">
              {aggregate.language_test.common_grammar_errors.map((item, i) => (
                <span key={i} className="px-3 py-1 bg-zinc-950 border border-zinc-800 text-xs text-zinc-300 font-mono">
                  {item.type} <span className="text-zinc-600 ml-1">x{item.count}</span>
                </span>
              ))}
            </div>
          </div>
        ) : null}

        {activeTab === 'company_tool' && aggregate && (
          <>
            <div className="bg-zinc-900 border border-white/10 p-6 h-full">
              <h3 className="text-xs font-bold text-white uppercase tracking-wider mb-4 flex items-center gap-2">
                <CheckCircle2 size={14} className="text-zinc-500" />
                Culture Interview Missed Dimensions
              </h3>
              <div className="flex flex-wrap gap-2">
                {aggregate.company_interviews.culture.common_missed_dimensions.length === 0 ? (
                  <span className="text-xs text-zinc-600 font-mono">No missed dimensions recorded</span>
                ) : (
                  aggregate.company_interviews.culture.common_missed_dimensions.map((item, i) => (
                    <span key={i} className="px-3 py-1 bg-zinc-950 border border-zinc-800 text-xs text-zinc-300 font-mono">
                      {item.dimension} <span className="text-zinc-600 ml-1">x{item.count}</span>
                    </span>
                  ))
                )}
              </div>
            </div>

            <div className="bg-zinc-900 border border-white/10 p-6 h-full">
              <h3 className="text-xs font-bold text-white uppercase tracking-wider mb-4 flex items-center gap-2">
                <Activity size={14} className="text-zinc-500" />
                Screening Recommendations
              </h3>
              <div className="flex flex-wrap gap-2">
                {Object.entries(aggregate.company_interviews.screening.recommendation_breakdown).length === 0 ? (
                  <span className="text-xs text-zinc-600 font-mono">No screening recommendations yet</span>
                ) : (
                  Object.entries(aggregate.company_interviews.screening.recommendation_breakdown).map(([label, count]) => (
                    <span key={label} className="px-3 py-1 bg-zinc-950 border border-zinc-800 text-xs text-zinc-300 font-mono">
                      {label.replace('_', ' ')} <span className="text-zinc-600 ml-1">x{count}</span>
                    </span>
                  ))
                )}
              </div>
            </div>
          </>
        )}
      </div>

      {/* Progress Over Time */}
      {(activeTab === 'all' || activeTab === 'language_test') && progress.length > 1 && (
        <div className="bg-zinc-900 border border-white/10 p-6">
          <h3 className="text-xs font-bold text-white uppercase tracking-wider mb-6 flex items-center gap-2">
             <BarChart2 size={14} className="text-zinc-500" />
             Progress Velocity
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <ProgressChart data={progress} title="Fluency" color="bg-emerald-500" />
            <ProgressChart data={progress} title="Grammar" color="bg-blue-500" />
            <ProgressChart data={progress} title="Vocabulary" color="bg-violet-500" />
          </div>
          <ProficiencyTimeline data={progress} />
        </div>
      )}

      {/* Vocabulary Tracking */}
      {(activeTab === 'all' || activeTab === 'language_test') && vocabulary && (
        <VocabularySection vocab={vocabulary} />
      )}

      {/* Sessions Table */}
      <div className="space-y-px bg-white/10 border border-white/10">
        <div className="flex items-center gap-4 py-3 px-6 bg-zinc-950 text-[10px] text-zinc-500 uppercase tracking-widest border-b border-white/10">
          <div className="flex-1">Date / Type</div>
          <div className="w-48 text-right">Context</div>
          <div className="w-32 text-right">Score</div>
          <div className="w-32 text-right">Status</div>
          <div className="w-16"></div>
        </div>

        {loading ? (
          <div className="p-12 text-center text-xs text-zinc-500 uppercase tracking-wider bg-zinc-950">Loading sessions...</div>
        ) : sessions.length === 0 ? (
          <div className="p-12 text-center text-xs text-zinc-500 uppercase tracking-wider bg-zinc-950">No sessions recorded</div>
        ) : (
          sessions.map((session) => (
            <div
              key={session.id}
              onClick={() => navigate(isCompanyInterviewType(session.interview_type) ? `/app/analysis/${session.id}` : `/app/admin/tutor-metrics/${session.id}`)}
              className="group bg-zinc-950 hover:bg-zinc-900 transition-colors p-4 px-6 flex items-center gap-4 cursor-pointer"
            >
              <div className="flex-1">
                <div className="text-sm font-bold text-white mb-1">
                  {getSessionTypeLabel(session.interview_type)}
                </div>
                <div className="text-xs text-zinc-500 font-mono flex items-center gap-2">
                  <Clock size={10} />
                  {formatDate(session.created_at)}
                </div>
              </div>

              <div className="w-48 text-right">
                <span className="text-xs font-mono text-zinc-400 uppercase">
                  {getSessionContext(session)}
                </span>
              </div>

              <div className="w-32 text-right">
                <ScoreDisplay score={session.overall_score} />
              </div>

              <div className="w-32 flex justify-end">
                <span className={`px-2 py-1 text-[10px] font-bold uppercase tracking-wider border rounded-sm ${STATUS_COLORS[session.status] || 'bg-zinc-800 text-zinc-500 border-zinc-700'}`}>
                  {session.status}
                </span>
              </div>

              <div className="w-16 flex justify-end">
                <button
                  onClick={(e) => handleDelete(session.id, e)}
                  disabled={deletingId === session.id}
                  className="p-2 text-zinc-600 hover:text-red-500 hover:bg-red-500/10 rounded transition-colors disabled:opacity-50"
                  title="Delete session"
                >
                  {deletingId === session.id ? (
                    <div className="w-4 h-4 rounded-full border-2 border-zinc-600 border-t-transparent animate-spin" />
                  ) : (
                    <Trash2 size={14} />
                  )}
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default TutorMetrics;
