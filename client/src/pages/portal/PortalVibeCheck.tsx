import { useState, useEffect } from 'react';
import { Smile, Send, Clock, MessageCircle, CalendarClock, AlertCircle } from 'lucide-react';
import { vibeChecksApi } from '../../api/xp';
import { MoodRatingInput } from '../../components/xp/MoodRatingInput';
import type { VibeCheckResponse } from '../../types/xp';

interface VibeCheckStatus {
  enabled: boolean;
  can_submit: boolean;
  already_submitted?: boolean;
  next_available?: string;
  message: string;
}

export default function PortalVibeCheck() {
  const [moodRating, setMoodRating] = useState(0);
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [history, setHistory] = useState<VibeCheckResponse[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [status, setStatus] = useState<VibeCheckStatus | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    fetchStatus();
    fetchHistory();
  }, []);

  const fetchStatus = async () => {
    try {
      setLoadingStatus(true);
      const data = await vibeChecksApi.getStatus();
      setStatus(data);
    } catch (err) {
      console.error('Failed to fetch status:', err);
    } finally {
      setLoadingStatus(false);
    }
  };

  const fetchHistory = async () => {
    try {
      setLoadingHistory(true);
      const data = await vibeChecksApi.getHistory();
      setHistory(data);
    } catch (err) {
      console.error('Failed to fetch history:', err);
    } finally {
      setLoadingHistory(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (moodRating === 0) {
      setError('Please select a mood rating');
      return;
    }

    try {
      setSubmitting(true);
      setError(null);
      setSuccess(false);

      await vibeChecksApi.submitResponse({
        mood_rating: moodRating,
        comment: comment.trim() || undefined,
      });

      setSuccess(true);
      setMoodRating(0);
      setComment('');
      fetchStatus();
      fetchHistory();

      setTimeout(() => setSuccess(false), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit response');
    } finally {
      setSubmitting(false);
    }
  };

  const getMoodEmoji = (rating: number) => {
    const emojis = ['', '😞', '😕', '😐', '🙂', '😄'];
    return emojis[rating] || '';
  };

  const getMoodLabel = (rating: number) => {
    const labels = ['', 'Very Bad', 'Bad', 'Okay', 'Good', 'Great'];
    return labels[rating] || '';
  };

  return (
    <div className="space-y-8 max-w-5xl">
      {/* Header */}
      <div className="border-b border-white/10 pb-6">
        <div className="flex items-center gap-3 mb-2">
          <Smile className="w-8 h-8 text-emerald-400" />
          <div className="px-2 py-1 border border-emerald-500/20 bg-emerald-900/10 text-emerald-400 text-[9px] uppercase tracking-widest font-mono rounded">
            Pulse Check
          </div>
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-white uppercase">Vibe Check</h1>
        <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">Share how you're feeling today. Your feedback helps create a better workplace.</p>
      </div>

      {success && (
        <div className="bg-emerald-500/10 border border-emerald-500/20 p-4 flex items-center gap-3 animate-in fade-in duration-500">
          <Smile className="w-5 h-5 text-emerald-400" />
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

      {/* Submission Form */}
      <div className="bg-zinc-900/30 border border-dashed border-white/10 p-8">
        {loadingStatus ? (
          <div className="text-center py-12">
            <div className="text-xs text-zinc-500 uppercase tracking-widest font-mono animate-pulse">Scanning Status...</div>
          </div>
        ) : status && !status.can_submit ? (
          <div className="text-center py-12 space-y-4">
            <CalendarClock className="w-12 h-12 text-zinc-700 mx-auto mb-4 opacity-50" />
            <h2 className="text-sm font-bold text-white uppercase tracking-widest">Feedback Cycle Complete</h2>
            <p className="text-xs text-zinc-500 uppercase tracking-widest font-mono max-w-md mx-auto leading-relaxed">
              Thanks for your feedback! You've already submitted your vibe check for this cycle.
            </p>
            {status.next_available && (
              <div className="pt-4">
                <p className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold mb-1">Next submission opens</p>
                <p className="text-xs text-emerald-400 font-mono">
                  {new Date(status.next_available).toLocaleDateString('en-US', {
                    weekday: 'long',
                    month: 'short',
                    day: 'numeric',
                    hour: 'numeric',
                    minute: '2-digit',
                  })}
                </p>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-10">
            <div>
              <h2 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-8 ml-1">How are you feeling today?</h2>
              <MoodRatingInput
                value={moodRating}
                onChange={setMoodRating}
                disabled={submitting}
              />
            </div>

            <form onSubmit={handleSubmit} className="space-y-8">
              <div>
                <label className="text-[9px] font-bold uppercase tracking-widest text-zinc-600 mb-2 ml-1 block">
                  Add a comment (optional)
                </label>
                <textarea
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  disabled={submitting}
                  placeholder="Share what's on your mind..."
                  rows={4}
                  className="w-full bg-zinc-950 border border-zinc-800 text-white px-4 py-3 text-sm focus:border-white transition-colors outline-none resize-none disabled:opacity-50 font-mono leading-relaxed"
                />
              </div>

              <button
                type="submit"
                disabled={submitting || moodRating === 0}
                className="w-full bg-white text-black py-4 px-8 text-[10px] font-bold uppercase tracking-widest border border-white hover:bg-zinc-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-3"
              >
                {submitting ? (
                  <span className="animate-pulse">Processing...</span>
                ) : (
                  <>
                    <Send className="w-4 h-4" />
                    Submit Feedback
                  </>
                )}
              </button>
            </form>
          </div>
        )}
      </div>

      {/* History */}
      <div className="bg-zinc-900/30 border border-white/10">
        <div className="px-6 py-4 border-b border-white/10 bg-white/5">
          <h2 className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 flex items-center gap-2">
            <Clock className="w-4 h-4" />
            Your History
          </h2>
        </div>

        <div className="divide-y divide-white/5">
          {loadingHistory ? (
            <div className="p-12 text-center text-[10px] text-zinc-500 uppercase tracking-widest font-mono animate-pulse">
              Retrieving history...
            </div>
          ) : history.length === 0 ? (
            <div className="p-16 text-center">
              <MessageCircle className="w-12 h-12 text-zinc-700 mx-auto mb-4 opacity-50" />
              <p className="text-xs text-zinc-500 font-mono uppercase tracking-widest">No previous submissions</p>
            </div>
          ) : (
            history.map((response) => (
              <div key={response.id} className="p-6 hover:bg-white/5 transition-colors group">
                <div className="flex items-start gap-6">
                  <div className="text-4xl filter grayscale group-hover:grayscale-0 transition-all duration-300 transform group-hover:scale-110">
                    {getMoodEmoji(response.mood_rating)}
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-4 mb-2">
                      <span className="text-sm font-bold text-white tracking-tight uppercase">
                        {getMoodLabel(response.mood_rating)}
                      </span>
                      <span className="text-[9px] text-zinc-600 font-mono uppercase tracking-widest">
                        {new Date(response.created_at).toLocaleDateString('en-US', {
                          month: 'short',
                          day: 'numeric',
                          year: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </span>
                    </div>
                    {response.comment && (
                      <p className="text-[11px] text-zinc-400 mt-2 font-mono uppercase tracking-wide leading-relaxed">{response.comment}</p>
                    )}
                    {response.sentiment_analysis && response.sentiment_analysis.themes.length > 0 && (
                      <div className="flex gap-2 mt-4 flex-wrap">
                        {response.sentiment_analysis.themes.map((theme, i) => (
                          <span
                            key={i}
                            className="text-[8px] px-2 py-0.5 border border-white/5 bg-white/5 text-zinc-500 uppercase tracking-widest font-bold"
                          >
                            {theme}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
