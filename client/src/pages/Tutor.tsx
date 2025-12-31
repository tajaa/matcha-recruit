import { useState, useEffect, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Button, Card, CardContent } from '../components';
import { tutor } from '../api/client';
import { useAudioInterview } from '../hooks/useAudioInterview';
import { useAuth } from '../context/AuthContext';

type TutorMode = 'interview_prep' | 'language_test';
type Language = 'en' | 'es';
type Duration = 2 | 5 | 8;
type InterviewRole = 'VP of People' | 'CTO' | 'Head of Marketing' | 'Junior Engineer';

const INTERVIEW_ROLES: { value: InterviewRole; label: string; description: string }[] = [
  { value: 'Junior Engineer', label: 'Junior Engineer', description: 'Entry-level technical role' },
  { value: 'CTO', label: 'CTO', description: 'Technical leadership' },
  { value: 'VP of People', label: 'VP of People', description: 'HR leadership' },
  { value: 'Head of Marketing', label: 'Head of Marketing', description: 'Marketing leadership' },
];

export function Tutor() {
  const navigate = useNavigate();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { user, interviewPrepTokens, refreshUser } = useAuth();
  const isCandidate = user?.role === 'candidate';

  // Mode selection state
  const [selectedMode, setSelectedMode] = useState<TutorMode | null>(null);
  const [selectedLanguage, setSelectedLanguage] = useState<Language>('es');
  const [selectedDuration, setSelectedDuration] = useState<Duration>(2);
  const [selectedInterviewDuration, setSelectedInterviewDuration] = useState<Duration>(5);
  const [selectedRole, setSelectedRole] = useState<InterviewRole>('Junior Engineer');

  // Session state
  const [interviewId, setInterviewId] = useState<string | null>(null);
  const [maxSessionDurationMs, setMaxSessionDurationMs] = useState<number | undefined>(undefined);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [completed, setCompleted] = useState(false);

  // Audio interview hook with server-configured session limit
  const {
    isConnected,
    isRecording,
    messages,
    sessionTimeRemaining,
    connect,
    disconnect,
    startRecording,
    stopRecording,
  } = useAudioInterview(interviewId || '', { maxSessionDurationMs });

  // Scroll to bottom of messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Start a tutor session
  const handleStartSession = async (mode: TutorMode, language?: Language, duration?: Duration, role?: InterviewRole) => {
    setStarting(true);
    setError(null);
    try {
      const result = await tutor.createSession({
        mode,
        language: mode === 'language_test' ? language : undefined,
        duration_minutes: duration,
        interview_role: mode === 'interview_prep' ? role : undefined,
      });
      setInterviewId(result.interview_id);
      setMaxSessionDurationMs(result.max_session_duration_seconds * 1000);
      setSelectedMode(mode);
      if (language) setSelectedLanguage(language);
      if (duration) setSelectedDuration(duration);
      if (role) setSelectedRole(role);
      // Refresh user to update token count
      if (isCandidate) {
        refreshUser();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start session');
    } finally {
      setStarting(false);
    }
  };

  // End the session
  const handleEnd = () => {
    disconnect();
    setCompleted(true);
  };

  // Reset to mode selection
  const handleReset = () => {
    setInterviewId(null);
    setSelectedMode(null);
    setCompleted(false);
    setError(null);
  };

  // Format time remaining
  const formatTime = (seconds: number | null) => {
    if (seconds === null) return '';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Completed state
  if (completed) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-white tracking-tight">Session Complete</h1>
            <p className="text-zinc-500 mt-1">Great practice session!</p>
          </div>
        </div>

        <Card>
          <CardContent className="py-12 text-center">
            <div className="w-16 h-16 mx-auto mb-6 rounded-full bg-matcha-500/20 flex items-center justify-center">
              <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h2 className="text-xl font-semibold text-white mb-2">
              {selectedMode === 'interview_prep' ? `${selectedRole} Interview Practice Complete` : 'Language Practice Complete'}
            </h2>
            <p className="text-zinc-400 mb-6">
              {selectedMode === 'interview_prep'
                ? `Keep practicing to ace your ${selectedRole} interview!`
                : `Great job practicing ${selectedLanguage === 'es' ? 'Spanish' : 'English'}!`}
            </p>
            <p className="text-zinc-500 text-sm mb-6">
              Your session is being analyzed. View your detailed feedback below.
            </p>
            <div className="flex gap-4 justify-center">
              <Button onClick={() => navigate(`/app/tutor-metrics/${interviewId}`)}>
                View Your Analysis
              </Button>
              <Button variant="secondary" onClick={handleReset}>
                Start Another Session
              </Button>
            </div>
            <p className="text-zinc-500 text-sm mt-6">
              <Link to="/app/tutor-metrics" className="text-matcha-400 hover:text-matcha-300 underline">
                View all your sessions
              </Link>
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Active session
  if (interviewId) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-white tracking-tight">
              {selectedMode === 'interview_prep' ? 'Interview Practice' : 'Language Practice'}
            </h1>
            <p className="text-zinc-500 mt-1">
              {selectedMode === 'interview_prep'
                ? `Practicing for ${selectedRole} interview`
                : `Practicing ${selectedLanguage === 'es' ? 'Spanish' : 'English'} conversation`}
            </p>
          </div>
          {sessionTimeRemaining !== null && (
            <div className="text-sm text-zinc-500">
              Time: <span className="text-zinc-300 font-medium">{formatTime(sessionTimeRemaining)}</span>
            </div>
          )}
        </div>

        {/* Controls */}
        <Card>
          <CardContent>
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

            <div className="flex gap-4">
              {!isConnected ? (
                <Button onClick={connect} className="flex-1 py-4 text-lg">
                  Connect to {selectedMode === 'interview_prep' ? 'Coach' : 'Tutor'}
                </Button>
              ) : (
                <>
                  {!isRecording ? (
                    <Button onClick={startRecording} className="flex-1 py-4 text-lg ">
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
                    className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}
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
      </div>
    );
  }

  // Mode selection
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight">
            {isCandidate ? 'Interview Prep' : 'Tutor'}
          </h1>
          <p className="text-zinc-500 mt-1">
            {isCandidate ? 'Practice your interview skills' : 'Practice your interview skills or language proficiency'}
          </p>
        </div>
        {isCandidate && (
          <div className="flex items-center gap-2 px-4 py-2 bg-zinc-900 border border-zinc-800 rounded-lg">
            <span className="text-xs text-zinc-500 uppercase tracking-wide">Tokens:</span>
            <span className={`text-lg font-mono font-bold ${interviewPrepTokens > 0 ? 'text-white' : 'text-red-400'}`}>
              {interviewPrepTokens}
            </span>
          </div>
        )}
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 text-red-400">
          {error}
        </div>
      )}

      {isCandidate && interviewPrepTokens === 0 && (
        <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-4 text-amber-400">
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <span>You have no tokens remaining. Contact support to get more tokens.</span>
          </div>
        </div>
      )}

      <div className={`grid gap-6 ${isCandidate ? 'grid-cols-1 max-w-xl' : 'grid-cols-1 md:grid-cols-2'}`}>
        {/* Interview Prep Card */}
        <Card className="overflow-hidden">
          <div className="h-2 bg-gradient-to-r from-matcha-500 to-matcha-400" />
          <CardContent className="pt-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-12 h-12 rounded-lg bg-matcha-500/20 flex items-center justify-center">
                <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <div>
                <h3 className="text-lg font-semibold text-white">Interview Prep</h3>
                <p className="text-sm text-zinc-500">Practice for your target role</p>
              </div>
            </div>

            <p className="text-zinc-400 text-sm mb-4">
              Practice role-specific interview questions with tailored feedback.
            </p>

            <div className="mb-4">
              <label className="block text-xs text-zinc-500 mb-2">Interviewing for</label>
              <div className="grid grid-cols-2 gap-2">
                {INTERVIEW_ROLES.map((role) => (
                  <button
                    key={role.value}
                    onClick={() => setSelectedRole(role.value)}
                    className={`py-2 px-3 rounded-lg border transition-colors text-left ${
                      selectedRole === role.value
                        ? 'bg-matcha-500/20 border-matcha-500 text-matcha-400'
                        : 'bg-zinc-900 border-zinc-700 text-zinc-400 hover:border-zinc-600'
                    }`}
                  >
                    <div className="text-sm font-medium">{role.label}</div>
                    <div className="text-xs text-zinc-500">{role.description}</div>
                  </button>
                ))}
              </div>
            </div>

            <div className="mb-6">
              <label className="block text-xs text-zinc-500 mb-2">Session Duration</label>
              <div className="flex gap-2">
                {([5, 8] as const).map((d) => (
                  <button
                    key={d}
                    onClick={() => setSelectedInterviewDuration(d)}
                    className={`flex-1 py-2 px-4 rounded-lg border transition-colors ${
                      selectedInterviewDuration === d
                        ? 'bg-matcha-500/20 border-matcha-500 text-matcha-400'
                        : 'bg-zinc-900 border-zinc-700 text-zinc-400 hover:border-zinc-600'
                    }`}
                  >
                    {d} min
                  </button>
                ))}
              </div>
            </div>

            <Button
              onClick={() => handleStartSession('interview_prep', undefined, selectedInterviewDuration, selectedRole)}
              disabled={starting || (isCandidate && interviewPrepTokens === 0)}
              className="w-full"
            >
              {starting ? 'Starting...' : `Practice ${selectedRole} Interview (${selectedInterviewDuration} min)`}
            </Button>
            {isCandidate && (
              <p className="text-xs text-zinc-500 text-center mt-2">
                This will use 1 token
              </p>
            )}
          </CardContent>
        </Card>

        {/* Language Test Card - Admin only */}
        {!isCandidate && (
        <Card className="overflow-hidden">
          <div className="h-2 bg-gradient-to-r from-blue-500 to-blue-400" />
          <CardContent className="pt-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-12 h-12 rounded-lg bg-blue-500/20 flex items-center justify-center">
                <svg className="w-6 h-6 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129" />
                </svg>
              </div>
              <div>
                <h3 className="text-lg font-semibold text-white">Language Test</h3>
                <p className="text-sm text-zinc-500">Practice conversation</p>
              </div>
            </div>

            <p className="text-zinc-400 text-sm mb-6">
              Have a natural conversation to practice and improve your language skills.
              Get gentle corrections and vocabulary suggestions.
            </p>

            <div className="mb-4">
              <label className="block text-xs text-zinc-500 mb-2">Select Language</label>
              <div className="flex gap-2">
                <button
                  onClick={() => setSelectedLanguage('en')}
                  className={`flex-1 py-2 px-4 rounded-lg border transition-colors ${
                    selectedLanguage === 'en'
                      ? 'bg-blue-500/20 border-blue-500 text-blue-400'
                      : 'bg-zinc-900 border-zinc-700 text-zinc-400 hover:border-zinc-600'
                  }`}
                >
                  English
                </button>
                <button
                  onClick={() => setSelectedLanguage('es')}
                  className={`flex-1 py-2 px-4 rounded-lg border transition-colors ${
                    selectedLanguage === 'es'
                      ? 'bg-blue-500/20 border-blue-500 text-blue-400'
                      : 'bg-zinc-900 border-zinc-700 text-zinc-400 hover:border-zinc-600'
                  }`}
                >
                  Spanish
                </button>
              </div>
            </div>

            <div className="mb-6">
              <label className="block text-xs text-zinc-500 mb-2">Session Duration</label>
              <div className="flex gap-2">
                <button
                  onClick={() => setSelectedDuration(2)}
                  className={`flex-1 py-2 px-4 rounded-lg border transition-colors ${
                    selectedDuration === 2
                      ? 'bg-blue-500/20 border-blue-500 text-blue-400'
                      : 'bg-zinc-900 border-zinc-700 text-zinc-400 hover:border-zinc-600'
                  }`}
                >
                  2 min
                </button>
                <button
                  onClick={() => setSelectedDuration(8)}
                  className={`flex-1 py-2 px-4 rounded-lg border transition-colors ${
                    selectedDuration === 8
                      ? 'bg-blue-500/20 border-blue-500 text-blue-400'
                      : 'bg-zinc-900 border-zinc-700 text-zinc-400 hover:border-zinc-600'
                  }`}
                >
                  8 min
                </button>
              </div>
            </div>

            <Button
              onClick={() => handleStartSession('language_test', selectedLanguage, selectedDuration)}
              disabled={starting}
              variant="secondary"
              className="w-full border-blue-500/30 hover:bg-blue-500/10"
            >
              {starting ? 'Starting...' : `Practice ${selectedLanguage === 'es' ? 'Spanish' : 'English'} (${selectedDuration} min)`}
            </Button>
          </CardContent>
        </Card>
        )}
      </div>

      {/* Tips */}
      <Card>
        <CardContent>
          <h3 className="text-sm font-medium text-zinc-400 mb-3">Tips for a good session</h3>
          <ul className="text-sm text-zinc-500 space-y-2">
            <li className="flex items-start gap-2">
              <span className="mt-1.5 w-1 h-1 rounded-full bg-zinc-600 flex-shrink-0" />
              Find a quiet place with minimal background noise
            </li>
            <li className="flex items-start gap-2">
              <span className="mt-1.5 w-1 h-1 rounded-full bg-zinc-600 flex-shrink-0" />
              Use headphones for the best audio quality
            </li>
            <li className="flex items-start gap-2">
              <span className="mt-1.5 w-1 h-1 rounded-full bg-zinc-600 flex-shrink-0" />
              Speak naturally and take your time with responses
            </li>
            <li className="flex items-start gap-2">
              <span className="mt-1.5 w-1 h-1 rounded-full bg-zinc-600 flex-shrink-0" />
              Choose 2 min for quick practice or 8 min for deeper conversation
            </li>
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}

export default Tutor;
