import { useState, useEffect } from 'react';
import { useParams, useSearchParams, useNavigate } from 'react-router-dom';
import { Button } from '../components';
import { outreach as outreachApi } from '../api/client';
import type { OutreachPublicInfo } from '../types';

export function OutreachLanding() {
  const { token } = useParams<{ token: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [info, setInfo] = useState<OutreachPublicInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [responding, setResponding] = useState(false);
  const [response, setResponse] = useState<{ status: string; message: string } | null>(null);

  // Check if decline param is present
  const isDecline = searchParams.get('decline') === 'true';

  useEffect(() => {
    const loadInfo = async () => {
      if (!token) return;
      try {
        const data = await outreachApi.getInfo(token);
        setInfo(data);

        // If already responded, show appropriate message
        if (data.status === 'interested' || data.status === 'screening_started' || data.status === 'screening_complete') {
          setResponse({
            status: 'interested',
            message: "You've already expressed interest in this opportunity.",
          });
        } else if (data.status === 'declined') {
          setResponse({
            status: 'declined',
            message: "You've already declined this opportunity.",
          });
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load opportunity details');
      } finally {
        setLoading(false);
      }
    };
    loadInfo();
  }, [token]);

  const handleRespond = async (interested: boolean) => {
    if (!token) return;
    setResponding(true);
    try {
      const result = await outreachApi.respond(token, interested);
      setResponse({ status: result.status, message: result.message });

      if (interested && result.interview_url) {
        // Navigate to screening after a short delay
        setTimeout(() => {
          navigate(`/outreach/${token}/screening`);
        }, 2000);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit response');
    } finally {
      setResponding(false);
    }
  };

  // Auto-decline if decline param is present
  useEffect(() => {
    if (isDecline && info && !response && info.status !== 'declined') {
      handleRespond(false);
    }
  }, [isDecline, info, response]);

  if (loading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="text-zinc-500">Loading...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-4">
        <div className="max-w-md text-center">
          <div className="text-red-400 text-lg mb-2">Unable to load</div>
          <p className="text-zinc-500">{error}</p>
        </div>
      </div>
    );
  }

  if (!info) return null;

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-400 font-mono">
      {/* Header */}
      <header className="border-b border-zinc-800/50 bg-zinc-950/90">
        <div className="max-w-2xl mx-auto px-4 py-4 flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-matcha-500 animate-pulse " />
          <span className="text-xs tracking-[0.25em] uppercase text-white font-medium">
            Matcha
          </span>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-4 py-12">
        {response ? (
          // Response received
          <div className="text-center">
            <div
              className={`w-16 h-16 mx-auto mb-6 rounded-full flex items-center justify-center ${
                response.status === 'interested'
                  ? 'bg-matcha-500/20'
                  : 'bg-zinc-800'
              }`}
            >
              {response.status === 'interested' ? (
                <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              ) : (
                <svg className="w-8 h-8 text-zinc-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              )}
            </div>
            <h1 className="text-2xl font-bold text-white mb-4">
              {response.status === 'interested' ? 'Thank you!' : 'No problem'}
            </h1>
            <p className="text-zinc-400 mb-6">{response.message}</p>

            {response.status === 'interested' && (
              <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
                <p className="text-sm text-zinc-500 mb-4">Redirecting to screening interview...</p>
                <Button onClick={() => navigate(`/outreach/${token}/screening`)}>
                  Start Screening Now
                </Button>
              </div>
            )}
          </div>
        ) : (
          // Show opportunity details
          <>
            {info.candidate_name && (
              <p className="text-zinc-500 mb-2">Hi {info.candidate_name},</p>
            )}
            <h1 className="text-3xl font-bold text-white mb-2">
              {info.position_title || 'New Opportunity'}
            </h1>
            <p className="text-xl text-white mb-8">{info.company_name}</p>

            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 mb-8">
              <div className="grid grid-cols-2 gap-6">
                {info.location && (
                  <div>
                    <span className="text-xs text-zinc-500 uppercase tracking-wide">Location</span>
                    <p className="text-zinc-200 mt-1">{info.location}</p>
                  </div>
                )}
                {info.salary_range && (
                  <div>
                    <span className="text-xs text-zinc-500 uppercase tracking-wide">Compensation</span>
                    <p className="text-zinc-200 mt-1">{info.salary_range}</p>
                  </div>
                )}
              </div>

              {info.requirements && (
                <div className="mt-6 pt-6 border-t border-zinc-800">
                  <span className="text-xs text-zinc-500 uppercase tracking-wide">What we're looking for</span>
                  <p className="text-zinc-300 mt-2 whitespace-pre-wrap">{info.requirements}</p>
                </div>
              )}

              {info.benefits && (
                <div className="mt-6 pt-6 border-t border-zinc-800">
                  <span className="text-xs text-zinc-500 uppercase tracking-wide">Benefits</span>
                  <p className="text-zinc-300 mt-2 whitespace-pre-wrap">{info.benefits}</p>
                </div>
              )}
            </div>

            <div className="text-center">
              <p className="text-zinc-400 mb-6">
                Interested in learning more? Express your interest below to proceed to a brief screening conversation.
              </p>

              <div className="flex flex-col sm:flex-row gap-4 justify-center">
                <Button
                  onClick={() => handleRespond(true)}
                  disabled={responding}
                  className="px-8"
                >
                  {responding ? 'Processing...' : "I'm Interested"}
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => handleRespond(false)}
                  disabled={responding}
                  className="px-8"
                >
                  Not for me
                </Button>
              </div>

              <p className="text-xs text-zinc-600 mt-6">
                This link is unique to you and will expire in 14 days.
              </p>
            </div>
          </>
        )}
      </main>
    </div>
  );
}

export default OutreachLanding;
