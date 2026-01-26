import { useState, useEffect } from 'react';
import { Smile, Send, Clock, MessageCircle } from 'lucide-react';
import { vibeChecksApi } from '../../api/xp';
import { MoodRatingInput } from '../../components/xp/MoodRatingInput';
import type { VibeCheckResponse } from '../../types/xp';

export default function PortalVibeCheck() {
  const [moodRating, setMoodRating] = useState(0);
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [history, setHistory] = useState<VibeCheckResponse[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    fetchHistory();
  }, []);

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
    <div className="min-h-screen bg-gradient-to-br from-zinc-950 via-zinc-900 to-zinc-950 p-6">
      <div className="max-w-4xl mx-auto space-y-8">
        {/* Header */}
        <div className="border-b border-white/10 pb-8">
          <div className="flex items-center gap-3 mb-2">
            <Smile className="w-8 h-8 text-emerald-400" />
            <div className="px-2 py-1 border border-emerald-500/20 bg-emerald-900/10 text-emerald-400 text-[9px] uppercase tracking-widest font-mono rounded">
              Pulse Check
            </div>
          </div>
          <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">
            Vibe Check
          </h1>
          <p className="text-sm text-zinc-400 mt-2">
            Share how you're feeling today. Your feedback helps create a better workplace.
          </p>
        </div>

        {success && (
          <div className="bg-emerald-500/10 border border-emerald-500/20 rounded p-4 flex items-center gap-3">
            <div className="text-emerald-400">
              <Smile className="w-5 h-5" />
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

        {/* Submission Form */}
        <div className="bg-zinc-900/30 border border-white/10 p-8">
          <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em] mb-6">
            How are you feeling today?
          </h2>

          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label className="text-[10px] uppercase tracking-wider text-zinc-500 mb-4 block">
                Select your mood
              </label>
              <MoodRatingInput
                value={moodRating}
                onChange={setMoodRating}
                disabled={submitting}
              />
            </div>

            <div>
              <label className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2 block">
                Add a comment (optional)
              </label>
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                disabled={submitting}
                placeholder="Share what's on your mind..."
                rows={4}
                className="w-full bg-zinc-900 border border-white/10 text-white px-4 py-3 text-sm rounded focus:border-white/30 focus:outline-none resize-none disabled:opacity-50"
              />
              <p className="text-xs text-zinc-500 mt-2">
                Your comment helps us understand context and improve our workplace.
              </p>
            </div>

            <button
              type="submit"
              disabled={submitting || moodRating === 0}
              className="w-full bg-white text-black py-3 px-6 text-sm font-medium uppercase tracking-wider hover:bg-zinc-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {submitting ? (
                <>
                  <span className="animate-pulse">Submitting...</span>
                </>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  Submit Feedback
                </>
              )}
            </button>
          </form>
        </div>

        {/* History */}
        <div className="bg-zinc-900/30 border border-white/10">
          <div className="p-6 border-b border-white/10">
            <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em] flex items-center gap-2">
              <Clock className="w-4 h-4" />
              Your History
            </h2>
          </div>

          <div className="divide-y divide-white/5">
            {loadingHistory ? (
              <div className="p-8 text-center text-xs text-zinc-500 uppercase tracking-wider animate-pulse">
                Loading history...
              </div>
            ) : history.length === 0 ? (
              <div className="p-8 text-center">
                <MessageCircle className="w-12 h-12 text-zinc-700 mx-auto mb-3" />
                <p className="text-sm text-zinc-500">No previous submissions</p>
                <p className="text-xs text-zinc-600 mt-1">Your feedback history will appear here</p>
              </div>
            ) : (
              history.map((response) => (
                <div key={response.id} className="p-4 hover:bg-white/5 transition-colors">
                  <div className="flex items-start gap-4">
                    <div className="text-3xl">{getMoodEmoji(response.mood_rating)}</div>
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-1">
                        <span className="text-sm font-medium text-white">
                          {getMoodLabel(response.mood_rating)}
                        </span>
                        <span className="text-xs text-zinc-500 font-mono">
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
                        <p className="text-sm text-zinc-400 mt-2">{response.comment}</p>
                      )}
                      {response.sentiment_analysis && response.sentiment_analysis.themes.length > 0 && (
                        <div className="flex gap-2 mt-3 flex-wrap">
                          {response.sentiment_analysis.themes.map((theme, i) => (
                            <span
                              key={i}
                              className="text-[10px] px-2 py-1 rounded bg-zinc-800/50 text-zinc-400 uppercase tracking-wider"
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
    </div>
  );
}
