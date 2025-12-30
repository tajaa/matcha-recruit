import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent } from '../components';
import { tutorMetrics } from '../api/client';
import type { TutorSessionSummary, TutorMetricsAggregate, TutorProgressDataPoint, TutorVocabularyStats } from '../types';

type TabValue = 'all' | 'interview_prep' | 'language_test';

const TABS: { label: string; value: TabValue }[] = [
  { label: 'All Sessions', value: 'all' },
  { label: 'Interview Prep', value: 'interview_prep' },
  { label: 'Language Test', value: 'language_test' },
];

const STATUS_COLORS: Record<string, string> = {
  completed: 'bg-matcha-500/20 text-white',
  analyzing: 'bg-yellow-500/20 text-yellow-400',
  in_progress: 'bg-blue-500/20 text-blue-400',
  pending: 'bg-zinc-700 text-zinc-300',
};

function ScoreDisplay({ score, label }: { score: number | null; label?: string }) {
  if (score === null) return <span className="text-zinc-500">-</span>;

  const getColor = (s: number) => {
    if (s >= 80) return 'text-white';
    if (s >= 60) return 'text-yellow-400';
    return 'text-red-400';
  };

  return (
    <span className={getColor(score)}>
      {label && <span className="text-zinc-500 mr-1">{label}</span>}
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
    <div>
      <div className="text-xs text-zinc-400 mb-2">{title}</div>
      <div className="flex items-end gap-1 h-24">
        {data.map((point, idx) => {
          const score = title === 'Fluency' ? point.fluency_score
            : title === 'Grammar' ? point.grammar_score
            : point.vocabulary_score;
          if (score === null) return <div key={idx} className="flex-1" />;
          const height = ((score - min) / (max - min)) * 100;
          return (
            <div
              key={idx}
              className={`flex-1 ${color} hover:opacity-80 transition-opacity rounded-t cursor-pointer relative group`}
              style={{ height: `${Math.max(height, 5)}%` }}
            >
              <div className="absolute bottom-full mb-1 left-1/2 -translate-x-1/2 hidden group-hover:block bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs whitespace-nowrap z-10">
                <div className="font-medium text-white">{score}</div>
                <div className="text-zinc-400">{formatShortDate(point.date)}</div>
              </div>
            </div>
          );
        })}
      </div>
      <div className="flex justify-between mt-1">
        <span className="text-[10px] text-zinc-600">{data[0] ? formatShortDate(data[0].date) : ''}</span>
        <span className="text-[10px] text-zinc-600">{data[data.length - 1] ? formatShortDate(data[data.length - 1].date) : ''}</span>
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
    if (idx <= 3) return 'bg-yellow-500';
    return 'bg-matcha-500';
  };

  return (
    <div>
      <div className="text-xs text-zinc-400 mb-2">CEFR Level Progression</div>
      <div className="flex gap-2 items-center">
        {data.map((point, idx) => {
          if (!point.proficiency_level) return null;
          return (
            <div key={idx} className="flex flex-col items-center">
              <div className={`w-8 h-8 rounded-full ${getColor(point.proficiency_level)} flex items-center justify-center text-xs font-bold text-white`}>
                {point.proficiency_level}
              </div>
              <div className="text-[10px] text-zinc-600 mt-1">{formatShortDate(point.date)}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function VocabularySection({ vocab }: { vocab: TutorVocabularyStats }) {
  return (
    <Card>
      <CardContent className="p-4">
        <h3 className="text-sm font-medium text-zinc-400 mb-4">Spanish Vocabulary ({vocab.total_unique_words} words tracked)</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Mastered Words */}
          <div>
            <div className="text-xs text-zinc-500 mb-2">Mastered</div>
            <div className="space-y-1">
              {vocab.mastered_words.length === 0 ? (
                <div className="text-xs text-zinc-600">No mastered words yet</div>
              ) : (
                vocab.mastered_words.slice(0, 5).map((w, i) => (
                  <div key={i} className="flex items-center justify-between text-sm">
                    <span className="text-matcha-400">{w.word}</span>
                    <span className="text-zinc-600 text-xs">{w.times_used}x</span>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Words to Review */}
          <div>
            <div className="text-xs text-zinc-500 mb-2">Needs Review</div>
            <div className="space-y-1">
              {vocab.words_to_review.length === 0 ? (
                <div className="text-xs text-zinc-600">No words to review</div>
              ) : (
                vocab.words_to_review.slice(0, 5).map((w, i) => (
                  <div key={i} className="text-sm">
                    <span className="text-yellow-400">{w.word}</span>
                    {w.correction && (
                      <span className="text-zinc-500 text-xs ml-1">&rarr; {w.correction}</span>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Suggested Vocabulary */}
          <div>
            <div className="text-xs text-zinc-500 mb-2">Suggested to Learn</div>
            <div className="space-y-1">
              {vocab.suggested_vocabulary.length === 0 ? (
                <div className="text-xs text-zinc-600">No suggestions yet</div>
              ) : (
                vocab.suggested_vocabulary.slice(0, 5).map((w, i) => (
                  <div key={i} className="text-sm">
                    <span className="text-blue-400">{w.word}</span>
                    {w.meaning && (
                      <span className="text-zinc-500 text-xs ml-1">- {w.meaning}</span>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export function TutorMetrics() {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<TutorSessionSummary[]>([]);
  const [aggregate, setAggregate] = useState<TutorMetricsAggregate | null>(null);
  const [progress, setProgress] = useState<TutorProgressDataPoint[]>([]);
  const [vocabulary, setVocabulary] = useState<TutorVocabularyStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<TabValue>('all');

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const mode = activeTab === 'all' ? undefined : activeTab;
      const [sessionsData, aggregateData, progressData, vocabData] = await Promise.all([
        tutorMetrics.listSessions({ mode, limit: 100 }),
        tutorMetrics.getAggregateMetrics(),
        tutorMetrics.getProgress('es', 15),
        tutorMetrics.getVocabularyStats('es', 10).catch(() => null),
      ]);
      setSessions(sessionsData);
      setAggregate(aggregateData);
      setProgress(progressData.sessions);
      setVocabulary(vocabData);
    } catch (err) {
      console.error('Failed to fetch tutor metrics:', err);
    } finally {
      setLoading(false);
    }
  }, [activeTab]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Tutor Metrics</h1>
      </div>

      {/* Tabs */}
      <div className="flex gap-2">
        {TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setActiveTab(tab.value)}
            className={`px-4 py-2 rounded-lg transition-colors ${
              activeTab === tab.value
                ? 'bg-matcha-500 text-white'
                : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Aggregate Stats */}
      {aggregate && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {activeTab !== 'language_test' && (
            <>
              <Card>
                <CardContent className="p-4">
                  <div className="text-sm text-zinc-400">Interview Prep Sessions</div>
                  <div className="text-2xl font-bold text-white mt-1">
                    {aggregate.interview_prep.total_sessions}
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <div className="text-sm text-zinc-400">Avg Response Quality</div>
                  <div className="text-2xl font-bold mt-1">
                    <ScoreDisplay score={aggregate.interview_prep.avg_response_quality} />
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <div className="text-sm text-zinc-400">Avg Communication</div>
                  <div className="text-2xl font-bold mt-1">
                    <ScoreDisplay score={aggregate.interview_prep.avg_communication_score} />
                  </div>
                </CardContent>
              </Card>
            </>
          )}
          {activeTab !== 'interview_prep' && (
            <>
              <Card>
                <CardContent className="p-4">
                  <div className="text-sm text-zinc-400">Language Test Sessions</div>
                  <div className="text-2xl font-bold text-white mt-1">
                    {aggregate.language_test.total_sessions}
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <div className="text-sm text-zinc-400">Avg Fluency Score</div>
                  <div className="text-2xl font-bold mt-1">
                    <ScoreDisplay score={aggregate.language_test.avg_fluency_score} />
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <div className="text-sm text-zinc-400">Avg Grammar Score</div>
                  <div className="text-2xl font-bold mt-1">
                    <ScoreDisplay score={aggregate.language_test.avg_grammar_score} />
                  </div>
                </CardContent>
              </Card>
            </>
          )}
        </div>
      )}

      {/* Common Issues */}
      {activeTab === 'interview_prep' && aggregate?.interview_prep.common_improvement_areas.length ? (
        <Card>
          <CardContent className="p-4">
            <h3 className="text-sm font-medium text-zinc-400 mb-3">Common Improvement Areas</h3>
            <div className="flex flex-wrap gap-2">
              {aggregate.interview_prep.common_improvement_areas.map((item, i) => (
                <span key={i} className="px-3 py-1 bg-zinc-800 rounded-full text-sm text-zinc-300">
                  {item.area} <span className="text-zinc-500">({item.count})</span>
                </span>
              ))}
            </div>
          </CardContent>
        </Card>
      ) : null}

      {activeTab === 'language_test' && aggregate?.language_test.common_grammar_errors.length ? (
        <Card>
          <CardContent className="p-4">
            <h3 className="text-sm font-medium text-zinc-400 mb-3">Common Grammar Errors</h3>
            <div className="flex flex-wrap gap-2">
              {aggregate.language_test.common_grammar_errors.map((item, i) => (
                <span key={i} className="px-3 py-1 bg-zinc-800 rounded-full text-sm text-zinc-300">
                  {item.type} <span className="text-zinc-500">({item.count})</span>
                </span>
              ))}
            </div>
          </CardContent>
        </Card>
      ) : null}

      {/* Progress Over Time */}
      {(activeTab === 'all' || activeTab === 'language_test') && progress.length > 1 && (
        <Card>
          <CardContent className="p-4">
            <h3 className="text-sm font-medium text-zinc-400 mb-4">Spanish Progress Over Time</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <ProgressChart data={progress} title="Fluency" color="bg-matcha-500" />
              <ProgressChart data={progress} title="Grammar" color="bg-blue-500" />
              <ProgressChart data={progress} title="Vocabulary" color="bg-purple-500" />
            </div>
            <div className="mt-6 pt-4 border-t border-zinc-800">
              <ProficiencyTimeline data={progress} />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Vocabulary Tracking */}
      {(activeTab === 'all' || activeTab === 'language_test') && vocabulary && (
        <VocabularySection vocab={vocabulary} />
      )}

      {/* Sessions Table */}
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-8 text-center text-zinc-400">Loading sessions...</div>
          ) : sessions.length === 0 ? (
            <div className="p-8 text-center text-zinc-400">No tutor sessions yet</div>
          ) : (
            <table className="w-full">
              <thead>
                <tr className="border-b border-zinc-800">
                  <th className="text-left p-4 text-sm font-medium text-zinc-400">Date</th>
                  <th className="text-left p-4 text-sm font-medium text-zinc-400">Type</th>
                  <th className="text-left p-4 text-sm font-medium text-zinc-400">Language</th>
                  <th className="text-left p-4 text-sm font-medium text-zinc-400">Score</th>
                  <th className="text-left p-4 text-sm font-medium text-zinc-400">Status</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((session) => (
                  <tr
                    key={session.id}
                    onClick={() => navigate(`/app/tutor-metrics/${session.id}`)}
                    className="border-b border-zinc-800 hover:bg-zinc-800/50 cursor-pointer transition-colors"
                  >
                    <td className="p-4 text-sm text-zinc-300">
                      {formatDate(session.created_at)}
                    </td>
                    <td className="p-4 text-sm text-zinc-300">
                      {session.interview_type === 'tutor_interview' ? 'Interview Prep' : 'Language Test'}
                    </td>
                    <td className="p-4 text-sm text-zinc-300">
                      {session.language === 'en' ? 'English' : session.language === 'es' ? 'Spanish' : '-'}
                    </td>
                    <td className="p-4 text-sm">
                      <ScoreDisplay score={session.overall_score} />
                    </td>
                    <td className="p-4">
                      <span className={`px-2 py-1 rounded text-xs ${STATUS_COLORS[session.status] || 'bg-zinc-700 text-zinc-300'}`}>
                        {session.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default TutorMetrics;
