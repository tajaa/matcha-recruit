import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { getCandidateOffer, submitCandidateRange } from '../api/client';
import type { CandidateOfferView, RangeNegotiateResult } from '../api/client';

function formatUsd(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value);
}

type PageState = 'loading' | 'expired' | 'already_matched' | 'awaiting' | 'result';

export default function CandidateOffer() {
  const { token } = useParams<{ token: string }>();
  const [pageState, setPageState] = useState<PageState>('loading');
  const [offer, setOffer] = useState<CandidateOfferView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rangeMin, setRangeMin] = useState('');
  const [rangeMax, setRangeMax] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<RangeNegotiateResult | null>(null);

  useEffect(() => {
    if (!token) return;
    getCandidateOffer(token)
      .then(data => {
        setOffer(data);
        if (data.range_match_status === 'matched') {
          setPageState('already_matched');
        } else {
          setPageState('awaiting');
        }
      })
      .catch((err: { status?: number; detail?: string }) => {
        if (err?.status === 410) {
          setPageState('expired');
        } else {
          setError(err?.detail || 'Offer not found');
          setPageState('expired');
        }
      });
  }, [token]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !rangeMin || !rangeMax) return;
    const min = parseFloat(rangeMin);
    const max = parseFloat(rangeMax);
    if (isNaN(min) || isNaN(max) || min > max) {
      setError('Please enter a valid range (min must be less than or equal to max)');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await submitCandidateRange(token, { range_min: min, range_max: max });
      setResult(res);
      setPageState('result');
    } catch (err: unknown) {
      const apiErr = err as { detail?: string };
      setError(apiErr?.detail || 'Failed to submit range. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-start justify-center pt-16 px-4">
      <div className="w-full max-w-lg">
        {/* Logo / brand */}
        <div className="text-center mb-8">
          <div className="text-2xl font-bold text-emerald-600">Matcha</div>
          <div className="text-sm text-gray-400 mt-1">Salary Range Offer</div>
        </div>

        {pageState === 'loading' && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8 text-center">
            <div className="text-gray-400">Loading offer...</div>
          </div>
        )}

        {pageState === 'expired' && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8 text-center">
            <h2 className="text-lg font-semibold text-gray-800 mb-2">This offer link has expired</h2>
            <p className="text-gray-500 text-sm">{error || 'The link may have expired or is no longer valid. Please contact your recruiter for a new link.'}</p>
          </div>
        )}

        {pageState === 'already_matched' && offer && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8 text-center">
            <h2 className="text-xl font-bold text-gray-800 mb-2">Offer Accepted</h2>
            <p className="text-gray-600 mb-4">
              This offer for <strong>{offer.position_title}</strong> at <strong>{offer.company_name}</strong> has already been accepted.
            </p>
            {offer.matched_salary && (
              <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                <div className="text-sm text-green-600 font-medium">Agreed Salary</div>
                <div className="text-2xl font-bold text-green-700">{formatUsd(offer.matched_salary)}</div>
              </div>
            )}
          </div>
        )}

        {pageState === 'awaiting' && offer && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
            {/* Header */}
            <div className="p-6 border-b border-gray-100">
              {offer.company_logo_url && (
                <img src={offer.company_logo_url} alt="" className="h-10 mb-3 object-contain" />
              )}
              <h1 className="text-xl font-bold text-gray-900">{offer.position_title}</h1>
              <p className="text-gray-500 text-sm mt-1">{offer.company_name}</p>
              {(offer.location || offer.employment_type) && (
                <p className="text-gray-400 text-xs mt-1">
                  {[offer.employment_type, offer.location].filter(Boolean).join(' \u00b7 ')}
                </p>
              )}
            </div>

            {/* Employer range */}
            <div className="p-6 border-b border-gray-100 bg-gray-50">
              <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Offered Salary Range</div>
              <div className="text-2xl font-bold text-gray-900">
                {formatUsd(offer.salary_range_min)} &ndash; {formatUsd(offer.salary_range_max)}
              </div>
              {offer.negotiation_round > 1 && (
                <div className="text-xs text-gray-400 mt-1">
                  Round {offer.negotiation_round} of {offer.max_negotiation_rounds}
                </div>
              )}
            </div>

            {/* Submit form */}
            <div className="p-6">
              <form onSubmit={handleSubmit}>
                <h3 className="font-semibold text-gray-800 mb-1">Your Target Range</h3>
                <p className="text-sm text-gray-500 mb-4">
                  Enter the salary range you'd accept. Neither party sees the other's exact numbers -- the system finds the overlap automatically.
                </p>
                <div className="flex gap-3 mb-4">
                  <div className="flex-1">
                    <label className="text-xs text-gray-500 block mb-1">Minimum ($)</label>
                    <input
                      type="number"
                      value={rangeMin}
                      onChange={e => setRangeMin(e.target.value)}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                      placeholder="e.g. 145000"
                      required
                      min={0}
                    />
                  </div>
                  <div className="flex-1">
                    <label className="text-xs text-gray-500 block mb-1">Maximum ($)</label>
                    <input
                      type="number"
                      value={rangeMax}
                      onChange={e => setRangeMax(e.target.value)}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                      placeholder="e.g. 165000"
                      required
                      min={0}
                    />
                  </div>
                </div>
                {error && (
                  <div className="text-sm text-red-600 mb-3 bg-red-50 border border-red-200 rounded-lg p-3">
                    {error}
                  </div>
                )}
                <button
                  type="submit"
                  disabled={submitting}
                  className="w-full bg-emerald-600 text-white py-2.5 rounded-lg font-medium text-sm hover:bg-emerald-700 disabled:opacity-60 transition-colors"
                >
                  {submitting ? 'Submitting...' : 'Submit My Range'}
                </button>
              </form>
            </div>
          </div>
        )}

        {pageState === 'result' && result && offer && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8 text-center">
            {result.result === 'matched' ? (
              <>
                <h2 className="text-xl font-bold text-gray-800 mb-2">Offer Accepted!</h2>
                <p className="text-gray-600 mb-4">
                  Great news -- your range overlapped with the employer's offer for <strong>{offer.position_title}</strong>.
                </p>
                <div className="bg-green-50 border border-green-200 rounded-lg p-4 inline-block">
                  <div className="text-sm text-green-600 font-medium">Agreed Salary</div>
                  <div className="text-2xl font-bold text-green-700">
                    {result.matched_salary ? formatUsd(result.matched_salary) : '--'}
                  </div>
                </div>
                <p className="text-xs text-gray-400 mt-4">The employer has been notified. Expect to hear from them soon.</p>
              </>
            ) : (
              <>
                <h2 className="text-xl font-bold text-gray-800 mb-2">Ranges Didn't Overlap</h2>
                <p className="text-gray-600 mb-3">
                  {result.result === 'no_match_low'
                    ? "The offer came in below your target range."
                    : "Your target range came in below the employer's minimum."}
                </p>
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-sm text-amber-800">
                  The employer has been notified and may revise the offer. You'll receive a new link if they choose to re-negotiate.
                </div>
              </>
            )}
          </div>
        )}

        <div className="text-center mt-6 text-xs text-gray-400">
          Powered by Matcha Recruit
        </div>
      </div>
    </div>
  );
}
