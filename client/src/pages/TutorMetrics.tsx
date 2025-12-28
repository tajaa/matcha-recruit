import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent } from '../components';
import { tutorMetrics } from '../api/client';
import type { TutorSessionSummary, TutorMetricsAggregate } from '../types';

type TabValue = 'all' | 'interview_prep' | 'language_test';

const TABS: { label: string; value: TabValue }[] = [
  { label: 'All Sessions', value: 'all' },
  { label: 'Interview Prep', value: 'interview_prep' },
  { label: 'Language Test', value: 'language_test' },
];

const STATUS_COLORS: Record<string, string> = {
  completed: 'bg-matcha-500/20 text-matcha-400',
  analyzing: 'bg-yellow-500/20 text-yellow-400',
  in_progress: 'bg-blue-500/20 text-blue-400',
  pending: 'bg-zinc-700 text-zinc-300',
};

function ScoreDisplay({ score, label }: { score: number | null; label?: string }) {
  if (score === null) return <span className="text-zinc-500">-</span>;

  const getColor = (s: number) => {
    if (s >= 80) return 'text-matcha-400';
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

export function TutorMetrics() {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<TutorSessionSummary[]>([]);
  const [aggregate, setAggregate] = useState<TutorMetricsAggregate | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<TabValue>('all');

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const mode = activeTab === 'all' ? undefined : activeTab;
      const [sessionsData, aggregateData] = await Promise.all([
        tutorMetrics.listSessions({ mode, limit: 100 }),
        tutorMetrics.getAggregateMetrics(),
      ]);
      setSessions(sessionsData);
      setAggregate(aggregateData);
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
