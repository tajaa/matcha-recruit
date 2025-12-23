import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, Card, CardContent } from '../components';
import { outreach as outreachApi } from '../api/client';
import type { OutreachPublicInfo } from '../types';
import { useAudioInterview } from '../hooks/useAudioInterview';

export function OutreachScreening() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [info, setInfo] = useState<OutreachPublicInfo | null>(null);
  const [interviewId, setInterviewId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [completed, setCompleted] = useState(false);

  // Audio interview hook - only active once we have an interview ID
  const {
    isConnected,
    isRecording,
    messages,
    sessionTimeRemaining,
    connect,
    disconnect,
    startRecording,
    stopRecording,
  } = useAudioInterview(interviewId || '');

  // Scroll to bottom of messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Load outreach info
  useEffect(() => {
    const loadInfo = async () => {
      if (!token) return;
      try {
        const data = await outreachApi.getInfo(token);
        setInfo(data);

        // Check status
        if (data.status === 'screening_complete') {
          setCompleted(true);
        } else if (data.status === 'declined') {
          setError('This opportunity has been declined.');
        } else if (data.status !== 'interested' && data.status !== 'screening_started') {
          // Not yet expressed interest
          navigate(`/outreach/${token}`);
          return;
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load');
      } finally {
        setLoading(false);
      }
    };
    loadInfo();
  }, [token, navigate]);

  // Start the screening interview
  const handleStartInterview = async () => {
    if (!token) return;
    setStarting(true);
    try {
      const result = await outreachApi.startInterview(token);
      setInterviewId(result.interview_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start interview');
    } finally {
      setStarting(false);
    }
  };

  // End the interview
  const handleEnd = () => {
    disconnect();
    setCompleted(true);
  };

  // Format time remaining
  const formatTime = (seconds: number | null) => {
    if (seconds === null) return '';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

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

  if (completed) {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-400 font-mono">
        <header className="border-b border-zinc-800/50 bg-zinc-950/90">
          <div className="max-w-2xl mx-auto px-4 py-4 flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-matcha-500 animate-pulse shadow-[0_0_8px_rgba(34,197,94,0.6)]" />
            <span className="text-xs tracking-[0.25em] uppercase text-matcha-500 font-medium">
              Matcha
            </span>
          </div>
        </header>

        <main className="max-w-2xl mx-auto px-4 py-12">
          <div className="text-center">
            <div className="w-16 h-16 mx-auto mb-6 rounded-full bg-matcha-500/20 flex items-center justify-center">
              <svg className="w-8 h-8 text-matcha-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold text-white mb-4">Screening Complete!</h1>
            <p className="text-zinc-400 mb-6">
              Thank you for completing the screening interview. Our team will review your responses
              and be in touch soon.
            </p>
            <Card>
              <CardContent className="p-6">
                <p className="text-sm text-zinc-500">
                  Position: <span className="text-zinc-300">{info?.position_title || 'N/A'}</span>
                </p>
                <p className="text-sm text-zinc-500 mt-2">
                  Company: <span className="text-zinc-300">{info?.company_name}</span>
                </p>
              </CardContent>
            </Card>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-400 font-mono">
      {/* Header */}
      <header className="border-b border-zinc-800/50 bg-zinc-950/90 sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-matcha-500 animate-pulse shadow-[0_0_8px_rgba(34,197,94,0.6)]" />
            <span className="text-xs tracking-[0.25em] uppercase text-matcha-500 font-medium">
              Matcha
            </span>
          </div>
          {sessionTimeRemaining !== null && (
            <div className="text-sm text-zinc-500">
              Time: <span className="text-zinc-300 font-medium">{formatTime(sessionTimeRemaining)}</span>
            </div>
          )}
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-8">
        {/* Info Banner */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 mb-6">
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-xl font-bold text-white">
                {info?.position_title || 'Screening Interview'}
              </h1>
              <p className="text-matcha-400">{info?.company_name}</p>
            </div>
            {info?.candidate_name && (
              <div className="text-right text-sm">
                <span className="text-zinc-500">Candidate:</span>
                <p className="text-zinc-300">{info.candidate_name}</p>
              </div>
            )}
          </div>
        </div>

        {!interviewId ? (
          // Pre-interview state
          <div className="text-center py-12">
            <div className="w-20 h-20 mx-auto mb-6 rounded-full bg-zinc-800 flex items-center justify-center">
              <svg className="w-10 h-10 text-zinc-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-white mb-4">Ready for your screening?</h2>
            <p className="text-zinc-400 mb-8 max-w-md mx-auto">
              You'll have a brief conversation with our AI interviewer. This helps us learn more
              about your background and fit for the role.
            </p>
            <Button onClick={handleStartInterview} disabled={starting} className="px-8 py-3 text-lg">
              {starting ? 'Starting...' : 'Begin Screening'}
            </Button>

            <div className="mt-8 p-5 bg-matcha-500/5 rounded-xl border border-matcha-500/10 text-left max-w-md mx-auto">
              <h3 className="font-semibold text-matcha-400 mb-3 flex items-center gap-2">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                Before you begin
              </h3>
              <ul className="text-sm text-zinc-400 space-y-2 ml-1">
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 w-1 h-1 rounded-full bg-matcha-500 flex-shrink-0"></span>
                  Find a quiet place with minimal background noise
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 w-1 h-1 rounded-full bg-matcha-500 flex-shrink-0"></span>
                  Use headphones for best audio quality
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 w-1 h-1 rounded-full bg-matcha-500 flex-shrink-0"></span>
                  The interview takes about 5-10 minutes
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 w-1 h-1 rounded-full bg-matcha-500 flex-shrink-0"></span>
                  Speak naturally about your experience
                </li>
              </ul>
            </div>
          </div>
        ) : (
          // Interview in progress
          <>
            <Card className="mb-6">
              <CardContent>
                {/* Connection Status */}
                <div className="flex items-center justify-between mb-6">
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-3 h-3 rounded-full shadow-[0_0_10px_currentColor] transition-colors ${
                        isConnected ? 'bg-matcha-500 text-matcha-500' : 'bg-zinc-600 text-zinc-600'
                      }`}
                    />
                    <span className="text-sm font-medium text-zinc-300">
                      {isConnected ? 'Connected' : 'Disconnected'}
                    </span>
                  </div>
                  {isRecording && (
                    <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-red-500/10 border border-red-500/20">
                      <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                      <span className="text-sm font-medium text-red-400">Recording</span>
                    </div>
                  )}
                </div>

                {/* Controls */}
                <div className="flex gap-4">
                  {!isConnected ? (
                    <Button onClick={connect} className="flex-1 py-4 text-lg">
                      Connect to AI Interviewer
                    </Button>
                  ) : (
                    <>
                      {!isRecording ? (
                        <Button onClick={startRecording} className="flex-1 py-4 text-lg shadow-[0_0_20px_rgba(34,197,94,0.2)]">
                          <svg className="w-6 h-6 mr-3" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
                            <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
                          </svg>
                          Start Speaking
                        </Button>
                      ) : (
                        <Button onClick={stopRecording} variant="danger" className="flex-1 py-4 text-lg">
                          <svg className="w-6 h-6 mr-3" fill="currentColor" viewBox="0 0 24 24">
                            <rect x="6" y="6" width="12" height="12" />
                          </svg>
                          Stop Speaking
                        </Button>
                      )}
                      <Button onClick={handleEnd} variant="secondary" className="px-8">
                        End
                      </Button>
                    </>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Conversation */}
            <Card>
              <CardContent className="h-[400px] overflow-y-auto custom-scrollbar p-6">
                {messages.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full text-zinc-500 space-y-4">
                    <div className="w-16 h-16 rounded-full bg-zinc-800 flex items-center justify-center">
                      <svg className="w-8 h-8 text-zinc-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                      </svg>
                    </div>
                    <p>Connect and start speaking to begin</p>
                  </div>
                ) : (
                  <div className="space-y-6">
                    {messages.map((msg, idx) => (
                      <div
                        key={idx}
                        className={`flex ${
                          msg.type === 'user' ? 'justify-end' : 'justify-start'
                        }`}
                      >
                        <div
                          className={`max-w-[80%] px-5 py-3 rounded-2xl shadow-md ${
                            msg.type === 'user'
                              ? 'bg-matcha-500 text-zinc-950 rounded-br-none'
                              : msg.type === 'assistant'
                              ? 'bg-zinc-800 text-zinc-100 rounded-bl-none border border-zinc-700'
                              : msg.type === 'system'
                              ? 'bg-yellow-500/10 text-yellow-400 text-sm border border-yellow-500/20 text-center mx-auto'
                              : 'bg-blue-500/10 text-blue-400 text-sm border border-blue-500/20 text-center mx-auto'
                          }`}
                        >
                          {msg.type === 'system' || msg.type === 'status' ? (
                            <span className="text-xs uppercase font-bold mr-2 opacity-75">
                              {msg.type}:
                            </span>
                          ) : null}
                          {msg.content}
                        </div>
                      </div>
                    ))}
                    <div ref={messagesEndRef} />
                  </div>
                )}
              </CardContent>
            </Card>
          </>
        )}
      </main>
    </div>
  );
}
