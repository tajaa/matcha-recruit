import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Card, CardContent } from '../components';
import { useAudioInterview } from '../hooks/useAudioInterview';
import { companies, interviews } from '../api/client';
import type { Company, InterviewType } from '../types';

export function TestBot() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<InterviewType>('culture');
  const [companiesList, setCompaniesList] = useState<Company[]>([]);
  const [selectedCompany, setSelectedCompany] = useState<string>('');
  const [interviewId, setInterviewId] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const {
    isConnected,
    isRecording,
    messages,
    connect,
    disconnect,
    startRecording,
    stopRecording,
  } = useAudioInterview(interviewId || '');

  // Load companies on mount
  useEffect(() => {
    loadCompanies();
  }, []);

  // Auto-scroll messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const loadCompanies = async () => {
    try {
      const list = await companies.list();
      setCompaniesList(list);
      // Auto-select "test" company if it exists
      const testCompany = list.find(c => c.name.toLowerCase() === 'test');
      if (testCompany) {
        setSelectedCompany(testCompany.id);
      } else if (list.length > 0) {
        setSelectedCompany(list[0].id);
      }
    } catch (err) {
      console.error('Failed to load companies:', err);
    }
  };

  const handleStartSession = async () => {
    if (!selectedCompany) return;

    setIsCreating(true);
    setError(null);

    try {
      const result = await interviews.create(selectedCompany, {
        interviewer_name: mode === 'culture' ? 'Test HR Rep' : undefined,
        interviewer_role: mode === 'culture' ? 'HR Director' : undefined,
        interview_type: mode,
      });
      setInterviewId(result.interview_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create interview session');
    } finally {
      setIsCreating(false);
    }
  };

  const handleEndSession = () => {
    disconnect();
    // Navigate to analysis page
    if (interviewId) {
      navigate(`/app/test-bot/analysis/${interviewId}`);
    }
    setInterviewId(null);
  };

  const handleReset = () => {
    disconnect();
    setInterviewId(null);
    setError(null);
  };

  const selectedCompanyName = companiesList.find(c => c.id === selectedCompany)?.name || 'Unknown';

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-white tracking-tight flex items-center gap-3">
          <svg className="w-8 h-8 text-violet-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
          Test Bot
        </h1>
        <p className="text-zinc-400 mt-1">Test the AI interview agents</p>
      </div>

      {!interviewId ? (
        <>
          {/* Mode Selection */}
          <Card>
            <CardContent className="p-6">
              <h2 className="text-lg font-semibold text-zinc-100 mb-4">Select Interview Mode</h2>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                {/* Culture Interview */}
                <button
                  onClick={() => setMode('culture')}
                  className={`p-5 rounded-xl border-2 text-left transition-all ${
                    mode === 'culture'
                      ? 'border-matcha-500 bg-matcha-500/10'
                      : 'border-zinc-800 hover:border-zinc-700 bg-zinc-900/50'
                  }`}
                >
                  <div className="flex items-center gap-3 mb-3">
                    <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                      mode === 'culture' ? 'bg-matcha-500/20 text-matcha-400' : 'bg-zinc-800 text-zinc-500'
                    }`}>
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                      </svg>
                    </div>
                    <div>
                      <h3 className={`font-semibold ${mode === 'culture' ? 'text-matcha-400' : 'text-zinc-300'}`}>
                        Culture Interview
                      </h3>
                      <p className="text-xs text-zinc-500">Test as HR representative</p>
                    </div>
                  </div>
                  <p className="text-sm text-zinc-400">
                    The AI will interview you as an HR rep describing your company's culture and values.
                  </p>
                </button>

                {/* Screening Interview */}
                <button
                  onClick={() => setMode('screening')}
                  className={`p-5 rounded-xl border-2 text-left transition-all ${
                    mode === 'screening'
                      ? 'border-orange-500 bg-orange-500/10'
                      : 'border-zinc-800 hover:border-zinc-700 bg-zinc-900/50'
                  }`}
                >
                  <div className="flex items-center gap-3 mb-3">
                    <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                      mode === 'screening' ? 'bg-orange-500/20 text-orange-400' : 'bg-zinc-800 text-zinc-500'
                    }`}>
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    </div>
                    <div>
                      <h3 className={`font-semibold ${mode === 'screening' ? 'text-orange-400' : 'text-zinc-300'}`}>
                        Screening Interview
                      </h3>
                      <p className="text-xs text-zinc-500">First-round filtering</p>
                    </div>
                  </div>
                  <p className="text-sm text-zinc-400">
                    Quick assessment of communication, engagement, critical thinking, and professionalism.
                  </p>
                </button>

                {/* Candidate Interview */}
                <button
                  onClick={() => setMode('candidate')}
                  className={`p-5 rounded-xl border-2 text-left transition-all ${
                    mode === 'candidate'
                      ? 'border-violet-500 bg-violet-500/10'
                      : 'border-zinc-800 hover:border-zinc-700 bg-zinc-900/50'
                  }`}
                >
                  <div className="flex items-center gap-3 mb-3">
                    <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                      mode === 'candidate' ? 'bg-violet-500/20 text-violet-400' : 'bg-zinc-800 text-zinc-500'
                    }`}>
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                      </svg>
                    </div>
                    <div>
                      <h3 className={`font-semibold ${mode === 'candidate' ? 'text-violet-400' : 'text-zinc-300'}`}>
                        Culture Fit Interview
                      </h3>
                      <p className="text-xs text-zinc-500">Requires culture profile</p>
                    </div>
                  </div>
                  <p className="text-sm text-zinc-400">
                    Deep dive into work preferences and values, assessed against company culture profile.
                  </p>
                </button>
              </div>

              {/* Company Selection */}
              <div className="mb-6 p-4 bg-zinc-800/30 rounded-lg border border-zinc-700">
                <label className="block text-sm font-medium text-zinc-400 mb-2">Select Company</label>
                <select
                  value={selectedCompany}
                  onChange={(e) => setSelectedCompany(e.target.value)}
                  className="w-full px-4 py-3 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 focus:ring-2 focus:ring-matcha-500 focus:border-transparent outline-none text-lg font-medium"
                >
                  {companiesList.map((company) => (
                    <option key={company.id} value={company.id}>
                      {company.name} {company.culture_profile ? '(has culture profile)' : ''}
                    </option>
                  ))}
                </select>
                {selectedCompanyName && (
                  <p className="text-sm text-matcha-400 mt-2 font-medium">
                    Testing with: {selectedCompanyName}
                  </p>
                )}
                {mode === 'candidate' && (
                  <p className="text-xs text-zinc-500 mt-1">
                    The candidate interview will use this company's culture profile (if available) to understand fit.
                  </p>
                )}
              </div>

              {error && (
                <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
                  {error}
                </div>
              )}

              <Button
                onClick={handleStartSession}
                disabled={!selectedCompany || isCreating}
                className="w-full py-4 text-lg"
              >
                {isCreating ? (
                  <>
                    <svg className="w-5 h-5 animate-spin mr-2" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    Creating Session...
                  </>
                ) : (
                  <>
                    <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    Start {mode === 'culture' ? 'Culture' : mode === 'screening' ? 'Screening' : 'Culture Fit'} Interview
                  </>
                )}
              </Button>
            </CardContent>
          </Card>

          {/* Mode Description */}
          <div className={`p-5 rounded-xl border ${
            mode === 'culture'
              ? 'bg-matcha-500/5 border-matcha-500/10'
              : mode === 'screening'
              ? 'bg-orange-500/5 border-orange-500/10'
              : 'bg-violet-500/5 border-violet-500/10'
          }`}>
            <h3 className={`font-semibold mb-3 flex items-center gap-2 ${
              mode === 'culture' ? 'text-matcha-400' : mode === 'screening' ? 'text-orange-400' : 'text-violet-400'
            }`}>
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              {mode === 'culture' ? 'Culture Interview Tips' : mode === 'screening' ? 'Screening Interview Tips' : 'Culture Fit Interview Tips'}
            </h3>
            <ul className="text-sm text-zinc-400 space-y-2 ml-1">
              {mode === 'culture' ? (
                <>
                  <li className="flex items-start gap-2">
                    <span className="mt-1.5 w-1 h-1 rounded-full bg-matcha-500 flex-shrink-0"></span>
                    Pretend you're an HR rep or team lead at a company
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="mt-1.5 w-1 h-1 rounded-full bg-matcha-500 flex-shrink-0"></span>
                    Describe your company's culture, values, and work style
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="mt-1.5 w-1 h-1 rounded-full bg-matcha-500 flex-shrink-0"></span>
                    Share how teams collaborate and make decisions
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="mt-1.5 w-1 h-1 rounded-full bg-matcha-500 flex-shrink-0"></span>
                    This helps build the company's culture profile
                  </li>
                </>
              ) : mode === 'screening' ? (
                <>
                  <li className="flex items-start gap-2">
                    <span className="mt-1.5 w-1 h-1 rounded-full bg-orange-500 flex-shrink-0"></span>
                    Respond as yourself - a job candidate
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="mt-1.5 w-1 h-1 rounded-full bg-orange-500 flex-shrink-0"></span>
                    Be clear and concise in your responses
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="mt-1.5 w-1 h-1 rounded-full bg-orange-500 flex-shrink-0"></span>
                    Show enthusiasm and engagement
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="mt-1.5 w-1 h-1 rounded-full bg-orange-500 flex-shrink-0"></span>
                    Give specific examples when possible
                  </li>
                </>
              ) : (
                <>
                  <li className="flex items-start gap-2">
                    <span className="mt-1.5 w-1 h-1 rounded-full bg-violet-500 flex-shrink-0"></span>
                    Respond as yourself - a job candidate
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="mt-1.5 w-1 h-1 rounded-full bg-violet-500 flex-shrink-0"></span>
                    Share your work style preferences honestly
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="mt-1.5 w-1 h-1 rounded-full bg-violet-500 flex-shrink-0"></span>
                    Describe what you're looking for in a role
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="mt-1.5 w-1 h-1 rounded-full bg-violet-500 flex-shrink-0"></span>
                    This tests how well the AI assesses culture fit
                  </li>
                </>
              )}
            </ul>
          </div>
        </>
      ) : (
        <>
          {/* Active Interview Session */}
          <Card>
            <CardContent className="p-6">
              {/* Session Info */}
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                  <span className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm font-medium ${
                    mode === 'culture'
                      ? 'bg-matcha-500/15 text-matcha-400'
                      : mode === 'screening'
                      ? 'bg-orange-500/15 text-orange-400'
                      : 'bg-violet-500/15 text-violet-400'
                  }`}>
                    {mode === 'culture' ? (
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                      </svg>
                    ) : mode === 'screening' ? (
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    ) : (
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                      </svg>
                    )}
                    {mode === 'culture' ? 'Culture Interview' : mode === 'screening' ? 'Screening Interview' : 'Culture Fit Interview'}
                  </span>
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium bg-zinc-800 text-zinc-200 border border-zinc-700">
                    <svg className="w-4 h-4 text-zinc-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                    </svg>
                    {selectedCompanyName}
                  </span>
                </div>
                <button
                  onClick={handleReset}
                  className="text-zinc-500 hover:text-zinc-300 text-sm transition-colors"
                >
                  Reset
                </button>
              </div>

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
                    <Button onClick={handleEndSession} variant="secondary" className="px-8">
                      End
                    </Button>
                  </>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Conversation */}
          <Card>
            <CardContent className="h-[500px] overflow-y-auto custom-scrollbar p-6">
              {messages.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-zinc-500 space-y-4">
                  <div className="w-16 h-16 rounded-full bg-zinc-800 flex items-center justify-center">
                    <svg className="w-8 h-8 text-zinc-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                    </svg>
                  </div>
                  <p>Connect and start speaking to begin the interview</p>
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
    </div>
  );
}

export default TestBot;
