import { useState, useEffect } from 'react';
import { ClipboardCheck, Send, Clock, CheckCircle, AlertCircle } from 'lucide-react';
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

    if (!currentSurvey) {
      setError('No survey selected');
      return;
    }

    try {
      setSubmitting(true);
      setError(null);
      setSuccess(false);

      await enpsApi.submitResponse(currentSurvey.id, {
        score,
        reason: reason.trim() || undefined,
      });

      setSuccess(true);
      setCompletedSurveyIds(prev => new Set(prev).add(currentSurvey.id));
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
    <div className="space-y-8 max-w-4xl">
      {/* Header */}
      <div className="border-b border-white/10 pb-6">
        <div className="flex items-center gap-3 mb-2">
          <ClipboardCheck className="w-8 h-8 text-emerald-400" />
          <div className="px-2 py-1 border border-emerald-500/20 bg-emerald-900/10 text-emerald-400 text-[9px] uppercase tracking-widest font-mono rounded">
            Employee Survey
          </div>
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-white uppercase">eNPS Survey</h1>
        <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">Your feedback helps us build a better workplace. All responses are anonymous.</p>
      </div>

      {success && (
        <div className="bg-emerald-500/10 border border-emerald-500/20 p-4 flex items-center gap-3 animate-in fade-in duration-500">
          <CheckCircle className="w-5 h-5 text-emerald-400" />
          <div>
            <p className="text-sm text-emerald-400 font-bold uppercase tracking-tight">Thank you for your feedback!</p>
            <p className="text-[10px] text-emerald-400/70 mt-1 uppercase tracking-widest font-mono">Your response has been recorded.</p>
          </div>
        </div>
      )}

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 p-4 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-400" />
          <p className="text-sm text-red-400 font-mono uppercase">{error}</p>
        </div>
      )}

      {loadingSurveys ? (
        <div className="flex items-center justify-center py-24">
          <div className="flex flex-col items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-zinc-600 animate-pulse" />
            <span className="text-xs text-zinc-500 font-mono uppercase tracking-widest">Scanning Surveys...</span>
          </div>
        </div>
      ) : currentSurvey ? (
        <div className="bg-zinc-900/30 border border-dashed border-white/10 p-8 space-y-10">
          {/* Survey Info */}
          <div>
            <h2 className="text-xl font-bold text-white tracking-tight uppercase">{currentSurvey.title}</h2>
            {currentSurvey.description && (
              <p className="text-xs text-zinc-500 font-mono uppercase tracking-wide mt-2 leading-relaxed">{currentSurvey.description}</p>
            )}
            <div className="flex items-center gap-5 mt-6 text-[10px] font-mono uppercase tracking-widest border-t border-white/5 pt-4">
              <div className="flex items-center gap-2 text-zinc-600">
                <Clock className="w-3.5 h-3.5" />
                <span>Ends {new Date(currentSurvey.end_date).toLocaleDateString()}</span>
              </div>
              {currentSurvey.is_anonymous && (
                <span className="text-emerald-500 font-bold">Anonymous Response</span>
              )}
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-10">
            {/* NPS Question */}
            <div>
              <label className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-8 ml-1 block">
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
              <label className="text-[9px] font-bold uppercase tracking-widest text-zinc-600 mb-2 ml-1 block">
                {currentSurvey.custom_question || "What's the main reason for your score? (optional)"}
              </label>
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                disabled={submitting}
                placeholder="Share your thoughts..."
                rows={4}
                className="w-full bg-zinc-950 border border-zinc-800 text-white px-4 py-3 text-sm focus:border-white transition-colors outline-none resize-none disabled:opacity-50 font-mono leading-relaxed"
              />
            </div>

            <button
              type="submit"
              disabled={submitting || score < 0}
              className="w-full bg-white text-black py-4 px-8 text-[10px] font-bold uppercase tracking-widest border border-white hover:bg-zinc-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-3"
            >
              {submitting ? (
                <span className="animate-pulse">Processing...</span>
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
        <div className="bg-emerald-500/5 border border-dashed border-emerald-500/20 p-16 text-center">
          <CheckCircle className="w-16 h-16 text-emerald-400 mx-auto mb-6 opacity-50" />
          <h3 className="text-xl font-bold text-white uppercase tracking-tight mb-2">All Done!</h3>
          <p className="text-xs text-zinc-500 font-mono uppercase tracking-widest leading-relaxed max-w-sm mx-auto">
            You've completed all available surveys. Thank you for your feedback!
          </p>
        </div>
      ) : (
        <div className="bg-zinc-900/30 border border-dashed border-white/10 p-16 text-center">
          <ClipboardCheck className="w-16 h-16 text-zinc-700 mx-auto mb-6 opacity-50" />
          <h3 className="text-lg font-bold text-white uppercase tracking-tight mb-2">No Active Surveys</h3>
          <p className="text-xs text-zinc-600 font-mono uppercase tracking-widest leading-relaxed max-w-sm mx-auto">
            There are no eNPS surveys available at this time. Check back later for new surveys.
          </p>
        </div>
      )}

      {/* Multiple Surveys Notice */}
      {pendingSurveys.length > 1 && (
        <div className="bg-zinc-900/30 border border-white/10">
          <div className="px-6 py-4 border-b border-white/10 bg-white/5">
            <h2 className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">{pendingSurveys.length} Surveys Available</h2>
          </div>
          <div className="p-6 flex flex-wrap gap-3">
            {pendingSurveys.map(survey => (
              <button
                key={survey.id}
                onClick={() => setSelectedSurvey(survey)}
                className={`px-6 py-2 text-[10px] font-bold uppercase tracking-widest border transition-all ${
                  selectedSurvey?.id === survey.id
                    ? 'bg-white text-black border-white'
                    : 'bg-zinc-900 text-zinc-500 border-zinc-800 hover:text-white hover:border-zinc-700'
                }`}
              >
                {survey.title}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
