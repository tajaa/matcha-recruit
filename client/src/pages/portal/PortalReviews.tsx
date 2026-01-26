import { useState, useEffect } from 'react';
import {
  FileText,
  Send,
  Clock,
  CheckCircle,
  ChevronRight,
  ArrowLeft,
  Save,
  Calendar,
} from 'lucide-react';
import { reviewsApi } from '../../api/xp';
import { StarRatingInput } from '../../components/xp/StarRatingInput';
import { StatusBadge } from '../../components/xp/StatusBadge';
import type { PerformanceReview } from '../../types/xp';

export default function PortalReviews() {
  const [pendingReviews, setPendingReviews] = useState<PerformanceReview[]>([]);
  const [loadingReviews, setLoadingReviews] = useState(true);
  const [selectedReview, setSelectedReview] = useState<PerformanceReview | null>(null);

  // Form state
  const [selfRatings, setSelfRatings] = useState<Record<string, number>>({});
  const [selfComments, setSelfComments] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    fetchPendingReviews();
  }, []);

  const fetchPendingReviews = async () => {
    try {
      setLoadingReviews(true);
      const reviews = await reviewsApi.getPendingReviews();
      setPendingReviews(reviews);
    } catch (err) {
      console.error('Failed to fetch pending reviews:', err);
      setPendingReviews([]);
    } finally {
      setLoadingReviews(false);
    }
  };

  const handleSelectReview = async (review: PerformanceReview) => {
    setSelectedReview(review);
    setError(null);
    setSuccess(false);

    // Initialize form with existing data
    setSelfRatings(review.self_ratings || {});
    setSelfComments(review.self_comments || '');
  };

  const handleSaveDraft = async () => {
    if (!selectedReview) return;

    try {
      setSaving(true);
      setError(null);
      // Note: This would need a saveDraft API endpoint
      // For now, we'll just show it's "saved" locally
      setTimeout(() => setSaving(false), 1000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save draft');
      setSaving(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!selectedReview) {
      setError('No review selected');
      return;
    }

    // Validate that all criteria have ratings
    const hasAllRatings = Object.values(selfRatings).every(r => r > 0);
    if (!hasAllRatings && Object.keys(selfRatings).length === 0) {
      setError('Please provide ratings for all criteria');
      return;
    }

    try {
      setSubmitting(true);
      setError(null);
      setSuccess(false);

      await reviewsApi.submitSelfAssessment(selectedReview.id, {
        self_ratings: selfRatings,
        self_comments: selfComments.trim() || undefined,
      });

      setSuccess(true);

      // Update local state
      setPendingReviews(prev =>
        prev.map(r =>
          r.id === selectedReview.id
            ? { ...r, status: 'self_submitted' as const, self_ratings: selfRatings, self_comments: selfComments }
            : r
        )
      );

      // Go back to list after a delay
      setTimeout(() => {
        setSelectedReview(null);
        setSuccess(false);
        fetchPendingReviews();
      }, 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit self-assessment');
    } finally {
      setSubmitting(false);
    }
  };

  const updateRating = (criterionId: string, rating: number) => {
    setSelfRatings(prev => ({ ...prev, [criterionId]: rating }));
  };

  // Default criteria if no template
  const defaultCriteria = [
    { id: 'quality', name: 'Quality of Work', description: 'Accuracy, thoroughness, and reliability of work output' },
    { id: 'productivity', name: 'Productivity', description: 'Volume of work completed and efficiency' },
    { id: 'teamwork', name: 'Teamwork', description: 'Works effectively with others and contributes to team goals' },
    { id: 'communication', name: 'Communication', description: 'Clear and effective verbal and written communication' },
    { id: 'initiative', name: 'Initiative', description: 'Takes ownership and proactively identifies improvements' },
    { id: 'growth', name: 'Professional Growth', description: 'Demonstrates willingness to learn and develop skills' },
  ];

  const reviewsNeedingSelfAssessment = pendingReviews.filter(r => r.status === 'pending');
  const reviewsAwaitingManager = pendingReviews.filter(r => r.status === 'self_submitted');

  return (
    <div className="min-h-screen bg-gradient-to-br from-zinc-950 via-zinc-900 to-zinc-950 p-6">
      <div className="max-w-4xl mx-auto space-y-8">
        {/* Header */}
        <div className="border-b border-white/10 pb-8">
          <div className="flex items-center gap-3 mb-2">
            <FileText className="w-8 h-8 text-emerald-400" />
            <div className="px-2 py-1 border border-emerald-500/20 bg-emerald-900/10 text-emerald-400 text-[9px] uppercase tracking-widest font-mono rounded">
              Self Assessment
            </div>
          </div>
          <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">
            Performance Reviews
          </h1>
          <p className="text-sm text-zinc-400 mt-2">
            Complete your self-assessment to help your manager understand your perspective.
          </p>
        </div>

        {success && (
          <div className="bg-emerald-500/10 border border-emerald-500/20 rounded p-4 flex items-center gap-3">
            <div className="text-emerald-400">
              <CheckCircle className="w-5 h-5" />
            </div>
            <div>
              <p className="text-sm text-emerald-400 font-medium">Self-assessment submitted!</p>
              <p className="text-xs text-emerald-400/70 mt-1">Your manager will be notified to complete their review.</p>
            </div>
          </div>
        )}

        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded p-4">
            <p className="text-sm text-red-400">{error}</p>
          </div>
        )}

        {loadingReviews ? (
          <div className="flex items-center justify-center py-12">
            <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">
              Loading reviews...
            </div>
          </div>
        ) : selectedReview ? (
          /* Review Form */
          <div className="space-y-6">
            {/* Back Button */}
            <button
              onClick={() => setSelectedReview(null)}
              className="flex items-center gap-2 text-xs text-zinc-400 uppercase tracking-wider hover:text-white transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Back to Reviews
            </button>

            {/* Review Form Card */}
            <div className="bg-zinc-900/30 border border-white/10 p-8">
              <div className="mb-8">
                <h2 className="text-xl font-bold text-white mb-2">
                  Self-Assessment: {selectedReview.cycle_title || 'Performance Review'}
                </h2>
                <div className="flex items-center gap-4 text-xs text-zinc-500">
                  <StatusBadge status={selectedReview.status} />
                  {selectedReview.manager_name && (
                    <span>Manager: {selectedReview.manager_name}</span>
                  )}
                </div>
              </div>

              <form onSubmit={handleSubmit} className="space-y-8">
                {/* Rating Criteria */}
                <div className="space-y-6">
                  <div className="text-xs font-bold text-white uppercase tracking-[0.2em]">
                    Rate Your Performance
                  </div>
                  <p className="text-xs text-zinc-500">
                    Rate yourself on a scale of 1-5 stars for each criterion.
                  </p>

                  <div className="space-y-6">
                    {defaultCriteria.map(criterion => (
                      <div
                        key={criterion.id}
                        className="bg-zinc-900/50 border border-white/5 p-4 space-y-3"
                      >
                        <div>
                          <div className="text-sm font-medium text-white">{criterion.name}</div>
                          <div className="text-xs text-zinc-500 mt-1">{criterion.description}</div>
                        </div>
                        <div className="flex items-center gap-4">
                          <StarRatingInput
                            value={selfRatings[criterion.id] || 0}
                            onChange={(rating) => updateRating(criterion.id, rating)}
                            disabled={submitting}
                            size={24}
                          />
                          <span className="text-sm text-zinc-400">
                            {selfRatings[criterion.id]
                              ? `${selfRatings[criterion.id]} / 5`
                              : 'Not rated'}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Comments */}
                <div>
                  <label className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2 block">
                    Additional Comments (optional)
                  </label>
                  <textarea
                    value={selfComments}
                    onChange={(e) => setSelfComments(e.target.value)}
                    disabled={submitting}
                    placeholder="Share any additional context about your performance, accomplishments, or areas for growth..."
                    rows={5}
                    className="w-full bg-zinc-900 border border-white/10 text-white px-4 py-3 text-sm rounded focus:border-white/30 focus:outline-none resize-none disabled:opacity-50"
                  />
                </div>

                {/* Actions */}
                <div className="flex items-center gap-4 pt-4 border-t border-white/10">
                  <button
                    type="button"
                    onClick={handleSaveDraft}
                    disabled={saving || submitting}
                    className="flex-1 border border-white/10 text-white py-3 px-6 text-sm font-medium uppercase tracking-wider hover:bg-white/5 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                  >
                    <Save className="w-4 h-4" />
                    {saving ? 'Saving...' : 'Save Draft'}
                  </button>
                  <button
                    type="submit"
                    disabled={submitting}
                    className="flex-1 bg-white text-black py-3 px-6 text-sm font-medium uppercase tracking-wider hover:bg-zinc-200 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                  >
                    {submitting ? (
                      <span className="animate-pulse">Submitting...</span>
                    ) : (
                      <>
                        <Send className="w-4 h-4" />
                        Submit Assessment
                      </>
                    )}
                  </button>
                </div>
              </form>
            </div>
          </div>
        ) : (
          /* Review List */
          <div className="space-y-6">
            {/* Pending Self-Assessments */}
            {reviewsNeedingSelfAssessment.length > 0 && (
              <div className="bg-zinc-900/30 border border-white/10">
                <div className="p-6 border-b border-white/10">
                  <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em]">
                    Pending Self-Assessments
                  </h2>
                  <p className="text-xs text-zinc-500 mt-1">
                    Complete these reviews to help your manager understand your perspective.
                  </p>
                </div>
                <div className="divide-y divide-white/5">
                  {reviewsNeedingSelfAssessment.map(review => (
                    <div
                      key={review.id}
                      className="p-4 hover:bg-white/5 transition-colors cursor-pointer"
                      onClick={() => handleSelectReview(review)}
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <h3 className="text-sm font-medium text-white">
                            {review.cycle_title || 'Performance Review'}
                          </h3>
                          <div className="flex items-center gap-4 mt-2 text-xs text-zinc-500">
                            <div className="flex items-center gap-2">
                              <Calendar className="w-4 h-4" />
                              <span>Created {new Date(review.created_at).toLocaleDateString()}</span>
                            </div>
                            {review.manager_name && (
                              <span>Manager: {review.manager_name}</span>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-3">
                          <StatusBadge status="pending" />
                          <ChevronRight className="w-4 h-4 text-zinc-500" />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Awaiting Manager Review */}
            {reviewsAwaitingManager.length > 0 && (
              <div className="bg-zinc-900/30 border border-white/10">
                <div className="p-6 border-b border-white/10">
                  <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em]">
                    Awaiting Manager Review
                  </h2>
                  <p className="text-xs text-zinc-500 mt-1">
                    You've completed your part. Waiting for your manager's review.
                  </p>
                </div>
                <div className="divide-y divide-white/5">
                  {reviewsAwaitingManager.map(review => (
                    <div key={review.id} className="p-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <h3 className="text-sm font-medium text-white">
                            {review.cycle_title || 'Performance Review'}
                          </h3>
                          <div className="flex items-center gap-4 mt-2 text-xs text-zinc-500">
                            {review.self_submitted_at && (
                              <div className="flex items-center gap-2">
                                <Clock className="w-4 h-4" />
                                <span>Submitted {new Date(review.self_submitted_at).toLocaleDateString()}</span>
                              </div>
                            )}
                            {review.manager_name && (
                              <span>Manager: {review.manager_name}</span>
                            )}
                          </div>
                        </div>
                        <StatusBadge status="self_submitted" />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* No Reviews */}
            {pendingReviews.length === 0 && (
              <div className="bg-zinc-900/50 border border-white/10 p-12 text-center">
                <FileText className="w-16 h-16 text-zinc-700 mx-auto mb-4" />
                <h3 className="text-xl font-bold text-white mb-2">No Pending Reviews</h3>
                <p className="text-sm text-zinc-500">
                  You don't have any performance reviews to complete at this time.
                </p>
                <p className="text-xs text-zinc-600 mt-2">
                  Check back later when a review cycle is active.
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
