import { useState, useEffect } from 'react';
import { ClipboardCheck, Send, Clock, CheckCircle } from 'lucide-react';
import { enpsApi } from '../../api/xp';
import { NPSRatingInput } from '../../components/xp/NPSRatingInput';
import type { ENPSSurvey } from '../../types/xp';

export default function PortalENPS() {
  const [activeSurveys, setActiveSurveys] = useState<ENPSSurvey[]>([]);
  const [loadingSurveys, setLoadingSurveys] = useState(true);
  const [selectedSurvey, setSelectedSurvey] = useState<ENPSSurvey | null>(null);

  const [score, setScore] = useState(-1);
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [completedSurveyIds, setCompletedSurveyIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    fetchActiveSurveys();
  }, []);

  const fetchActiveSurveys = async () => {
    try {
      setLoadingSurveys(true);
      const surveys = await enpsApi.getActiveSurveys();
      setActiveSurveys(surveys);
      if (surveys.length > 0 && !selectedSurvey) {
        setSelectedSurvey(surveys[0]);
      }
    } catch (err) {
      console.error('Failed to fetch active surveys:', err);
      setActiveSurveys([]);
    } finally {
      setLoadingSurveys(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (score < 0) {
      setError('Please select a score');
      return;
    }

    if (!selectedSurvey) {
      setError('No survey selected');
      return;
    }

    try {
      setSubmitting(true);
      setError(null);
      setSuccess(false);

      await enpsApi.submitResponse(selectedSurvey.id, {
        score,
        reason: reason.trim() || undefined,
      });

      setSuccess(true);
      setCompletedSurveyIds(prev => new Set(prev).add(selectedSurvey.id));
      setScore(-1);
      setReason('');

      setTimeout(() => setSuccess(false), 5000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit response');
    } finally {
      setSubmitting(false);
    }
  };

  const pendingSurveys = activeSurveys.filter(s => !completedSurveyIds.has(s.id));
  const currentSurvey = selectedSurvey && !completedSurveyIds.has(selectedSurvey.id)
    ? selectedSurvey
    : pendingSurveys[0] || null;

  return (
    <div className="min-h-screen bg-gradient-to-br from-zinc-950 via-zinc-900 to-zinc-950 p-6">
      <div className="max-w-2xl mx-auto space-y-8">
        {/* Header */}
        <div className="border-b border-white/10 pb-8">
          <div className="flex items-center gap-3 mb-2">
            <ClipboardCheck className="w-8 h-8 text-emerald-400" />
            <div className="px-2 py-1 border border-emerald-500/20 bg-emerald-900/10 text-emerald-400 text-[9px] uppercase tracking-widest font-mono rounded">
              Employee Survey
            </div>
          </div>
          <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">
            eNPS Survey
          </h1>
          <p className="text-sm text-zinc-400 mt-2">
            Your feedback helps us build a better workplace. All responses are anonymous.
          </p>
        </div>

        {success && (
          <div className="bg-emerald-500/10 border border-emerald-500/20 rounded p-4 flex items-center gap-3">
            <div className="text-emerald-400">
              <CheckCircle className="w-5 h-5" />
            </div>
            <div>
              <p className="text-sm text-emerald-400 font-medium">Thank you for your feedback!</p>
              <p className="text-xs text-emerald-400/70 mt-1">Your response has been recorded.</p>
            </div>
          </div>
        )}

        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded p-4">
            <p className="text-sm text-red-400">{error}</p>
          </div>
        )}

        {loadingSurveys ? (
          <div className="flex items-center justify-center py-12">
            <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">
              Loading surveys...
            </div>
          </div>
        ) : currentSurvey ? (
          <div className="bg-zinc-900/30 border border-white/10 p-8">
            {/* Survey Info */}
            <div className="mb-8">
              <h2 className="text-xl font-bold text-white mb-2">{currentSurvey.title}</h2>
              {currentSurvey.description && (
                <p className="text-sm text-zinc-400">{currentSurvey.description}</p>
              )}
              <div className="flex items-center gap-4 mt-4 text-xs text-zinc-500">
                <div className="flex items-center gap-2">
                  <Clock className="w-4 h-4" />
                  <span>
                    Ends {new Date(currentSurvey.end_date).toLocaleDateString()}
                  </span>
                </div>
                {currentSurvey.is_anonymous && (
                  <span className="text-emerald-400">Anonymous</span>
                )}
              </div>
            </div>

            <form onSubmit={handleSubmit} className="space-y-8">
              {/* NPS Question */}
              <div>
                <label className="text-sm font-medium text-white mb-6 block">
                  How likely are you to recommend this company as a place to work?
                </label>
                <NPSRatingInput
                  value={score}
                  onChange={setScore}
                  disabled={submitting}
                />
              </div>

              {/* Reason */}
              <div>
                <label className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2 block">
                  {currentSurvey.custom_question || "What's the main reason for your score? (optional)"}
                </label>
                <textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  disabled={submitting}
                  placeholder="Share your thoughts..."
                  rows={4}
                  className="w-full bg-zinc-900 border border-white/10 text-white px-4 py-3 text-sm rounded focus:border-white/30 focus:outline-none resize-none disabled:opacity-50"
                />
                <p className="text-xs text-zinc-500 mt-2">
                  Your feedback is {currentSurvey.is_anonymous ? 'anonymous and ' : ''}used to improve our workplace.
                </p>
              </div>

              <button
                type="submit"
                disabled={submitting || score < 0}
                className="w-full bg-white text-black py-3 px-6 text-sm font-medium uppercase tracking-wider hover:bg-zinc-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {submitting ? (
                  <span className="animate-pulse">Submitting...</span>
                ) : (
                  <>
                    <Send className="w-4 h-4" />
                    Submit Response
                  </>
                )}
              </button>
            </form>
          </div>
        ) : completedSurveyIds.size > 0 ? (
          <div className="bg-emerald-900/10 border border-emerald-500/20 p-12 text-center">
            <CheckCircle className="w-16 h-16 text-emerald-400 mx-auto mb-4" />
            <h3 className="text-xl font-bold text-white mb-2">All Done!</h3>
            <p className="text-sm text-zinc-400">
              You've completed all available surveys. Thank you for your feedback!
            </p>
          </div>
        ) : (
          <div className="bg-zinc-900/50 border border-white/10 p-12 text-center">
            <ClipboardCheck className="w-16 h-16 text-zinc-700 mx-auto mb-4" />
            <h3 className="text-xl font-bold text-white mb-2">No Active Surveys</h3>
            <p className="text-sm text-zinc-500">
              There are no eNPS surveys available at this time.
            </p>
            <p className="text-xs text-zinc-600 mt-2">
              Check back later for new surveys.
            </p>
          </div>
        )}

        {/* Multiple Surveys Notice */}
        {pendingSurveys.length > 1 && (
          <div className="bg-zinc-900/30 border border-white/10 p-4">
            <div className="text-xs text-zinc-500 uppercase tracking-wider mb-3">
              {pendingSurveys.length} Surveys Available
            </div>
            <div className="flex flex-wrap gap-2">
              {pendingSurveys.map(survey => (
                <button
                  key={survey.id}
                  onClick={() => setSelectedSurvey(survey)}
                  className={`px-3 py-2 text-xs rounded transition-colors ${
                    selectedSurvey?.id === survey.id
                      ? 'bg-white text-black font-bold'
                      : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'
                  }`}
                >
                  {survey.title}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
