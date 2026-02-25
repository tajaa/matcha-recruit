import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { matchaWorkPublic } from '../api/client';
import type { MWPublicReviewRequest } from '../types/matcha-work';

export default function MatchaWorkReviewRequest() {
  const { token } = useParams<{ token: string }>();
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [request, setRequest] = useState<MWPublicReviewRequest | null>(null);
  const [feedback, setFeedback] = useState('');
  const [rating, setRating] = useState<number | ''>('');
  const [error, setError] = useState<string | null>(null);
  const [submittedAt, setSubmittedAt] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setError('Invalid review link');
      setLoading(false);
      return;
    }
    let isMounted = true;
    (async () => {
      try {
        const data = await matchaWorkPublic.getReviewRequest(token);
        if (!isMounted) return;
        setRequest(data);
        if (data.status === 'submitted' && data.submitted_at) {
          setSubmittedAt(data.submitted_at);
        }
      } catch (err) {
        if (!isMounted) return;
        setError(err instanceof Error ? err.message : 'Failed to load review request');
      } finally {
        if (isMounted) setLoading(false);
      }
    })();
    return () => {
      isMounted = false;
    };
  }, [token]);

  const handleSubmit = async () => {
    if (!token || !feedback.trim() || submitting) return;
    try {
      setSubmitting(true);
      setError(null);
      const resp = await matchaWorkPublic.submitReviewRequest(token, {
        feedback: feedback.trim(),
        rating: rating === '' ? undefined : rating,
      });
      setSubmittedAt(resp.submitted_at);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit response');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center">
        <div className="text-sm text-zinc-400">Loading review request...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center p-4">
      <div className="w-full max-w-2xl bg-zinc-900 border border-zinc-800 rounded-2xl p-6 sm:p-8">
        <h1 className="text-xl font-semibold text-zinc-100">Anonymous Review Response</h1>
        <p className="text-sm text-zinc-400 mt-2">
          {request?.review_title || 'Review request'}
        </p>

        {error && (
          <div className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
            {error}
          </div>
        )}

        {submittedAt ? (
          <div className="mt-6 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3">
            <p className="text-sm text-emerald-300 font-medium">Response submitted</p>
            <p className="text-xs text-emerald-300/80 mt-1">
              Submitted on {new Date(submittedAt).toLocaleString()}
            </p>
          </div>
        ) : (
          <div className="mt-6 space-y-4">
            <label className="block">
              <span className="text-xs uppercase tracking-wide text-zinc-500">Rating (optional)</span>
              <select
                value={rating}
                onChange={(e) => setRating(e.target.value ? Number(e.target.value) : '')}
                className="mt-1 w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-matcha-500/50"
              >
                <option value="">Select rating</option>
                <option value="1">1 - Needs significant improvement</option>
                <option value="2">2 - Below expectations</option>
                <option value="3">3 - Meets expectations</option>
                <option value="4">4 - Exceeds expectations</option>
                <option value="5">5 - Outstanding</option>
              </select>
            </label>

            <label className="block">
              <span className="text-xs uppercase tracking-wide text-zinc-500">Feedback</span>
              <textarea
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                rows={8}
                placeholder="Share your feedback..."
                className="mt-1 w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-matcha-500/50"
              />
            </label>

            <button
              onClick={handleSubmit}
              disabled={submitting || !feedback.trim()}
              className="w-full sm:w-auto px-4 py-2 text-sm bg-matcha-600 hover:bg-matcha-700 disabled:opacity-50 text-white rounded-lg transition-colors"
            >
              {submitting ? 'Submitting...' : 'Submit Response'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
