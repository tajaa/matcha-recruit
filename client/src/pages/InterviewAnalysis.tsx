import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, Card, CardContent } from '../components';
import { interviews } from '../api/client';
import type { Interview } from '../types';

export function InterviewAnalysis() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [interview, setInterview] = useState<Interview | null>(null);
  const [loading, setLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (id) {
      loadInterview();
    }
  }, [id]);

  const loadInterview = async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const data = await interviews.get(id);
      setInterview(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load interview');
    } finally {
      setLoading(false);
    }
  };

  const handleRegenerate = async () => {
    if (!id) return;
    setRegenerating(true);
    try {
      const analysis = await interviews.generateAnalysis(id);
      setInterview(prev => prev ? { ...prev, conversation_analysis: analysis } : null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to regenerate analysis');
    } finally {
      setRegenerating(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin w-8 h-8 border-2 border-matcha-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  if (error || !interview) {
    return (
      <div className="space-y-4">
        <Button variant="secondary" onClick={() => navigate('/app/test-bot')}>
          Back to Test Bot
        </Button>
        <Card>
          <CardContent className="p-6 text-center text-red-400">
            {error || 'Interview not found'}
          </CardContent>
        </Card>
      </div>
    );
  }

  const analysis = interview.conversation_analysis;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="secondary" onClick={() => navigate('/app/test-bot')}>
            <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            Back
          </Button>
          <div>
            <h1 className="text-2xl font-bold text-white">Interview Analysis</h1>
            <div className="flex items-center gap-2 mt-1">
              <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                interview.interview_type === 'culture'
                  ? 'bg-matcha-500/15 text-matcha-400'
                  : 'bg-violet-500/15 text-violet-400'
              }`}>
                {interview.interview_type === 'culture' ? 'Culture Interview' : 'Candidate Interview'}
              </span>
              <span className="text-zinc-500 text-sm">
                {new Date(interview.created_at).toLocaleDateString()}
              </span>
            </div>
          </div>
        </div>
        <Button
          onClick={handleRegenerate}
          disabled={regenerating || !interview.transcript}
          variant="secondary"
        >
          {regenerating ? (
            <>
              <svg className="w-4 h-4 animate-spin mr-2" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              Regenerating...
            </>
          ) : (
            <>
              <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Regenerate
            </>
          )}
        </Button>
      </div>

      {!analysis ? (
        <Card>
          <CardContent className="p-8 text-center">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-zinc-800 flex items-center justify-center">
              <svg className="w-8 h-8 text-zinc-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
            <h3 className="text-lg font-medium text-zinc-300 mb-2">No Analysis Available</h3>
            <p className="text-zinc-500 mb-4">
              {interview.transcript
                ? 'Click "Regenerate" to generate an analysis for this interview.'
                : 'This interview has no transcript to analyze.'}
            </p>
            {interview.transcript && (
              <Button onClick={handleRegenerate} disabled={regenerating}>
                Generate Analysis
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Summary Card */}
          <Card>
            <CardContent className="p-6">
              <h2 className="text-lg font-semibold text-zinc-100 mb-3">Summary</h2>
              <p className="text-zinc-300">{analysis.interview_summary}</p>
              <div className="flex items-center gap-6 mt-4 pt-4 border-t border-zinc-800">
                <ScoreDisplay
                  label="Coverage"
                  score={analysis.coverage_completeness.overall_score}
                />
                <ScoreDisplay
                  label="Response Depth"
                  score={analysis.response_depth.overall_score}
                />
                <div className="text-sm text-zinc-500">
                  Analyzed: {new Date(analysis.analyzed_at).toLocaleString()}
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Coverage Completeness */}
          <Card>
            <CardContent className="p-6">
              <h2 className="text-lg font-semibold text-zinc-100 mb-4">Coverage Completeness</h2>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                {Object.entries(analysis.coverage_completeness.coverage_details).map(([key, detail]) => (
                  <div
                    key={key}
                    className={`p-4 rounded-lg border ${
                      detail.covered && detail.depth === 'deep'
                        ? 'bg-matcha-500/10 border-matcha-500/30'
                        : detail.covered && detail.depth === 'shallow'
                        ? 'bg-yellow-500/10 border-yellow-500/30'
                        : 'bg-zinc-800/50 border-zinc-700'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium text-zinc-300 capitalize">
                        {key.replace(/_/g, ' ')}
                      </span>
                      {detail.covered ? (
                        <span className={`text-xs px-2 py-0.5 rounded ${
                          detail.depth === 'deep'
                            ? 'bg-matcha-500/20 text-matcha-400'
                            : 'bg-yellow-500/20 text-yellow-400'
                        }`}>
                          {detail.depth}
                        </span>
                      ) : (
                        <span className="text-xs px-2 py-0.5 rounded bg-zinc-700 text-zinc-400">
                          missed
                        </span>
                      )}
                    </div>
                    {detail.evidence && (
                      <p className="text-xs text-zinc-500 line-clamp-2">{detail.evidence}</p>
                    )}
                  </div>
                ))}
              </div>
              {analysis.coverage_completeness.dimensions_missed.length > 0 && (
                <div className="mt-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
                  <span className="text-sm font-medium text-red-400">Missed Dimensions: </span>
                  <span className="text-sm text-red-300">
                    {analysis.coverage_completeness.dimensions_missed.join(', ')}
                  </span>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Response Depth */}
          <Card>
            <CardContent className="p-6">
              <h2 className="text-lg font-semibold text-zinc-100 mb-4">Response Quality</h2>
              <div className="flex items-center gap-6 mb-4">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-matcha-500" />
                  <span className="text-sm text-zinc-400">
                    Specific: {analysis.response_depth.specific_examples_count}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-yellow-500" />
                  <span className="text-sm text-zinc-400">
                    Vague: {analysis.response_depth.vague_responses_count}
                  </span>
                </div>
              </div>
              <div className="space-y-3">
                {analysis.response_depth.response_analysis.map((item, idx) => (
                  <div
                    key={idx}
                    className="p-3 bg-zinc-800/50 rounded-lg border border-zinc-700"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <p className="text-sm text-zinc-300 flex-1">{item.question_summary}</p>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <span className={`text-xs px-2 py-0.5 rounded ${
                          item.response_quality === 'specific'
                            ? 'bg-matcha-500/20 text-matcha-400'
                            : item.response_quality === 'somewhat_specific' || item.response_quality === 'shallow'
                            ? 'bg-yellow-500/20 text-yellow-400'
                            : 'bg-zinc-700 text-zinc-400'
                        }`}>
                          {item.response_quality.replace('_', ' ')}
                        </span>
                        <span className={`text-xs px-2 py-0.5 rounded ${
                          item.actionability === 'high'
                            ? 'bg-blue-500/20 text-blue-400'
                            : item.actionability === 'medium'
                            ? 'bg-zinc-600 text-zinc-300'
                            : 'bg-zinc-700 text-zinc-500'
                        }`}>
                          {item.actionability} value
                        </span>
                      </div>
                    </div>
                    {item.notes && (
                      <p className="text-xs text-zinc-500 mt-2">{item.notes}</p>
                    )}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Missed Opportunities */}
          {analysis.missed_opportunities.length > 0 && (
            <Card>
              <CardContent className="p-6">
                <h2 className="text-lg font-semibold text-zinc-100 mb-4">Missed Opportunities</h2>
                <div className="space-y-3">
                  {analysis.missed_opportunities.map((opp, idx) => (
                    <div
                      key={idx}
                      className="p-4 bg-yellow-500/5 border border-yellow-500/20 rounded-lg"
                    >
                      <h4 className="text-sm font-medium text-yellow-400 mb-1">{opp.topic}</h4>
                      <p className="text-sm text-zinc-300 mb-2">
                        <span className="text-zinc-500">Suggested follow-up: </span>
                        "{opp.suggested_followup}"
                      </p>
                      <p className="text-xs text-zinc-500">{opp.reason}</p>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Prompt Improvement Suggestions */}
          {analysis.prompt_improvement_suggestions.length > 0 && (
            <Card>
              <CardContent className="p-6">
                <h2 className="text-lg font-semibold text-zinc-100 mb-4">Prompt Improvement Suggestions</h2>
                <div className="space-y-4">
                  {analysis.prompt_improvement_suggestions.map((suggestion, idx) => (
                    <div
                      key={idx}
                      className="p-4 bg-zinc-800/50 border border-zinc-700 rounded-lg"
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-sm font-medium text-zinc-300 capitalize">
                          {suggestion.category.replace(/_/g, ' ')}
                        </span>
                        <span className={`text-xs px-2 py-0.5 rounded ${
                          suggestion.priority === 'high'
                            ? 'bg-red-500/20 text-red-400'
                            : suggestion.priority === 'medium'
                            ? 'bg-yellow-500/20 text-yellow-400'
                            : 'bg-zinc-700 text-zinc-400'
                        }`}>
                          {suggestion.priority} priority
                        </span>
                      </div>
                      <div className="space-y-2 text-sm">
                        <p className="text-zinc-500">
                          <span className="font-medium">Current: </span>
                          {suggestion.current_behavior}
                        </p>
                        <p className="text-matcha-400">
                          <span className="font-medium text-zinc-400">Suggestion: </span>
                          {suggestion.suggested_improvement}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

function ScoreDisplay({ label, score }: { label: string; score: number }) {
  const getColor = (s: number) => {
    if (s >= 80) return 'text-matcha-400';
    if (s >= 60) return 'text-yellow-400';
    return 'text-red-400';
  };

  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-zinc-500">{label}:</span>
      <span className={`text-lg font-bold ${getColor(score)}`}>{score}</span>
      <span className="text-sm text-zinc-600">/100</span>
    </div>
  );
}
