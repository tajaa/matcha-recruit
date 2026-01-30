import { useState, useEffect, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Button } from '../components/Button';
import { tutor } from '../api/client';
import { useAudioInterview } from '../hooks/useAudioInterview';
import { useAuth } from '../context/AuthContext';
import { Mic, Square, Clock, Award, Users, Globe, Play, CheckCircle2 } from 'lucide-react';

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
  const { user, interviewPrepTokens, allowedInterviewRoles, refreshUser } = useAuth();
  const isCandidate = user?.role === 'candidate';

  // Filter roles for candidates based on admin-assigned allowed roles
  const availableRoles = isCandidate
    ? INTERVIEW_ROLES.filter(role => allowedInterviewRoles.includes(role.value))
    : INTERVIEW_ROLES;

  // Mode selection state
  const [selectedMode, setSelectedMode] = useState<TutorMode | null>(null);
  const [selectedLanguage, setSelectedLanguage] = useState<Language>('es');
  const [selectedDuration, setSelectedDuration] = useState<Duration>(2);
  const [selectedInterviewDuration, setSelectedInterviewDuration] = useState<Duration>(5);
  const [selectedRole, setSelectedRole] = useState<InterviewRole>('Junior Engineer');

  // Set default selected role to first available for candidates
  useEffect(() => {
    if (isCandidate && availableRoles.length > 0 && !availableRoles.some(r => r.value === selectedRole)) {
      setSelectedRole(availableRoles[0].value);
    }
  }, [isCandidate, availableRoles, selectedRole]);

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
    cancelSession,
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

  // End the session (cancel — skip analysis, return to mode selection)
  const handleEnd = () => {
    cancelSession();
    handleReset();
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
      <div className="max-w-2xl mx-auto space-y-8 py-12">
        <div className="text-center space-y-6">
          <div className="w-20 h-20 mx-auto rounded-full bg-emerald-500/20 border border-emerald-500/50 flex items-center justify-center">
            <CheckCircle2 className="w-10 h-10 text-emerald-400" />
          </div>
          <div>
            <h1 className="text-4xl font-bold text-white tracking-tight uppercase">Session Complete</h1>
            <p className="text-zinc-400 mt-2 font-mono">Analysis in progress...</p>
          </div>
        </div>

        <div className="bg-zinc-900 border border-zinc-800 p-8 text-center">
          <h2 className="text-lg font-bold text-white uppercase tracking-wider mb-4">
            {selectedMode === 'interview_prep' ? `${selectedRole} Simulation` : 'Language Practice'}
          </h2>
          <p className="text-sm text-zinc-400 mb-8 max-w-md mx-auto leading-relaxed">
            {selectedMode === 'interview_prep'
              ? `Your responses for the ${selectedRole} role have been recorded. Our system is generating detailed feedback on your delivery and content.`
              : `Great job practicing ${selectedLanguage === 'es' ? 'Spanish' : 'English'}! Review your grammar and fluency scores below.`}
          </p>
          
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Button 
               onClick={() => navigate(`/app/admin/tutor-metrics/${interviewId}`)}
               className="bg-white text-black hover:bg-zinc-200 font-bold uppercase tracking-wider"
            >
              View Analysis
            </Button>
            <Button 
               variant="secondary" 
               onClick={handleReset}
               className="bg-transparent border border-zinc-700 text-zinc-300 hover:text-white hover:bg-zinc-800 font-bold uppercase tracking-wider"
            >
              Start New Session
            </Button>
          </div>
        </div>
        
        <div className="text-center">
           <Link to="/app/admin/tutor-metrics" className="text-xs text-zinc-500 hover:text-white uppercase tracking-widest border-b border-transparent hover:border-white pb-0.5 transition-all">
             View All Sessions
           </Link>
        </div>
      </div>
    );
  }

  // Active session
  if (interviewId) {
    return (
      <div className="max-w-4xl mx-auto space-y-8">
        <div className="flex items-center justify-between border-b border-white/10 pb-6">
          <div>
            <div className="flex items-center gap-3 mb-1">
               <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-500 animate-pulse' : 'bg-red-500'}`} />
               <h1 className="text-xl font-bold text-white uppercase tracking-wider">
                 {selectedMode === 'interview_prep' ? 'Interview Simulation' : 'Language Lab'}
               </h1>
            </div>
            <p className="text-xs text-zinc-500 font-mono ml-5">
              {selectedMode === 'interview_prep'
                ? `ROLE: ${selectedRole}`
                : `TARGET: ${selectedLanguage === 'es' ? 'Spanish' : 'English'}`}
            </p>
          </div>
          {sessionTimeRemaining !== null && (
            <div className="flex items-center gap-2 px-4 py-2 bg-zinc-900 border border-zinc-800 rounded-sm">
              <Clock className="w-4 h-4 text-zinc-500" />
              <span className={`font-mono text-lg font-bold ${sessionTimeRemaining < 60 ? 'text-red-500 animate-pulse' : 'text-white'}`}>
                 {formatTime(sessionTimeRemaining)}
              </span>
            </div>
          )}
        </div>

        {/* Interface */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 h-[600px]">
           {/* Chat Feed */}
           <div className="lg:col-span-2 bg-zinc-950 border border-white/10 flex flex-col">
              <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-black/40">
                 {messages.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center text-zinc-600 space-y-4 opacity-50">
                       <Mic size={48} />
                       <p className="uppercase tracking-widest text-xs">Waiting for audio input...</p>
                    </div>
                 ) : (
                    messages.map((msg, idx) => (
                       <div key={idx} className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}>
                          <div className={`max-w-[85%] p-4 border ${
                             msg.type === 'user'
                                ? 'bg-zinc-900 border-zinc-700 text-white'
                                : msg.type === 'assistant'
                                   ? 'bg-zinc-950 border-emerald-500/30 text-emerald-100 shadow-[0_0_15px_rgba(16,185,129,0.1)]'
                                   : 'bg-transparent border-dashed border-zinc-800 text-zinc-500 text-xs w-full text-center'
                          }`}>
                             {msg.type !== 'system' && (
                                <div className={`text-[9px] uppercase tracking-widest mb-2 ${msg.type === 'user' ? 'text-zinc-500' : 'text-emerald-500'}`}>
                                   {msg.type === 'user' ? 'Candidate' : 'AI Interviewer'}
                                </div>
                             )}
                             <p className="leading-relaxed">{msg.content}</p>
                          </div>
                       </div>
                    ))
                 )}
                 <div ref={messagesEndRef} />
              </div>

              {/* Controls */}
              <div className="p-6 bg-zinc-900 border-t border-white/10">
                 {!isConnected ? (
                    <Button onClick={connect} className="w-full py-4 text-sm font-bold bg-white text-black hover:bg-zinc-200 uppercase tracking-widest">
                       Initialize Connection
                    </Button>
                 ) : (
                    <div className="flex gap-4">
                       {!isRecording ? (
                          <Button onClick={startRecording} className="flex-1 py-4 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-widest flex items-center justify-center gap-2">
                             <Mic size={16} /> Start Speaking
                          </Button>
                       ) : (
                          <Button onClick={stopRecording} className="flex-1 py-4 bg-red-600 hover:bg-red-700 text-white text-xs font-bold uppercase tracking-widest flex items-center justify-center gap-2 animate-pulse">
                             <Square size={16} /> Stop Speaking
                          </Button>
                       )}
                       <Button onClick={handleEnd} variant="secondary" className="px-6 bg-zinc-800 border-zinc-700 text-zinc-300 hover:text-white uppercase tracking-widest text-xs font-bold">
                          End
                       </Button>
                    </div>
                 )}
              </div>
           </div>

           {/* Status Panel */}
           <div className="space-y-4">
              <div className="bg-zinc-900 border border-white/10 p-6">
                 <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-wider mb-4 border-b border-zinc-800 pb-2">Session Status</h3>
                 <div className="space-y-4">
                    <div className="flex justify-between items-center">
                       <span className="text-xs text-zinc-400">Connection</span>
                       <span className={`text-xs font-mono uppercase ${isConnected ? 'text-emerald-500' : 'text-zinc-600'}`}>
                          {isConnected ? 'Stable' : 'Offline'}
                       </span>
                    </div>
                    <div className="flex justify-between items-center">
                       <span className="text-xs text-zinc-400">Audio Stream</span>
                       <span className={`text-xs font-mono uppercase ${isRecording ? 'text-red-500 animate-pulse' : 'text-zinc-600'}`}>
                          {isRecording ? 'Active' : 'Idle'}
                       </span>
                    </div>
                    <div className="flex justify-between items-center">
                       <span className="text-xs text-zinc-400">Transcript</span>
                       <span className="text-xs font-mono text-zinc-300">{messages.length} Events</span>
                    </div>
                 </div>
              </div>

              <div className="bg-zinc-900/50 border border-zinc-800 p-6">
                 <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-wider mb-4">Tips</h3>
                 <ul className="text-xs text-zinc-400 space-y-3 leading-relaxed">
                    <li>• Speak clearly and at a moderate pace.</li>
                    <li>• Wait for the AI to finish speaking before responding.</li>
                    <li>• Use specific examples (STAR method) for behavioral questions.</li>
                 </ul>
              </div>
           </div>
        </div>
      </div>
    );
  }

  // Mode selection
  return (
    <div className="max-w-5xl mx-auto space-y-12">
      <div className="flex items-center justify-between border-b border-white/10 pb-8">
        <div>
          <h1 className="text-4xl font-bold text-white tracking-tighter uppercase">
            {isCandidate ? 'Interview Prep' : 'Tutor'}
          </h1>
          <p className="text-zinc-500 mt-2 text-xs font-mono tracking-wide uppercase">
            {isCandidate ? 'AI-Powered Role Simulation' : 'Language & Interview Practice Module'}
          </p>
        </div>
        {isCandidate && (
          <div className="flex items-center gap-3 px-4 py-2 bg-zinc-900 border border-zinc-800">
            <Award className="w-4 h-4 text-amber-500" />
            <div className="flex flex-col items-end">
               <span className={`text-lg font-mono font-bold leading-none ${interviewPrepTokens > 0 ? 'text-white' : 'text-red-500'}`}>
                 {interviewPrepTokens}
               </span>
               <span className="text-[9px] text-zinc-600 uppercase tracking-wider">Tokens Available</span>
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="bg-red-900/20 border border-red-500/30 p-4 text-red-400 text-sm font-mono flex items-center gap-3">
           <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse" />
           {error}
        </div>
      )}

      {isCandidate && interviewPrepTokens === 0 && (
        <div className="bg-amber-900/20 border border-amber-500/30 p-6 text-amber-400">
          <h3 className="font-bold uppercase tracking-wider text-sm mb-2 flex items-center gap-2">
             <Clock className="w-4 h-4" /> Insufficient Tokens
          </h3>
          <p className="text-xs opacity-80 font-mono">You have exhausted your interview preparation tokens. Please contact your administrator to request additional access.</p>
        </div>
      )}

      <div className={`grid gap-8 ${isCandidate ? 'grid-cols-1 max-w-2xl' : 'grid-cols-1 md:grid-cols-2'}`}>
        {/* Interview Prep Card */}
        <div className="bg-zinc-950 border border-white/10 p-8 relative overflow-hidden group">
          <div className="absolute top-0 right-0 p-8 opacity-10 group-hover:opacity-20 transition-opacity">
             <Users className="w-32 h-32 text-white" />
          </div>
          
          <div className="relative z-10">
             <div className="w-12 h-12 bg-white text-black flex items-center justify-center mb-6">
                <Users className="w-6 h-6" />
             </div>
             
             <h2 className="text-xl font-bold text-white uppercase tracking-tight mb-2">Role Simulation</h2>
             <p className="text-zinc-400 text-sm mb-8 max-w-sm">
               Practice role-specific interview questions with an AI coach that adapts to your responses and provides detailed feedback.
             </p>

             <div className="space-y-6">
                <div>
                   <label className="block text-[10px] text-zinc-500 uppercase tracking-wider font-bold mb-2">Target Role</label>
                   {availableRoles.length === 0 ? (
                      <div className="p-4 border border-dashed border-zinc-800 text-center text-xs text-zinc-600 font-mono uppercase">
                         No roles assigned
                      </div>
                   ) : (
                      <div className="grid grid-cols-2 gap-2">
                         {availableRoles.map((role) => (
                            <button
                               key={role.value}
                               onClick={() => setSelectedRole(role.value)}
                               className={`px-3 py-2 text-left border text-xs font-bold uppercase tracking-wider transition-all ${
                                  selectedRole === role.value 
                                     ? 'bg-white text-black border-white' 
                                     : 'bg-zinc-900 text-zinc-500 border-zinc-800 hover:border-zinc-600'
                               }`}
                            >
                               {role.label}
                            </button>
                         ))}
                      </div>
                   )}
                </div>

                <div>
                   <label className="block text-[10px] text-zinc-500 uppercase tracking-wider font-bold mb-2">Duration</label>
                   <div className="flex gap-2">
                      {[5, 8].map((d) => (
                         <button
                            key={d}
                            onClick={() => setSelectedInterviewDuration(d as Duration)}
                            className={`flex-1 py-2 border text-xs font-bold uppercase tracking-wider transition-all ${
                               selectedInterviewDuration === d 
                                  ? 'bg-white text-black border-white' 
                                  : 'bg-zinc-900 text-zinc-500 border-zinc-800 hover:border-zinc-600'
                            }`}
                         >
                            {d} MIN
                         </button>
                      ))}
                   </div>
                </div>

                <Button
                   onClick={() => handleStartSession('interview_prep', undefined, selectedInterviewDuration, selectedRole)}
                   disabled={starting || (isCandidate && interviewPrepTokens === 0) || (isCandidate && availableRoles.length === 0)}
                   className="w-full bg-white text-black hover:bg-zinc-200 font-bold uppercase tracking-widest py-4 rounded-none"
                >
                   {starting ? 'INITIALIZING...' : 'START SIMULATION'}
                </Button>
                
                {isCandidate && (
                   <div className="text-center text-[10px] text-zinc-600 uppercase tracking-wider font-mono">
                      Cost: 1 Token
                   </div>
                )}
             </div>
          </div>
        </div>

        {/* Language Test Card - Admin only */}
        {!isCandidate && (
        <div className="bg-zinc-900/30 border border-zinc-800 p-8 relative overflow-hidden group hover:border-zinc-700 transition-colors">
           <div className="absolute top-0 right-0 p-8 opacity-5 group-hover:opacity-10 transition-opacity">
             <Globe className="w-32 h-32 text-white" />
          </div>

          <div className="relative z-10">
             <div className="w-12 h-12 bg-zinc-800 border border-zinc-700 flex items-center justify-center mb-6 text-zinc-400">
                <Globe className="w-6 h-6" />
             </div>
             
             <h2 className="text-xl font-bold text-white uppercase tracking-tight mb-2">Language Lab</h2>
             <p className="text-zinc-500 text-sm mb-8 max-w-sm">
               Test fluency and grammar in English or Spanish through natural conversation.
             </p>

             <div className="space-y-6">
                <div>
                   <label className="block text-[10px] text-zinc-500 uppercase tracking-wider font-bold mb-2">Language</label>
                   <div className="flex gap-2">
                      <button
                         onClick={() => setSelectedLanguage('en')}
                         className={`flex-1 py-2 border text-xs font-bold uppercase tracking-wider transition-all ${
                            selectedLanguage === 'en' 
                               ? 'bg-zinc-800 text-white border-zinc-600' 
                               : 'bg-zinc-950 text-zinc-500 border-zinc-800 hover:border-zinc-700'
                         }`}
                      >
                         English
                      </button>
                      <button
                         onClick={() => setSelectedLanguage('es')}
                         className={`flex-1 py-2 border text-xs font-bold uppercase tracking-wider transition-all ${
                            selectedLanguage === 'es' 
                               ? 'bg-zinc-800 text-white border-zinc-600' 
                               : 'bg-zinc-950 text-zinc-500 border-zinc-800 hover:border-zinc-700'
                         }`}
                      >
                         Spanish
                      </button>
                   </div>
                </div>

                <div>
                   <label className="block text-[10px] text-zinc-500 uppercase tracking-wider font-bold mb-2">Duration</label>
                   <div className="flex gap-2">
                      {[2, 8].map((d) => (
                         <button
                            key={d}
                            onClick={() => setSelectedDuration(d as Duration)}
                            className={`flex-1 py-2 border text-xs font-bold uppercase tracking-wider transition-all ${
                               selectedDuration === d 
                                  ? 'bg-zinc-800 text-white border-zinc-600' 
                                  : 'bg-zinc-950 text-zinc-500 border-zinc-800 hover:border-zinc-700'
                            }`}
                         >
                            {d} MIN
                         </button>
                      ))}
                   </div>
                </div>

                <Button
                   onClick={() => handleStartSession('language_test', selectedLanguage, selectedDuration)}
                   disabled={starting}
                   variant="secondary"
                   className="w-full bg-transparent border border-white/20 text-white hover:bg-white hover:text-black font-bold uppercase tracking-widest py-4 rounded-none flex items-center justify-center gap-2"
                >
                   {starting ? 'INITIALIZING...' : (
                      <>
                         <Play size={14} fill="currentColor" /> Start Practice
                      </>
                   )}
                </Button>
             </div>
          </div>
        </div>
        )}
      </div>
    </div>
  );
}

export default Tutor;