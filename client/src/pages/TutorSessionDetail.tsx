import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, Card, CardContent } from '../components';
import { tutorMetrics } from '../api/client';
import type { TutorSessionDetail as TutorSessionDetailType, TutorInterviewAnalysis, TutorLanguageAnalysis, TutorSessionComparison, SpanishSpecificAnalysis } from '../types';

function ScoreDisplay({ label, score }: { label: string; score: number }) {
  const getColor = (s: number) => {
    if (s >= 80) return 'text-white';
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

function PriorityBadge({ priority }: { priority: 'high' | 'medium' | 'low' }) {
  const colors = {
    high: 'bg-red-500/20 text-red-400',
    medium: 'bg-yellow-500/20 text-yellow-400',
    low: 'bg-zinc-700 text-zinc-400',
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs ${colors[priority]}`}>
      {priority}
    </span>
  );
}

function ChangeIndicator({ change }: { change: number | null }) {
  if (change === null) return <span className="text-zinc-500">-</span>;
  const isPositive = change >= 0;
  return (
    <span className={`text-sm font-medium ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
      {isPositive ? '+' : ''}{change.toFixed(1)}
    </span>
  );
}

function SessionComparisonCard({ comparison }: { comparison: TutorSessionComparison }) {
  if (comparison.previous_session_count === 0) {
    return (
      <Card>
        <CardContent className="p-6 text-center">
          <p className="text-zinc-500">Complete more sessions to see how you compare!</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-6">
        <h3 className="text-sm font-medium text-zinc-400 mb-4">
          Compared to Your Last {comparison.previous_session_count} Session{comparison.previous_session_count > 1 ? 's' : ''}
        </h3>
        <div className="grid grid-cols-3 gap-4">
          <div className="text-center">
            <div className="text-xs text-zinc-500 mb-1">Fluency</div>
            <div className="text-2xl font-bold text-white">{comparison.current_fluency ?? '-'}</div>
            <div className="mt-1">
              <ChangeIndicator change={comparison.fluency_change} />
              <span className="text-xs text-zinc-500 ml-1">vs avg {comparison.avg_previous_fluency?.toFixed(0)}</span>
            </div>
          </div>
          <div className="text-center">
            <div className="text-xs text-zinc-500 mb-1">Grammar</div>
            <div className="text-2xl font-bold text-white">{comparison.current_grammar ?? '-'}</div>
            <div className="mt-1">
              <ChangeIndicator change={comparison.grammar_change} />
              <span className="text-xs text-zinc-500 ml-1">vs avg {comparison.avg_previous_grammar?.toFixed(0)}</span>
            </div>
          </div>
          <div className="text-center">
            <div className="text-xs text-zinc-500 mb-1">Vocabulary</div>
            <div className="text-2xl font-bold text-white">{comparison.current_vocabulary ?? '-'}</div>
            <div className="mt-1">
              <ChangeIndicator change={comparison.vocabulary_change} />
              <span className="text-xs text-zinc-500 ml-1">vs avg {comparison.avg_previous_vocabulary?.toFixed(0)}</span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function SpanishSpecificSection({ analysis }: { analysis: SpanishSpecificAnalysis }) {
  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold text-white">Spanish-Specific Feedback</h3>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Conjugation */}
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-medium text-zinc-400">Verb Conjugation</h4>
              <span className={`text-lg font-bold ${analysis.conjugation.score >= 80 ? 'text-white' : analysis.conjugation.score >= 60 ? 'text-yellow-400' : 'text-red-400'}`}>
                {analysis.conjugation.score}
              </span>
            </div>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-zinc-500">Regular verbs:</span>
                <span className="text-zinc-300">{analysis.conjugation.regular_verb_accuracy}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-zinc-500">Irregular verbs:</span>
                <span className="text-zinc-300">{analysis.conjugation.irregular_verb_accuracy}%</span>
              </div>
              {analysis.conjugation.subjunctive_attempts > 0 && (
                <div className="flex justify-between">
                  <span className="text-zinc-500">Subjunctive:</span>
                  <span className="text-zinc-300">{analysis.conjugation.subjunctive_accuracy ?? 0}%</span>
                </div>
              )}
            </div>
            {analysis.conjugation.notable_errors.length > 0 && (
              <div className="mt-3 pt-3 border-t border-zinc-800">
                <div className="text-xs text-zinc-500 mb-2">Errors:</div>
                {analysis.conjugation.notable_errors.slice(0, 3).map((err, i) => (
                  <div key={i} className="text-xs mb-1">
                    <span className="text-red-400 line-through">{err.user_said}</span>
                    <span className="text-zinc-500 mx-1">&rarr;</span>
                    <span className="text-white">{err.correct}</span>
                    <span className="text-zinc-600 ml-1">({err.verb}, {err.tense})</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Gender Agreement */}
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-medium text-zinc-400">Gender & Agreement</h4>
              <span className={`text-lg font-bold ${analysis.gender_agreement.score >= 80 ? 'text-white' : analysis.gender_agreement.score >= 60 ? 'text-yellow-400' : 'text-red-400'}`}>
                {analysis.gender_agreement.score}
              </span>
            </div>
            <p className="text-sm text-zinc-400 mb-2">{analysis.gender_agreement.notes}</p>
            {analysis.gender_agreement.errors.length > 0 && (
              <div className="mt-2">
                {analysis.gender_agreement.errors.slice(0, 3).map((err, i) => (
                  <div key={i} className="text-xs mb-2 p-2 bg-zinc-800/50 rounded">
                    <div>
                      <span className="text-red-400 line-through">{err.phrase}</span>
                      <span className="text-zinc-500 mx-1">&rarr;</span>
                      <span className="text-white">{err.correction}</span>
                    </div>
                    <div className="text-zinc-500 mt-1">{err.rule}</div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Ser vs Estar */}
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-medium text-zinc-400">Ser vs Estar</h4>
              <span className={`text-lg font-bold ${analysis.ser_estar.score >= 80 ? 'text-white' : analysis.ser_estar.score >= 60 ? 'text-yellow-400' : 'text-red-400'}`}>
                {analysis.ser_estar.score}
              </span>
            </div>
            <p className="text-sm text-zinc-400 mb-2">{analysis.ser_estar.notes}</p>
            {analysis.ser_estar.errors.length > 0 && (
              <div className="mt-2">
                {analysis.ser_estar.errors.slice(0, 3).map((err, i) => (
                  <div key={i} className="text-xs mb-2 p-2 bg-zinc-800/50 rounded">
                    <div>
                      <span className="text-red-400 line-through">{err.user_said}</span>
                      <span className="text-zinc-500 mx-1">&rarr;</span>
                      <span className="text-white">{err.correction}</span>
                    </div>
                    <div className="text-zinc-500 mt-1">{err.explanation}</div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Por vs Para */}
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-medium text-zinc-400">Por vs Para</h4>
              <span className={`text-lg font-bold ${analysis.por_para.score >= 80 ? 'text-white' : analysis.por_para.score >= 60 ? 'text-yellow-400' : 'text-red-400'}`}>
                {analysis.por_para.score}
              </span>
            </div>
            <p className="text-sm text-zinc-400 mb-2">{analysis.por_para.notes}</p>
            {analysis.por_para.errors.length > 0 && (
              <div className="mt-2">
                {analysis.por_para.errors.slice(0, 3).map((err, i) => (
                  <div key={i} className="text-xs mb-2 p-2 bg-zinc-800/50 rounded">
                    <div>
                      <span className="text-red-400 line-through">{err.user_said}</span>
                      <span className="text-zinc-500 mx-1">&rarr;</span>
                      <span className="text-white">{err.correction}</span>
                    </div>
                    <div className="text-zinc-500 mt-1">{err.explanation}</div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function InterviewPrepAnalysis({ analysis }: { analysis: TutorInterviewAnalysis }) {
  return (
    <div className="space-y-6">
      {/* Summary */}
      <Card>
        <CardContent className="p-6">
          <h2 className="text-lg font-semibold text-white mb-4">Session Summary</h2>
          <p className="text-zinc-300">{analysis.session_summary}</p>
        </CardContent>
      </Card>

      {/* Scores Overview */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Response Quality */}
        <Card>
          <CardContent className="p-6">
            <h3 className="text-sm font-medium text-zinc-400 mb-4">Response Quality</h3>
            <div className="space-y-3">
              <ScoreDisplay label="Overall" score={analysis.response_quality.overall_score} />
              <ScoreDisplay label="Specificity" score={analysis.response_quality.specificity_score} />
              <ScoreDisplay label="Example Usage" score={analysis.response_quality.example_usage_score} />
              <ScoreDisplay label="Depth" score={analysis.response_quality.depth_score} />
            </div>
          </CardContent>
        </Card>

        {/* Communication Skills */}
        <Card>
          <CardContent className="p-6">
            <h3 className="text-sm font-medium text-zinc-400 mb-4">Communication Skills</h3>
            <div className="space-y-3">
              <ScoreDisplay label="Overall" score={analysis.communication_skills.overall_score} />
              <ScoreDisplay label="Clarity" score={analysis.communication_skills.clarity_score} />
              <ScoreDisplay label="Confidence" score={analysis.communication_skills.confidence_score} />
              <ScoreDisplay label="Professionalism" score={analysis.communication_skills.professionalism_score} />
              <ScoreDisplay label="Engagement" score={analysis.communication_skills.engagement_score} />
            </div>
            {analysis.communication_skills.notes && (
              <p className="mt-4 text-sm text-zinc-400 border-l-2 border-zinc-700 pl-3">
                {analysis.communication_skills.notes}
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Content Coverage */}
      <Card>
        <CardContent className="p-6">
          <h3 className="text-sm font-medium text-zinc-400 mb-4">Content Coverage</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h4 className="text-xs uppercase tracking-wider text-zinc-500 mb-2">Topics Covered</h4>
              <div className="flex flex-wrap gap-2">
                {analysis.content_coverage.topics_covered.map((topic, i) => (
                  <span key={i} className="px-2 py-1 bg-matcha-500/20 text-white rounded text-sm">
                    {topic}
                  </span>
                ))}
                {analysis.content_coverage.topics_covered.length === 0 && (
                  <span className="text-zinc-500 text-sm">No specific topics identified</span>
                )}
              </div>
            </div>
            <div>
              <h4 className="text-xs uppercase tracking-wider text-zinc-500 mb-2">Follow-up Depth</h4>
              <span className={`px-3 py-1 rounded text-sm ${
                analysis.content_coverage.follow_up_depth === 'excellent' ? 'bg-matcha-500/20 text-white' :
                analysis.content_coverage.follow_up_depth === 'good' ? 'bg-yellow-500/20 text-yellow-400' :
                'bg-red-500/20 text-red-400'
              }`}>
                {analysis.content_coverage.follow_up_depth}
              </span>
            </div>
          </div>

          {analysis.content_coverage.missed_opportunities.length > 0 && (
            <div className="mt-6">
              <h4 className="text-xs uppercase tracking-wider text-zinc-500 mb-2">Missed Opportunities</h4>
              <div className="space-y-2">
                {analysis.content_coverage.missed_opportunities.map((opp, i) => (
                  <div key={i} className="p-3 bg-zinc-800/50 rounded">
                    <div className="font-medium text-zinc-300">{opp.topic}</div>
                    <div className="text-sm text-zinc-500 mt-1">{opp.suggestion}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Response Breakdown */}
      {analysis.response_quality.breakdown.length > 0 && (
        <Card>
          <CardContent className="p-6">
            <h3 className="text-sm font-medium text-zinc-400 mb-4">Response Breakdown</h3>
            <div className="space-y-4">
              {analysis.response_quality.breakdown.map((item, i) => (
                <div key={i} className="p-4 bg-zinc-800/50 rounded-lg">
                  <div className="flex items-start justify-between mb-2">
                    <div className="font-medium text-zinc-300">{item.question}</div>
                    <div className="flex items-center gap-2">
                      <span className={`px-2 py-0.5 rounded text-xs ${
                        item.quality === 'specific' ? 'bg-matcha-500/20 text-white' :
                        item.quality === 'somewhat_specific' ? 'bg-yellow-500/20 text-yellow-400' :
                        'bg-red-500/20 text-red-400'
                      }`}>
                        {item.quality.replace('_', ' ')}
                      </span>
                      {item.used_examples && (
                        <span className="px-2 py-0.5 bg-blue-500/20 text-blue-400 rounded text-xs">
                          used examples
                        </span>
                      )}
                    </div>
                  </div>
                  <p className="text-sm text-zinc-400">{item.feedback}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Improvement Suggestions */}
      {analysis.improvement_suggestions.length > 0 && (
        <Card>
          <CardContent className="p-6">
            <h3 className="text-sm font-medium text-zinc-400 mb-4">Improvement Suggestions</h3>
            <div className="space-y-3">
              {analysis.improvement_suggestions.map((suggestion, i) => (
                <div key={i} className="flex items-start gap-3 p-3 bg-zinc-800/50 rounded">
                  <PriorityBadge priority={suggestion.priority} />
                  <div>
                    <div className="font-medium text-zinc-300">{suggestion.area}</div>
                    <div className="text-sm text-zinc-500 mt-1">{suggestion.suggestion}</div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function LanguageTestAnalysis({ analysis, comparison }: { analysis: TutorLanguageAnalysis; comparison: TutorSessionComparison | null }) {
  return (
    <div className="space-y-6">
      {/* Session Comparison */}
      {comparison && <SessionComparisonCard comparison={comparison} />}

      {/* Summary & Proficiency */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="md:col-span-2">
          <CardContent className="p-6">
            <h2 className="text-lg font-semibold text-white mb-4">Session Summary</h2>
            <p className="text-zinc-300">{analysis.session_summary}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-6 text-center">
            <h3 className="text-sm font-medium text-zinc-400 mb-2">Proficiency Level</h3>
            <div className="text-4xl font-bold text-white mb-2">
              {analysis.overall_proficiency.level}
            </div>
            <p className="text-sm text-zinc-500">{analysis.overall_proficiency.level_description}</p>
          </CardContent>
        </Card>
      </div>

      {/* Scores Overview */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Fluency */}
        <Card>
          <CardContent className="p-6">
            <h3 className="text-sm font-medium text-zinc-400 mb-4">Fluency & Pace</h3>
            <div className="space-y-3">
              <ScoreDisplay label="Overall" score={analysis.fluency_pace.overall_score} />
              <div className="flex items-center gap-2 text-sm">
                <span className="text-zinc-500">Speed:</span>
                <span className="text-zinc-300">{analysis.fluency_pace.speaking_speed.replace('_', ' ')}</span>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <span className="text-zinc-500">Pauses:</span>
                <span className="text-zinc-300">{analysis.fluency_pace.pause_frequency}</span>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <span className="text-zinc-500">Filler words:</span>
                <span className="text-zinc-300">{analysis.fluency_pace.filler_word_count}</span>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <span className="text-zinc-500">Flow:</span>
                <span className={`${
                  analysis.fluency_pace.flow_rating === 'excellent' ? 'text-white' :
                  analysis.fluency_pace.flow_rating === 'good' ? 'text-yellow-400' :
                  'text-red-400'
                }`}>
                  {analysis.fluency_pace.flow_rating}
                </span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Vocabulary */}
        <Card>
          <CardContent className="p-6">
            <h3 className="text-sm font-medium text-zinc-400 mb-4">Vocabulary</h3>
            <div className="space-y-3">
              <ScoreDisplay label="Overall" score={analysis.vocabulary.overall_score} />
              <ScoreDisplay label="Variety" score={analysis.vocabulary.variety_score} />
              <ScoreDisplay label="Appropriateness" score={analysis.vocabulary.appropriateness_score} />
              <div className="flex items-center gap-2 text-sm">
                <span className="text-zinc-500">Level:</span>
                <span className="text-zinc-300">{analysis.vocabulary.complexity_level}</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Grammar */}
        <Card>
          <CardContent className="p-6">
            <h3 className="text-sm font-medium text-zinc-400 mb-4">Grammar</h3>
            <div className="space-y-3">
              <ScoreDisplay label="Overall" score={analysis.grammar.overall_score} />
              <ScoreDisplay label="Structure" score={analysis.grammar.sentence_structure_score} />
              <ScoreDisplay label="Tense Usage" score={analysis.grammar.tense_usage_score} />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Strengths & Areas to Improve */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardContent className="p-6">
            <h3 className="text-sm font-medium text-zinc-400 mb-4">Strengths</h3>
            <div className="space-y-2">
              {analysis.overall_proficiency.strengths.map((strength, i) => (
                <div key={i} className="flex items-center gap-2 text-zinc-300">
                  <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  {strength}
                </div>
              ))}
              {analysis.overall_proficiency.strengths.length === 0 && (
                <span className="text-zinc-500">No specific strengths identified</span>
              )}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-6">
            <h3 className="text-sm font-medium text-zinc-400 mb-4">Areas to Improve</h3>
            <div className="space-y-2">
              {analysis.overall_proficiency.areas_to_improve.map((area, i) => (
                <div key={i} className="flex items-center gap-2 text-zinc-300">
                  <svg className="w-4 h-4 text-yellow-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                  {area}
                </div>
              ))}
              {analysis.overall_proficiency.areas_to_improve.length === 0 && (
                <span className="text-zinc-500">No specific areas identified</span>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Grammar Errors */}
      {analysis.grammar.common_errors.length > 0 && (
        <Card>
          <CardContent className="p-6">
            <h3 className="text-sm font-medium text-zinc-400 mb-4">Grammar Errors</h3>
            <div className="space-y-3">
              {analysis.grammar.common_errors.map((error, i) => (
                <div key={i} className="p-3 bg-zinc-800/50 rounded">
                  <div className="flex items-start justify-between">
                    <div>
                      <span className="text-red-400 line-through">{error.error}</span>
                      <span className="mx-2 text-zinc-500">→</span>
                      <span className="text-white">{error.correction}</span>
                    </div>
                    <span className="px-2 py-0.5 bg-zinc-700 text-zinc-400 rounded text-xs">
                      {error.type}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Spanish-Specific Analysis */}
      {analysis.spanish_specific && (
        <SpanishSpecificSection analysis={analysis.spanish_specific} />
      )}

      {/* Practice Suggestions */}
      {analysis.practice_suggestions.length > 0 && (
        <Card>
          <CardContent className="p-6">
            <h3 className="text-sm font-medium text-zinc-400 mb-4">Practice Suggestions</h3>
            <div className="space-y-3">
              {analysis.practice_suggestions.map((suggestion, i) => (
                <div key={i} className="flex items-start gap-3 p-3 bg-zinc-800/50 rounded">
                  <PriorityBadge priority={suggestion.priority} />
                  <div>
                    <div className="font-medium text-zinc-300">{suggestion.skill}</div>
                    <div className="text-sm text-zinc-500 mt-1">{suggestion.exercise}</div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export function TutorSessionDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [session, setSession] = useState<TutorSessionDetailType | null>(null);
  const [comparison, setComparison] = useState<TutorSessionComparison | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (id) {
      loadSession();
    }
  }, [id]);

  const loadSession = async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const [sessionData, comparisonData] = await Promise.all([
        tutorMetrics.getSession(id),
        tutorMetrics.getSessionComparison(id).catch(() => null),
      ]);
      setSession(sessionData);
      setComparison(comparisonData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load session');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin w-8 h-8 border-2 border-white border-t-transparent rounded-full" />
      </div>
    );
  }

  if (error || !session) {
    return (
      <div className="space-y-4">
        <Button variant="secondary" onClick={() => navigate(-1)}>
          Back
        </Button>
        <Card>
          <CardContent className="p-6 text-center text-red-400">
            {error || 'Session not found'}
          </CardContent>
        </Card>
      </div>
    );
  }

  const isInterviewPrep = session.interview_type === 'tutor_interview';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="secondary" onClick={() => navigate('/app/admin/tutor-metrics')}>
          <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
          Back
        </Button>
        <div>
          <h1 className="text-2xl font-bold text-white">
            {isInterviewPrep ? 'Interview Prep Analysis' : 'Language Test Analysis'}
          </h1>
          <div className="flex items-center gap-2 mt-1">
            <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
              isInterviewPrep
                ? 'bg-violet-500/15 text-violet-400'
                : 'bg-blue-500/15 text-blue-400'
            }`}>
              {isInterviewPrep ? 'Interview Prep' : 'Language Test'}
            </span>
            {session.language && (
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-zinc-700 text-zinc-300">
                {session.language === 'en' ? 'English' : 'Spanish'}
              </span>
            )}
            <span className="text-zinc-500 text-sm">
              {new Date(session.created_at).toLocaleDateString()}
            </span>
            <span className={`px-2 py-0.5 rounded text-xs ${
              session.status === 'completed' ? 'bg-matcha-500/20 text-white' :
              session.status === 'analyzing' ? 'bg-yellow-500/20 text-yellow-400' :
              'bg-zinc-700 text-zinc-300'
            }`}>
              {session.status}
            </span>
          </div>
        </div>
      </div>

      {/* No Analysis State */}
      {!session.tutor_analysis ? (
        <Card>
          <CardContent className="p-8 text-center">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-zinc-800 flex items-center justify-center">
              <svg className="w-8 h-8 text-zinc-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
            <h3 className="text-lg font-medium text-zinc-300 mb-2">
              {session.status === 'analyzing' ? 'Analysis in Progress' : 'No Analysis Available'}
            </h3>
            <p className="text-zinc-500">
              {session.status === 'analyzing'
                ? 'The analysis is being generated. Please check back shortly.'
                : 'This session has not been analyzed yet.'}
            </p>
          </CardContent>
        </Card>
      ) : isInterviewPrep ? (
        <InterviewPrepAnalysis analysis={session.tutor_analysis as TutorInterviewAnalysis} />
      ) : (
        <LanguageTestAnalysis analysis={session.tutor_analysis as TutorLanguageAnalysis} comparison={comparison} />
      )}

      {/* Transcript */}
      {session.transcript && (
        <Card>
          <CardContent className="p-6">
            <h3 className="text-sm font-medium text-zinc-400 mb-4">Transcript</h3>
            <div className="max-h-96 overflow-y-auto">
              <pre className="text-sm text-zinc-300 whitespace-pre-wrap font-sans">
                {session.transcript}
              </pre>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default TutorSessionDetail;
