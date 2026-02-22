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
  AlertCircle
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
    } finally {
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
    const requiredCriteria = ['quality', 'productivity', 'teamwork', 'communication', 'initiative', 'growth'];
    const missingRatings = requiredCriteria.filter(id => !selfRatings[id] || selfRatings[id] <= 0);
    if (missingRatings.length > 0) {
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
    <div className="space-y-8 max-w-5xl">
      {/* Header */}
      <div className="border-b border-white/10 pb-6">
        <div className="flex items-center gap-3 mb-2">
          <FileText className="w-8 h-8 text-emerald-400" />
          <div className="px-2 py-1 border border-emerald-500/20 bg-emerald-900/10 text-emerald-400 text-[9px] uppercase tracking-widest font-mono rounded">
            Self Assessment
          </div>
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-white uppercase">Performance Reviews</h1>
        <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">Complete your self-assessment to help your manager understand your perspective.</p>
      </div>

      {success && (
        <div className="bg-emerald-500/10 border border-emerald-500/20 p-4 flex items-center gap-3 animate-in fade-in duration-500">
          <CheckCircle className="w-5 h-5 text-emerald-400" />
          <div>
            <p className="text-sm text-emerald-400 font-bold uppercase tracking-tight">Self-assessment submitted!</p>
            <p className="text-[10px] text-emerald-400/70 mt-1 uppercase tracking-widest font-mono">Your manager will be notified to complete their review.</p>
          </div>
        </div>
      )}

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 p-4 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-400" />
          <p className="text-sm text-red-400 font-mono uppercase">{error}</p>
        </div>
      )}

      {loadingReviews ? (
        <div className="flex items-center justify-center py-24">
          <div className="flex flex-col items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-zinc-600 animate-pulse" />
            <span className="text-xs text-zinc-500 font-mono uppercase tracking-widest">Loading Reviews...</span>
          </div>
        </div>
      ) : selectedReview ? (
        /* Review Form */
        <div className="space-y-6 animate-in slide-in-from-right-4 duration-300">
          {/* Back Button */}
          <button
            onClick={() => setSelectedReview(null)}
            className="flex items-center gap-2 text-[10px] text-zinc-500 font-bold uppercase tracking-widest hover:text-white transition-colors group"
          >
            <ArrowLeft className="w-4 h-4 group-hover:-translate-x-1 transition-transform" />
            Back to Reviews
          </button>

          {/* Review Form Card */}
          <div className="bg-zinc-900/30 border border-dashed border-white/10 p-8">
            <div className="mb-8 pb-8 border-b border-white/10">
              <h2 className="text-xl font-bold text-white tracking-tight uppercase mb-2">
                Self-Assessment: {selectedReview.cycle_title || 'Performance Review'}
              </h2>
              <div className="flex items-center gap-6 mt-4">
                <StatusBadge status={selectedReview.status} />
                {selectedReview.manager_name && (
                  <span className="text-[10px] text-zinc-500 font-mono uppercase tracking-widest">Manager: <span className="text-white">{selectedReview.manager_name}</span></span>
                )}
              </div>
            </div>

            <form onSubmit={handleSubmit} className="space-y-10">
              {/* Rating Criteria */}
              <div className="space-y-6">
                <div>
                  <div className="text-[10px] font-bold text-white uppercase tracking-widest mb-1">Rate Your Performance</div>
                  <p className="text-xs text-zinc-500 font-mono uppercase tracking-widest">Rate yourself on a scale of 1-5 stars for each criterion.</p>
                </div>

                <div className="grid grid-cols-1 gap-4">
                  {defaultCriteria.map(criterion => (
                    <div
                      key={criterion.id}
                      className="bg-zinc-950/50 border border-white/5 p-6 space-y-4 hover:border-white/10 transition-colors"
                    >
                      <div className="flex justify-between items-start">
                        <div>
                          <div className="text-sm font-bold text-white uppercase tracking-tight">{criterion.name}</div>
                          <div className="text-[11px] text-zinc-500 mt-1 font-mono uppercase tracking-wide leading-relaxed">{criterion.description}</div>
                        </div>
                        <span className="text-[10px] text-zinc-600 font-mono uppercase tracking-widest tabular-nums">
                          {selfRatings[criterion.id] ? `${selfRatings[criterion.id]} / 5` : 'Not rated'}
                        </span>
                      </div>
                      <div className="flex items-center gap-4">
                        <StarRatingInput
                          value={selfRatings[criterion.id] || 0}
                          onChange={(rating) => updateRating(criterion.id, rating)}
                          disabled={submitting}
                          size={20}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Comments */}
              <div>
                <label className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 mb-2 ml-1 block">
                  Additional Comments (optional)
                </label>
                <textarea
                  value={selfComments}
                  onChange={(e) => setSelfComments(e.target.value)}
                  disabled={submitting}
                  placeholder="Share any additional context about your performance, accomplishments, or areas for growth..."
                  rows={6}
                  className="w-full bg-zinc-950 border border-zinc-800 text-white px-4 py-3 text-sm focus:border-white transition-colors outline-none resize-none disabled:opacity-50 font-mono leading-relaxed"
                />
              </div>

              {/* Actions */}
              <div className="flex items-center gap-4 pt-6 border-t border-white/5">
                <button
                  type="button"
                  onClick={handleSaveDraft}
                  disabled={saving || submitting}
                  className="flex-1 border border-white/10 text-zinc-400 py-4 px-6 text-[10px] font-bold uppercase tracking-widest hover:text-white hover:border-white/30 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  <Save className="w-4 h-4" />
                  {saving ? 'Saving...' : 'Save Draft'}
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="flex-1 bg-white text-black py-4 px-6 text-[10px] font-bold uppercase tracking-widest hover:bg-zinc-200 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
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
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Pending Self-Assessments */}
          <div className="bg-zinc-900/30 border border-white/10 h-fit">
            <div className="px-6 py-4 border-b border-white/10 bg-white/5">
              <h2 className="text-[10px] font-bold text-white uppercase tracking-widest">Pending Self-Assessments</h2>
              <p className="text-[9px] text-zinc-600 uppercase tracking-widest mt-1">Complete these reviews</p>
            </div>
            {reviewsNeedingSelfAssessment.length === 0 ? (
               <div className="p-12 text-center">
                <FileText className="w-10 h-10 mx-auto text-zinc-700 mb-4 opacity-50" />
                <p className="text-xs text-zinc-500 font-mono uppercase tracking-widest">No pending assessments</p>
              </div>
            ) : (
              <div className="divide-y divide-white/5">
                {reviewsNeedingSelfAssessment.map(review => (
                  <button
                    key={review.id}
                    className="w-full p-6 hover:bg-white/5 transition-colors text-left group"
                    onClick={() => handleSelectReview(review)}
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="text-sm font-bold text-white tracking-tight group-hover:text-emerald-400 transition-colors">
                          {review.cycle_title || 'Performance Review'}
                        </h3>
                        <div className="flex flex-col gap-1 mt-2">
                          <div className="flex items-center gap-2 text-[10px] text-zinc-500 font-mono uppercase tracking-widest">
                            <Calendar className="w-3 h-3" />
                            <span>Created {new Date(review.created_at).toLocaleDateString()}</span>
                          </div>
                          {review.manager_name && (
                            <span className="text-[10px] text-zinc-600 font-mono uppercase tracking-widest pl-5">Manager: {review.manager_name}</span>
                          )}
                        </div>
                      </div>
                      <ChevronRight className="w-4 h-4 text-zinc-600 group-hover:text-white transition-colors" />
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Awaiting Manager Review */}
          <div className="bg-zinc-900/30 border border-white/10 h-fit">
            <div className="px-6 py-4 border-b border-white/10 bg-white/5">
              <h2 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Awaiting Manager Review</h2>
              <p className="text-[9px] text-zinc-600 uppercase tracking-widest mt-1">Waiting for manager feedback</p>
            </div>
            {reviewsAwaitingManager.length === 0 ? (
               <div className="p-12 text-center">
                <Clock className="w-10 h-10 mx-auto text-zinc-700 mb-4 opacity-50" />
                <p className="text-xs text-zinc-500 font-mono uppercase tracking-widest">No reviews in progress</p>
              </div>
            ) : (
              <div className="divide-y divide-white/5">
                {reviewsAwaitingManager.map(review => (
                  <div key={review.id} className="p-6 opacity-75 hover:opacity-100 transition-opacity">
                    <div className="flex items-start justify-between">
                      <div>
                        <h3 className="text-sm font-bold text-zinc-300 tracking-tight">
                          {review.cycle_title || 'Performance Review'}
                        </h3>
                        <div className="flex flex-col gap-1 mt-2">
                          {review.self_submitted_at && (
                            <div className="flex items-center gap-2 text-[10px] text-zinc-500 font-mono uppercase tracking-widest">
                              <Clock className="w-3 h-3" />
                              <span>Submitted {new Date(review.self_submitted_at).toLocaleDateString()}</span>
                            </div>
                          )}
                          {review.manager_name && (
                            <span className="text-[10px] text-zinc-600 font-mono uppercase tracking-widest pl-5">Manager: {review.manager_name}</span>
                          )}
                        </div>
                      </div>
                      <div className="scale-75 origin-right">
                        <StatusBadge status="self_submitted" />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
