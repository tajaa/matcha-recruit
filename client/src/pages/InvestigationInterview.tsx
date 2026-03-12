import { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { Button, Card, CardContent } from '../components';
import { investigationInvite } from '../api/client';
import type { InvestigationInviteInfo } from '../types';
import { useAudioInterview } from '../hooks/useAudioInterview';

export function InvestigationInterview() {
  const { token } = useParams<{ token: string }>();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [info, setInfo] = useState<InvestigationInviteInfo | null>(null);
  const [interviewId, setInterviewId] = useState<string | null>(null);
  const [wsAuthToken, setWsAuthToken] = useState<string | null>(null);
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
  } = useAudioInterview(interviewId || '', { wsAuthToken });

  // Scroll to bottom of messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Load invite info
  useEffect(() => {
    const loadInfo = async () => {
      if (!token) return;
      try {
        const data = await investigationInvite.getInfo(token);
        setInfo(data);

        // Check status
        if (data.status === 'completed' || data.status === 'analyzed') {
          setCompleted(true);
        } else if (data.status === 'cancelled') {
          setError('This interview invitation has been cancelled.');
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load');
      } finally {
        setLoading(false);
      }
    };
    loadInfo();
  }, [token]);

  // Start the investigation interview
  const handleStartInterview = async () => {
    if (!token) return;
    setStarting(true);
    try {
      const result = await investigationInvite.start(token);
      setInterviewId(result.interview_id);
      setWsAuthToken(result.ws_auth_token || null);
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

  const formatRole = (role: string) => {
    return role.charAt(0).toUpperCase() + role.slice(1);
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
            <div className="w-2 h-2 rounded-full bg-matcha-500 animate-pulse" />
            <span className="text-xs tracking-[0.25em] uppercase text-white font-medium">
              Matcha
            </span>
          </div>
        </header>

        <main className="max-w-2xl mx-auto px-4 py-12">
          <div className="text-center">
            <div className="w-16 h-16 mx-auto mb-6 rounded-full bg-matcha-500/20 flex items-center justify-center">
              <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold text-white mb-4">Interview Complete</h1>
            <p className="text-zinc-400 mb-6">
              Thank you for your participation. Your input helps ensure a thorough and fair investigation.
            </p>
            {info && (
              <Card>
                <CardContent className="p-6">
                  <p className="text-sm text-zinc-500">
                    Company: <span className="text-zinc-300">{info.company_name}</span>
                  </p>
                  <p className="text-sm text-zinc-500 mt-2">
                    Role: <span className="text-zinc-300">{formatRole(info.interviewee_role)}</span>
                  </p>
                </CardContent>
              </Card>
            )}
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
            <div className="w-2 h-2 rounded-full bg-matcha-500 animate-pulse" />
            <span className="text-xs tracking-[0.25em] uppercase text-white font-medium">
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
                Investigation Interview
              </h1>
              <p className="text-white">{info?.company_name}</p>
            </div>
            <div className="text-right text-sm">
              {info?.interviewee_role && (
                <p className="text-zinc-400">{formatRole(info.interviewee_role)}</p>
              )}
              {info?.interviewee_name && (
                <p className="text-zinc-300">{info.interviewee_name}</p>
              )}
            </div>
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
            <h2 className="text-2xl font-bold text-white mb-4">Ready to begin?</h2>
            <p className="text-zinc-400 mb-8 max-w-md mx-auto">
              You'll have a confidential conversation with our AI interviewer as part of this workplace investigation.
              Please speak honestly and to the best of your recollection.
            </p>
            <Button onClick={handleStartInterview} disabled={starting} className="px-8 py-3 text-lg">
              {starting ? 'Starting...' : 'Begin Interview'}
            </Button>

            <div className="mt-8 p-5 bg-matcha-500/5 rounded-xl border border-zinc-700 text-left max-w-md mx-auto">
              <h3 className="font-semibold text-white mb-3 flex items-center gap-2">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                Before you begin
              </h3>
              <ul className="text-sm text-zinc-400 space-y-2 ml-1">
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 w-1 h-1 rounded-full bg-matcha-500 flex-shrink-0"></span>
                  Find a quiet, private space with minimal background noise
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 w-1 h-1 rounded-full bg-matcha-500 flex-shrink-0"></span>
                  Use headphones for best audio quality
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 w-1 h-1 rounded-full bg-matcha-500 flex-shrink-0"></span>
                  This conversation is confidential within the scope of the investigation
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 w-1 h-1 rounded-full bg-matcha-500 flex-shrink-0"></span>
                  Speak honestly and to the best of your recollection
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 w-1 h-1 rounded-full bg-matcha-500 flex-shrink-0"></span>
                  The interview takes about 10–15 minutes
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
                        isConnected ? 'bg-matcha-500 text-white' : 'bg-zinc-600 text-zinc-600'
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
                        <Button onClick={startRecording} className="flex-1 py-4 text-lg">
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

export default InvestigationInterview;
