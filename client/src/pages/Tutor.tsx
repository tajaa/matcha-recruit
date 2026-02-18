import { useState, useEffect, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Button } from '../components/Button';
import { AsciiWaveform } from '../components/AsciiWaveform';
import { tutor, companies } from '../api/client';
import { useAudioInterview } from '../hooks/useAudioInterview';
import { useAuth } from '../context/AuthContext';
import type { Company } from '../types';
import { Mic, Square, Clock, Award, Users, Globe, Play, CheckCircle2, Search, Target, Activity, ArrowLeft, ChevronRight } from 'lucide-react';
import { SystemCheckModal } from '../components/SystemCheckModal';

type CompanyInterviewMode = 'culture' | 'screening' | 'candidate';
type TutorMode = 'interview_prep' | 'language_test' | CompanyInterviewMode;
type Language = 'en' | 'es';
type Duration = 2 | 5 | 8;
type InterviewRole = 'VP of People' | 'CTO' | 'Head of Marketing' | 'Junior Engineer';

const INTERVIEW_ROLES: { value: InterviewRole; label: string; description: string }[] = [
  { value: 'Junior Engineer', label: 'Junior Engineer', description: 'Entry-level technical role' },
  { value: 'CTO', label: 'CTO', description: 'Technical leadership' },
  { value: 'VP of People', label: 'VP of People', description: 'HR leadership' },
  { value: 'Head of Marketing', label: 'Head of Marketing', description: 'Marketing leadership' },
];

const COMPANY_MODES: { value: CompanyInterviewMode; label: string; description: string; icon: typeof Users }[] = [
  { value: 'culture', label: 'Culture Interview', description: 'Capture executive culture signals', icon: Users },
  { value: 'screening', label: 'Screening Interview', description: 'First-pass candidate filtering', icon: Search },
  { value: 'candidate', label: 'Culture Fit Interview', description: 'Cross-check against culture profile', icon: Target },
];

function isCompanyInterviewMode(mode: TutorMode | null): mode is CompanyInterviewMode {
  return mode === 'culture' || mode === 'screening' || mode === 'candidate';
}

function getModeTitle(mode: TutorMode | null, role: InterviewRole, language: Language) {
  if (mode === 'interview_prep') return `${role} Simulation`;
  if (mode === 'language_test') return `Language Practice (${language === 'es' ? 'Spanish' : 'English'})`;
  if (mode === 'culture') return 'Culture Interview';
  if (mode === 'screening') return 'Screening Interview';
  if (mode === 'candidate') return 'Culture Fit Interview';
  return 'Session';
}

// Corner bracket decoration
function Brackets({ className = '', color = 'border-zinc-700' }: { className?: string; color?: string }) {
  return (
    <div className={`absolute inset-0 pointer-events-none ${className}`}>
      <div className={`absolute top-0 left-0 w-4 h-4 border-t border-l ${color}`} />
      <div className={`absolute top-0 right-0 w-4 h-4 border-t border-r ${color}`} />
      <div className={`absolute bottom-0 left-0 w-4 h-4 border-b border-l ${color}`} />
      <div className={`absolute bottom-0 right-0 w-4 h-4 border-b border-r ${color}`} />
    </div>
  );
}

// Scan line overlay
function ScanLine() {
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none rounded-inherit">
      <div
        className="absolute left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-white/8 to-transparent animate-scan-line"
        style={{ top: 0 }}
      />
    </div>
  );
}

// Grid dot background
function GridBg({ className = '' }: { className?: string }) {
  return (
    <div
      className={`absolute inset-0 pointer-events-none ${className}`}
      style={{
        backgroundImage: 'radial-gradient(circle, rgba(63,63,70,0.35) 1px, transparent 1px)',
        backgroundSize: '24px 24px',
      }}
    />
  );
}

export function Tutor() {
  const navigate = useNavigate();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { user, profile, interviewPrepTokens, allowedInterviewRoles, refreshUser } = useAuth();

  const isCandidate = user?.role === 'candidate';
  const isCompanyUser = user?.role === 'admin' || user?.role === 'client';
  const profileCompanyId =
    profile && typeof profile === 'object' && 'company_id' in profile && typeof profile.company_id === 'string'
      ? profile.company_id
      : null;

  const availableRoles = isCandidate
    ? INTERVIEW_ROLES.filter((role) => allowedInterviewRoles.includes(role.value))
    : INTERVIEW_ROLES;

  const [selectedMode, setSelectedMode] = useState<TutorMode | null>(null);
  const [selectedLanguage, setSelectedLanguage] = useState<Language>('es');
  const [selectedDuration, setSelectedDuration] = useState<Duration>(2);
  const [selectedInterviewDuration, setSelectedInterviewDuration] = useState<Duration>(5);
  const [selectedRole, setSelectedRole] = useState<InterviewRole>('Junior Engineer');
  const [companyModesLoaded, setCompanyModesLoaded] = useState(false);
  const [companiesList, setCompaniesList] = useState<Company[]>([]);
  const [selectedCompany, setSelectedCompany] = useState<string>('');
  const [selectedCompanyMode, setSelectedCompanyMode] = useState<CompanyInterviewMode>('culture');
  const [selectedCompanyDuration, setSelectedCompanyDuration] = useState<Duration>(8);
  const [interviewId, setInterviewId] = useState<string | null>(null);
  const [wsAuthToken, setWsAuthToken] = useState<string | null>(null);
  const [maxSessionDurationMs, setMaxSessionDurationMs] = useState<number | undefined>(undefined);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [completed, setCompleted] = useState(false);
  const [showSystemCheck, setShowSystemCheck] = useState(false);
  const [isPracticeMode, setIsPracticeMode] = useState(false);

  const {
    isConnected,
    isRecording,
    isPlaying,
    messages,
    sessionTimeRemaining,
    connect,
    disconnect,
    startRecording,
    stopRecording,
  } = useAudioInterview(interviewId || '', { maxSessionDurationMs, wsAuthToken });

  useEffect(() => {
    if (isCandidate && availableRoles.length > 0 && !availableRoles.some((r) => r.value === selectedRole)) {
      setSelectedRole(availableRoles[0].value);
    }
  }, [isCandidate, availableRoles, selectedRole]);

  useEffect(() => {
    if (!isCompanyUser) { setCompanyModesLoaded(true); return; }
    let mounted = true;
    const loadCompanies = async () => {
      try {
        const list = await companies.list();
        if (!mounted) return;
        setCompaniesList(list);
        const initialCompanyId =
          (profileCompanyId && list.some((c) => c.id === profileCompanyId) ? profileCompanyId : null) ||
          list[0]?.id || '';
        setSelectedCompany(initialCompanyId);
      } catch (err) {
        if (!mounted) return;
        console.error('Failed to load companies:', err);
        setError('Failed to load companies');
      } finally {
        if (mounted) setCompanyModesLoaded(true);
      }
    };
    loadCompanies();
    return () => { mounted = false; };
  }, [isCompanyUser, profileCompanyId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleStartSession = async (params: {
    mode: TutorMode;
    language?: Language;
    duration?: Duration;
    role?: InterviewRole;
    companyId?: string;
    isPractice?: boolean;
  }) => {
    setStarting(true);
    setError(null);
    setIsPracticeMode(params.isPractice || false);
    try {
      const result = await tutor.createSession({
        mode: params.mode,
        language: params.mode === 'language_test' ? params.language : undefined,
        duration_minutes: params.duration,
        interview_role: params.mode === 'interview_prep' ? params.role : undefined,
        company_id: isCompanyInterviewMode(params.mode) ? params.companyId : undefined,
        is_practice: params.isPractice || false,
      });
      setInterviewId(result.interview_id);
      setWsAuthToken(result.ws_auth_token || null);
      setMaxSessionDurationMs(result.max_session_duration_seconds * 1000);
      setSelectedMode(params.mode);
      if (params.language) setSelectedLanguage(params.language);
      if (params.duration) {
        if (params.mode === 'interview_prep') setSelectedInterviewDuration(params.duration);
        if (params.mode === 'language_test') setSelectedDuration(params.duration);
        if (isCompanyInterviewMode(params.mode)) setSelectedCompanyDuration(params.duration);
      }
      if (params.role) setSelectedRole(params.role);
      if (isCompanyInterviewMode(params.mode)) setSelectedCompanyMode(params.mode);
      if (params.companyId) setSelectedCompany(params.companyId);
      if (isCandidate) refreshUser();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start session');
    } finally {
      setStarting(false);
    }
  };

  const handleEnd = () => { disconnect(); setCompleted(true); };
  const handleReset = () => {
    disconnect();
    setInterviewId(null);
    setWsAuthToken(null);
    setSelectedMode(null);
    setCompleted(false);
    setError(null);
  };

  const formatTime = (seconds: number | null) => {
    if (seconds === null) return '';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const selectedCompanyName = companiesList.find((c) => c.id === selectedCompany)?.name || 'Selected Company';
  const selectedSessionTitle = getModeTitle(selectedMode, selectedRole, selectedLanguage);
  const completedCompanyMode = isCompanyInterviewMode(selectedMode);

  // ─── COMPLETED SCREEN ──────────────────────────────────────────────────────
  if (completed) {
    return (
      <motion.div
        className="max-w-2xl mx-auto py-12 space-y-8"
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
      >
        <div className="text-center space-y-6">
          {/* Animated ring stack */}
          <div className="relative w-24 h-24 mx-auto flex items-center justify-center">
            <div className={`absolute inset-0 rounded-full border ${isPracticeMode ? 'border-amber-500/20' : 'border-emerald-500/20'} animate-pulse-ring`} />
            <div className={`absolute inset-2 rounded-full border ${isPracticeMode ? 'border-amber-500/30' : 'border-emerald-500/30'} animate-pulse-ring`}
              style={{ animationDelay: '0.3s' }} />
            <div className={`w-16 h-16 rounded-full flex items-center justify-center ${isPracticeMode ? 'bg-amber-500/15 border border-amber-500/40' : 'bg-emerald-500/15 border border-emerald-500/40'}`}
              style={{ boxShadow: isPracticeMode ? '0 0 30px rgba(245,158,11,0.2)' : '0 0 30px rgba(52,211,153,0.2)' }}>
              <CheckCircle2 className={`w-8 h-8 ${isPracticeMode ? 'text-amber-400' : 'text-emerald-400'}`} />
            </div>
          </div>

          <div>
            <h1
              className="text-5xl font-black text-white tracking-tight uppercase animate-text-flicker"
              style={{ textShadow: '0 0 40px rgba(255,255,255,0.15)' }}
            >
              Session Complete
            </h1>
            <p className={`mt-3 font-mono text-sm tracking-widest uppercase ${isPracticeMode ? 'text-amber-400/70' : 'text-zinc-500'}`}>
              {isPracticeMode ? '// practice mode — session not saved' : '// analysis pipeline initiated'}
            </p>
          </div>
        </div>

        <div className="relative bg-zinc-900/80 border border-zinc-800 p-8 text-center overflow-hidden"
          style={{ boxShadow: '0 8px 40px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.05)' }}>
          <GridBg />
          <Brackets color={isPracticeMode ? 'border-amber-500/30' : 'border-emerald-500/20'} />
          <div className="relative z-10">
            <div className="text-[10px] font-mono text-zinc-600 uppercase tracking-widest mb-1">Session</div>
            <h2 className="text-lg font-bold text-white uppercase tracking-wider mb-4">{selectedSessionTitle}</h2>
            <p className="text-sm text-zinc-400 mb-8 max-w-md mx-auto leading-relaxed">
              {isPracticeMode
                ? 'This was a practice session — no data was saved and no analysis will be generated.'
                : selectedMode === 'interview_prep'
                ? `Responses for the ${selectedRole} role have been recorded. Review your communication and response quality once analysis completes.`
                : selectedMode === 'language_test'
                ? `Great work practicing ${selectedLanguage === 'es' ? 'Spanish' : 'English'}. Language scoring stays separate from hiring metrics.`
                : `Company interview analysis is being generated for ${selectedCompanyName}.`}
            </p>

            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              {!isPracticeMode && completedCompanyMode && isCompanyUser && (
                <Button
                  onClick={() => navigate(`/app/analysis/${interviewId}`)}
                  className="bg-white text-black hover:bg-zinc-200 font-bold uppercase tracking-wider"
                  style={{ boxShadow: '0 0 20px rgba(255,255,255,0.1)' }}
                >
                  View Analysis
                </Button>
              )}
              {!isPracticeMode && !completedCompanyMode && user?.role === 'admin' && (
                <Button
                  onClick={() => navigate(`/app/admin/tutor-metrics/${interviewId}`)}
                  className="bg-white text-black hover:bg-zinc-200 font-bold uppercase tracking-wider"
                  style={{ boxShadow: '0 0 20px rgba(255,255,255,0.1)' }}
                >
                  View Analysis
                </Button>
              )}
              <Button
                onClick={handleReset}
                className="bg-transparent border border-zinc-700 text-zinc-300 hover:text-white hover:border-zinc-500 font-bold uppercase tracking-wider flex items-center gap-2"
              >
                <ArrowLeft size={14} /> Back to Interviewer
              </Button>
              <Button
                variant="secondary"
                onClick={handleReset}
                className="bg-transparent border border-zinc-800 text-zinc-500 hover:text-zinc-300 font-bold uppercase tracking-wider text-xs"
              >
                Start New Session
              </Button>
            </div>
          </div>
        </div>

        {user?.role === 'admin' && (
          <div className="text-center">
            <Link to="/app/admin/tutor-metrics" className="text-[10px] text-zinc-600 hover:text-zinc-400 uppercase tracking-widest flex items-center justify-center gap-1 transition-colors">
              View All Sessions <ChevronRight size={10} />
            </Link>
          </div>
        )}
      </motion.div>
    );
  }

  // ─── ACTIVE SESSION ─────────────────────────────────────────────────────────
  if (interviewId) {
    return (
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Header */}
        <div className="relative flex items-center justify-between pb-5 border-b border-zinc-800/80">
          <div className="flex items-center gap-4">
            {/* Connection indicator with pulse ring */}
            <div className="relative flex items-center justify-center w-5 h-5 flex-shrink-0">
              {isConnected && (
                <div className="absolute inset-0 rounded-full bg-emerald-500/30 animate-pulse-ring" />
              )}
              <div className={`w-2.5 h-2.5 rounded-full ${isConnected ? 'bg-emerald-400' : 'bg-red-500'}`}
                style={{ boxShadow: isConnected ? '0 0 8px rgba(52,211,153,0.8)' : '0 0 8px rgba(239,68,68,0.6)' }} />
            </div>
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-lg font-black text-white uppercase tracking-widest">{selectedSessionTitle}</h1>
                {isPracticeMode && (
                  <span className="px-2 py-0.5 bg-amber-500/15 border border-amber-500/40 text-amber-400 text-[9px] font-bold uppercase tracking-widest"
                    style={{ boxShadow: '0 0 12px rgba(245,158,11,0.15)' }}>
                    Not Recording
                  </span>
                )}
              </div>
              <p className="text-[10px] text-zinc-600 font-mono uppercase tracking-widest mt-0.5">
                {selectedMode === 'interview_prep'
                  ? `Role: ${selectedRole}`
                  : selectedMode === 'language_test'
                  ? `Target: ${selectedLanguage === 'es' ? 'Spanish' : 'English'}`
                  : `Company: ${selectedCompanyName}`}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {sessionTimeRemaining !== null && (
              <div className="flex items-center gap-2 px-3 py-1.5 bg-zinc-900 border border-zinc-800"
                style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.04)' }}>
                <Clock className="w-3 h-3 text-zinc-600" />
                <span className={`font-mono text-base font-bold tracking-widest ${sessionTimeRemaining < 60 ? 'text-red-400 animate-pulse' : 'text-white'}`}>
                  [{formatTime(sessionTimeRemaining)}]
                </span>
              </div>
            )}
            <button
              onClick={handleReset}
              className="flex items-center gap-1.5 px-3 py-1.5 text-[10px] text-zinc-500 hover:text-white border border-zinc-800 hover:border-zinc-600 uppercase tracking-widest font-bold transition-all"
            >
              <ArrowLeft size={10} /> Back
            </button>
          </div>
        </div>

        {/* Main grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 h-[620px]">
          {/* Chat panel */}
          <div className="lg:col-span-2 relative flex flex-col border border-zinc-800 overflow-hidden"
            style={{ boxShadow: 'inset 0 0 60px rgba(0,0,0,0.5), 0 4px 30px rgba(0,0,0,0.4)' }}>
            <GridBg className="opacity-40" />
            <ScanLine />

            {/* Messages */}
            <div className="relative flex-1 overflow-y-auto p-5 space-y-4 bg-gradient-to-b from-black/60 to-black/40">
              {messages.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-zinc-700 space-y-4 opacity-60">
                  <div className="relative">
                    <div className="absolute inset-0 rounded-full bg-zinc-800/50 animate-ping" />
                    <Mic size={36} className="relative" />
                  </div>
                  <p className="font-mono text-[10px] uppercase tracking-widest">// awaiting audio input</p>
                </div>
              ) : (
                messages.map((msg, idx) => (
                  <motion.div
                    key={idx}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div className={`max-w-[88%] p-4 ${
                      msg.type === 'user'
                        ? 'bg-zinc-900/90 border border-zinc-700 text-white'
                        : msg.type === 'assistant'
                        ? 'bg-black/60 border border-emerald-500/25 text-emerald-50'
                        : 'bg-transparent border border-dashed border-zinc-800 text-zinc-600 text-xs w-full text-center'
                    }`}
                    style={msg.type === 'assistant' ? { boxShadow: '0 0 20px rgba(52,211,153,0.07)' } : {}}>
                      {msg.type !== 'system' && (
                        <div className={`text-[9px] uppercase tracking-widest mb-2 font-bold ${msg.type === 'user' ? 'text-zinc-500' : 'text-emerald-500'}`}>
                          {msg.type === 'user' ? '// Participant' : '// AI Interviewer'}
                        </div>
                      )}
                      <p className="leading-relaxed text-sm">{msg.content}</p>
                    </div>
                  </motion.div>
                ))
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Controls */}
            <div className="relative p-4 bg-zinc-950/90 border-t border-zinc-800/80"
              style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.04)' }}>
              {!isConnected ? (
                <Button onClick={connect} className="w-full py-3.5 text-xs font-black bg-white text-black hover:bg-zinc-100 uppercase tracking-widest"
                  style={{ boxShadow: '0 0 20px rgba(255,255,255,0.08)' }}>
                  Initialize Connection
                </Button>
              ) : (
                <div className="flex gap-3">
                  {!isRecording ? (
                    <Button onClick={startRecording}
                      className="flex-1 py-3.5 bg-white text-black hover:bg-zinc-100 text-xs font-black uppercase tracking-widest flex items-center justify-center gap-2"
                      style={{ boxShadow: '0 0 20px rgba(255,255,255,0.1)' }}>
                      <Mic size={14} /> Start Speaking
                    </Button>
                  ) : (
                    <Button onClick={stopRecording}
                      className="flex-1 py-3.5 bg-red-600 hover:bg-red-500 text-white text-xs font-black uppercase tracking-widest flex items-center justify-center gap-2"
                      style={{ boxShadow: '0 0 24px rgba(239,68,68,0.3)', animation: 'pulse 1.5s ease-in-out infinite' }}>
                      <Square size={14} fill="currentColor" /> Stop Speaking
                    </Button>
                  )}
                  <Button onClick={handleEnd} className="px-5 bg-transparent border border-zinc-700 text-zinc-400 hover:text-white hover:border-zinc-500 uppercase tracking-widest text-xs font-bold transition-all">
                    End
                  </Button>
                </div>
              )}
            </div>
          </div>

          {/* Status panel */}
          <div className="space-y-3 flex flex-col">
            {/* Waveform panel */}
            <div className="relative border border-zinc-800 bg-zinc-950/80 p-4 overflow-hidden"
              style={{
                boxShadow: isPlaying
                  ? '0 0 30px rgba(52,211,153,0.12), inset 0 0 30px rgba(0,0,0,0.6)'
                  : 'inset 0 0 30px rgba(0,0,0,0.6)',
                borderColor: isPlaying ? 'rgba(52,211,153,0.3)' : undefined,
                transition: 'box-shadow 0.4s, border-color 0.4s',
              }}>
              <Brackets color={isPlaying ? 'border-emerald-500/30' : 'border-zinc-800'} />
              <ScanLine />
              <div className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest mb-2 font-mono">
                // Audio Stream
              </div>
              <div className="bg-black/60 border border-zinc-900 py-3 px-2 rounded-sm">
                <AsciiWaveform isRecording={isRecording} isPlaying={isPlaying} />
              </div>
              <div className={`text-[9px] font-mono text-center mt-2 uppercase tracking-widest transition-colors ${
                isPlaying ? 'text-emerald-500' : isRecording ? 'text-white' : 'text-zinc-700'
              }`}>
                {isPlaying ? '◆ AI Speaking' : isRecording ? '◆ Listening' : '◇ Idle'}
              </div>
            </div>

            {/* Session data */}
            <div className="relative flex-1 border border-zinc-800 bg-zinc-950/60 p-4"
              style={{ boxShadow: 'inset 0 0 40px rgba(0,0,0,0.5)' }}>
              <Brackets />
              <div className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest mb-4 font-mono">
                // Session Status
              </div>
              <div className="space-y-3">
                {[
                  { label: 'Connection', value: isConnected ? 'Stable' : 'Offline', color: isConnected ? 'text-emerald-400' : 'text-zinc-600' },
                  { label: 'Recording', value: isPracticeMode ? 'Off' : 'On', color: isPracticeMode ? 'text-amber-400' : 'text-emerald-400' },
                  { label: 'Transcript', value: `${messages.length} Events`, color: 'text-zinc-300' },
                ].map(({ label, value, color }) => (
                  <div key={label} className="flex justify-between items-center border-b border-zinc-900 pb-2">
                    <span className="text-[10px] text-zinc-500 font-mono uppercase tracking-wider">{label}</span>
                    <span className={`text-[10px] font-mono font-bold uppercase tracking-wider ${color}`}>{value}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Tips */}
            <div className="relative border border-zinc-800/60 bg-zinc-950/40 p-4">
              <div className="text-[9px] font-bold text-zinc-700 uppercase tracking-widest mb-3 font-mono">// Tips</div>
              <ul className="text-[11px] text-zinc-500 space-y-2 leading-relaxed">
                <li className="flex gap-1.5"><span className="text-zinc-700 flex-shrink-0">›</span> Speak clearly and keep responses concise.</li>
                <li className="flex gap-1.5"><span className="text-zinc-700 flex-shrink-0">›</span> Wait for the AI to finish before responding.</li>
                {selectedMode === 'language_test' ? (
                  <li className="flex gap-1.5"><span className="text-zinc-700 flex-shrink-0">›</span> Prioritize grammar and fluency.</li>
                ) : isCompanyInterviewMode(selectedMode) ? (
                  <li className="flex gap-1.5"><span className="text-zinc-700 flex-shrink-0">›</span> Focus on values and alignment signals.</li>
                ) : (
                  <li className="flex gap-1.5"><span className="text-zinc-700 flex-shrink-0">›</span> Use specific examples (STAR method).</li>
                )}
              </ul>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ─── MODE SELECTION ─────────────────────────────────────────────────────────
  return (
    <div className="relative max-w-6xl mx-auto space-y-10">
      <GridBg className="opacity-50 fixed inset-0 pointer-events-none" />

      {/* Header */}
      <div className="relative flex items-start justify-between border-b border-zinc-800/60 pb-7">
        <div>
          <div className="flex items-center gap-4 mb-2">
            <h1
              className="text-5xl font-black text-white tracking-tight uppercase"
              style={{ textShadow: '0 0 60px rgba(255,255,255,0.12)', letterSpacing: '-0.02em' }}
            >
              {isCandidate ? 'Interview Prep' : 'Tutor'}
            </h1>
            <button
              onClick={() => setShowSystemCheck(true)}
              className="hidden sm:flex items-center gap-1.5 text-[9px] text-zinc-600 hover:text-zinc-300 uppercase tracking-widest border border-zinc-800 hover:border-zinc-600 px-3 py-1.5 transition-all font-bold font-mono"
            >
              <Activity size={10} /> System Check
            </button>
          </div>
          <p className="text-[10px] text-zinc-600 font-mono tracking-widest uppercase">
            <span className="text-zinc-700 mr-1">&gt;</span>
            Unified Interview System — Language Coaching + Culture/Screening
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={() => setShowSystemCheck(true)} className="sm:hidden text-zinc-600 hover:text-white p-2 border border-zinc-800 hover:border-zinc-600 transition-all">
            <Activity size={15} />
          </button>
          {isCandidate && (
            <div className="flex items-center gap-3 px-4 py-2.5 bg-zinc-900/60 border border-zinc-800 relative overflow-hidden"
              style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.04)' }}>
              <Award className="w-4 h-4 text-amber-500" style={{ filter: 'drop-shadow(0 0 6px rgba(245,158,11,0.5))' }} />
              <div className="flex flex-col items-end">
                <span className={`text-xl font-mono font-black leading-none ${interviewPrepTokens > 0 ? 'text-white' : 'text-red-400'}`}>
                  {interviewPrepTokens}
                </span>
                <span className="text-[8px] text-zinc-600 uppercase tracking-wider font-mono">Tokens</span>
              </div>
            </div>
          )}
        </div>
      </div>

      <SystemCheckModal isOpen={showSystemCheck} onClose={() => setShowSystemCheck(false)} />

      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="bg-red-950/40 border border-red-500/30 p-4 text-red-400 text-xs font-mono flex items-center gap-3"
            style={{ boxShadow: '0 0 20px rgba(239,68,68,0.1)' }}
          >
            <div className="w-1.5 h-1.5 bg-red-500 rounded-full animate-pulse flex-shrink-0" />
            {error}
          </motion.div>
        )}
      </AnimatePresence>

      {isCandidate && interviewPrepTokens === 0 && (
        <div className="bg-amber-950/30 border border-amber-500/25 p-5 relative overflow-hidden"
          style={{ boxShadow: '0 0 30px rgba(245,158,11,0.08)' }}>
          <Brackets color="border-amber-500/20" />
          <div className="relative">
            <h3 className="font-bold uppercase tracking-wider text-sm mb-1.5 flex items-center gap-2 text-amber-400">
              <Clock className="w-4 h-4" /> Insufficient Tokens
            </h3>
            <p className="text-xs text-amber-400/60 font-mono">You have exhausted your interview preparation tokens. Contact your administrator to request additional access.</p>
          </div>
        </div>
      )}

      {/* Cards grid */}
      <div className={`grid gap-5 ${isCandidate ? 'grid-cols-1 max-w-2xl' : 'grid-cols-1 xl:grid-cols-3'}`}>

        {/* ── Role Simulation Card ── */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0 }}
          className="relative bg-zinc-950/90 border border-zinc-800 p-7 overflow-hidden group"
          style={{ boxShadow: '0 8px 40px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.04)' }}
          whileHover={{ boxShadow: '0 12px 50px rgba(0,0,0,0.7), inset 0 1px 0 rgba(255,255,255,0.06), 0 0 0 1px rgba(255,255,255,0.06)' }}
        >
          {/* Accent line top */}
          <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-white/20 to-transparent" />
          <Brackets />
          <ScanLine />

          {/* Background icon */}
          <div className="absolute top-0 right-0 p-6 opacity-[0.04] group-hover:opacity-[0.07] transition-opacity duration-500">
            <Users className="w-36 h-36 text-white" />
          </div>

          <div className="relative z-10 space-y-6">
            <div>
              <div className="w-10 h-10 bg-white/95 text-black flex items-center justify-center mb-5"
                style={{ boxShadow: '0 0 20px rgba(255,255,255,0.15)' }}>
                <Users className="w-5 h-5" />
              </div>
              <h2 className="text-xl font-black text-white uppercase tracking-tight">Role Simulation</h2>
              <p className="text-zinc-500 text-xs mt-1.5 leading-relaxed max-w-xs">
                Practice role-specific questions with an AI coach that adapts and provides detailed feedback.
              </p>
            </div>

            <div>
              <label className="block text-[9px] text-zinc-600 uppercase tracking-widest font-bold font-mono mb-2">Target Role</label>
              {availableRoles.length === 0 ? (
                <div className="p-4 border border-dashed border-zinc-800 text-center text-[10px] text-zinc-700 font-mono uppercase tracking-widest">
                  // No roles assigned
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-1.5">
                  {availableRoles.map((role) => (
                    <button
                      key={role.value}
                      onClick={() => setSelectedRole(role.value)}
                      className={`px-3 py-2 text-left border text-[10px] font-bold uppercase tracking-wider transition-all ${
                        selectedRole === role.value
                          ? 'bg-white text-black border-white'
                          : 'bg-zinc-900/60 text-zinc-500 border-zinc-800 hover:border-zinc-600 hover:text-zinc-300'
                      }`}
                      style={selectedRole === role.value ? { boxShadow: '0 0 16px rgba(255,255,255,0.12)' } : {}}
                    >
                      {role.label}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div>
              <label className="block text-[9px] text-zinc-600 uppercase tracking-widest font-bold font-mono mb-2">Duration</label>
              <div className="flex gap-1.5">
                {[5, 8].map((d) => (
                  <button
                    key={d}
                    onClick={() => setSelectedInterviewDuration(d as Duration)}
                    className={`flex-1 py-2 border text-[10px] font-bold uppercase tracking-wider transition-all ${
                      selectedInterviewDuration === d
                        ? 'bg-white text-black border-white'
                        : 'bg-zinc-900/60 text-zinc-500 border-zinc-800 hover:border-zinc-600 hover:text-zinc-300'
                    }`}
                    style={selectedInterviewDuration === d ? { boxShadow: '0 0 16px rgba(255,255,255,0.12)' } : {}}
                  >
                    {d} Min
                  </button>
                ))}
              </div>
            </div>

            <Button
              onClick={() => handleStartSession({ mode: 'interview_prep', duration: selectedInterviewDuration, role: selectedRole })}
              disabled={starting || (isCandidate && interviewPrepTokens === 0) || (isCandidate && availableRoles.length === 0)}
              className="w-full bg-white text-black hover:bg-zinc-100 font-black uppercase tracking-widest py-3.5 rounded-none text-xs"
              style={{ boxShadow: '0 0 20px rgba(255,255,255,0.1)' }}
            >
              {starting ? '// Initializing...' : 'Start Simulation'}
            </Button>

            {isCandidate && (
              <div className="text-center text-[9px] text-zinc-700 uppercase tracking-widest font-mono">
                // Cost: 1 Token
              </div>
            )}
          </div>
        </motion.div>

        {/* ── Language Lab Card ── */}
        {!isCandidate && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.08 }}
            className="relative bg-zinc-900/40 border border-zinc-800/80 p-7 overflow-hidden group"
            style={{ boxShadow: '0 8px 40px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.03)' }}
            whileHover={{ boxShadow: '0 12px 50px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.05), 0 0 0 1px rgba(255,255,255,0.05)' }}
          >
            <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-zinc-600/30 to-transparent" />
            <Brackets color="border-zinc-800" />
            <ScanLine />

            <div className="absolute top-0 right-0 p-6 opacity-[0.03] group-hover:opacity-[0.06] transition-opacity duration-500">
              <Globe className="w-36 h-36 text-white" />
            </div>

            <div className="relative z-10 space-y-6">
              <div>
                <div className="w-10 h-10 bg-zinc-800/80 border border-zinc-700 flex items-center justify-center mb-5 text-zinc-400">
                  <Globe className="w-5 h-5" />
                </div>
                <h2 className="text-xl font-black text-white uppercase tracking-tight">Language Lab</h2>
                <p className="text-zinc-500 text-xs mt-1.5 leading-relaxed max-w-xs">
                  Non-native language interview practice. Fluency scores stay isolated from company hiring metrics.
                </p>
              </div>

              <div>
                <label className="block text-[9px] text-zinc-600 uppercase tracking-widest font-bold font-mono mb-2">Language</label>
                <div className="flex gap-1.5">
                  {(['en', 'es'] as Language[]).map((lang) => (
                    <button
                      key={lang}
                      onClick={() => setSelectedLanguage(lang)}
                      className={`flex-1 py-2 border text-[10px] font-bold uppercase tracking-wider transition-all ${
                        selectedLanguage === lang
                          ? 'bg-zinc-800 text-white border-zinc-600'
                          : 'bg-zinc-950/60 text-zinc-500 border-zinc-800 hover:border-zinc-700 hover:text-zinc-300'
                      }`}
                    >
                      {lang === 'en' ? 'English' : 'Spanish'}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-[9px] text-zinc-600 uppercase tracking-widest font-bold font-mono mb-2">Duration</label>
                <div className="flex gap-1.5">
                  {[2, 8].map((d) => (
                    <button
                      key={d}
                      onClick={() => setSelectedDuration(d as Duration)}
                      className={`flex-1 py-2 border text-[10px] font-bold uppercase tracking-wider transition-all ${
                        selectedDuration === d
                          ? 'bg-zinc-800 text-white border-zinc-600'
                          : 'bg-zinc-950/60 text-zinc-500 border-zinc-800 hover:border-zinc-700 hover:text-zinc-300'
                      }`}
                    >
                      {d} Min
                    </button>
                  ))}
                </div>
              </div>

              {/* Don't Record toggle */}
              <div className="flex items-center justify-between py-3 border-t border-zinc-800/60">
                <div>
                  <div className="text-[10px] font-bold text-zinc-300 uppercase tracking-wider">Don't Record</div>
                  <div className="text-[9px] text-zinc-600 font-mono mt-0.5">Session won't be saved or analyzed</div>
                </div>
                <button
                  onClick={() => setIsPracticeMode((v) => !v)}
                  className={`relative w-10 h-5 rounded-full transition-all duration-200 focus:outline-none ${isPracticeMode ? 'bg-amber-500' : 'bg-zinc-800 border border-zinc-700'}`}
                  aria-label="Toggle practice mode"
                  style={isPracticeMode ? { boxShadow: '0 0 12px rgba(245,158,11,0.4)' } : {}}
                >
                  <div className={`absolute top-0.5 w-4 h-4 rounded-full transition-all duration-200 ${isPracticeMode ? 'left-5 bg-white' : 'left-0.5 bg-zinc-600'}`} />
                </button>
              </div>

              <Button
                onClick={() => handleStartSession({ mode: 'language_test', language: selectedLanguage, duration: selectedDuration, isPractice: isPracticeMode })}
                disabled={starting}
                className={`w-full font-black uppercase tracking-widest py-3.5 rounded-none flex items-center justify-center gap-2 text-xs ${
                  isPracticeMode
                    ? 'bg-amber-500/10 border border-amber-500/40 text-amber-400 hover:bg-amber-500/20'
                    : 'bg-transparent border border-white/20 text-white hover:bg-white hover:text-black'
                }`}
                style={isPracticeMode ? { boxShadow: '0 0 20px rgba(245,158,11,0.1)' } : {}}
              >
                {starting ? '// Initializing...' : isPracticeMode ? (
                  <><Play size={12} fill="currentColor" /> Start (No Recording)</>
                ) : (
                  <><Play size={12} fill="currentColor" /> Start Practice</>
                )}
              </Button>
            </div>
          </motion.div>
        )}

        {/* ── Company Interviews Card ── */}
        {!isCandidate && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.16 }}
            className="relative bg-zinc-900/40 border border-zinc-800/80 p-7 overflow-hidden group"
            style={{ boxShadow: '0 8px 40px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.03)' }}
            whileHover={{ boxShadow: '0 12px 50px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.05), 0 0 0 1px rgba(255,255,255,0.05)' }}
          >
            <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-zinc-600/30 to-transparent" />
            <Brackets color="border-zinc-800" />
            <ScanLine />

            <div className="relative z-10 space-y-5">
              <div>
                <h2 className="text-xl font-black text-white uppercase tracking-tight">Company Interviews</h2>
                <p className="text-zinc-500 text-xs mt-1.5 leading-relaxed">
                  Culture capture and hiring evaluation. Scores tracked separately from language coaching.
                </p>
              </div>

              <div className="space-y-1.5">
                {COMPANY_MODES.map((option) => {
                  const Icon = option.icon;
                  const sel = selectedCompanyMode === option.value;
                  return (
                    <button
                      key={option.value}
                      onClick={() => setSelectedCompanyMode(option.value)}
                      className={`w-full p-3 border text-left transition-all ${
                        sel
                          ? 'border-zinc-600 bg-zinc-800/80 text-white'
                          : 'border-zinc-800/80 bg-zinc-950/60 text-zinc-500 hover:border-zinc-700 hover:text-zinc-300'
                      }`}
                      style={sel ? { boxShadow: '0 0 16px rgba(255,255,255,0.05)' } : {}}
                    >
                      <div className="flex items-center gap-3">
                        <Icon size={13} />
                        <div>
                          <div className="text-[10px] font-bold uppercase tracking-wider">{option.label}</div>
                          <div className="text-[9px] font-mono text-zinc-600 mt-0.5">{option.description}</div>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>

              <div>
                <label className="block text-[9px] text-zinc-600 uppercase tracking-widest font-bold font-mono mb-2">Target Company</label>
                <select
                  value={selectedCompany}
                  onChange={(e) => setSelectedCompany(e.target.value)}
                  disabled={!companyModesLoaded || companiesList.length === 0 || user?.role === 'client'}
                  className="w-full px-3 py-2 bg-zinc-950/80 border border-zinc-800 text-white text-xs focus:outline-none focus:border-zinc-600 transition-colors disabled:opacity-40 font-mono"
                >
                  {companiesList.map((company) => (
                    <option key={company.id} value={company.id}>{company.name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-[9px] text-zinc-600 uppercase tracking-widest font-bold font-mono mb-2">Duration</label>
                <div className="flex gap-1.5">
                  {[5, 8].map((d) => (
                    <button
                      key={d}
                      onClick={() => setSelectedCompanyDuration(d as Duration)}
                      className={`flex-1 py-2 border text-[10px] font-bold uppercase tracking-wider transition-all ${
                        selectedCompanyDuration === d
                          ? 'bg-zinc-800 text-white border-zinc-600'
                          : 'bg-zinc-950/60 text-zinc-500 border-zinc-800 hover:border-zinc-700 hover:text-zinc-300'
                      }`}
                    >
                      {d} Min
                    </button>
                  ))}
                </div>
              </div>

              <Button
                onClick={() => handleStartSession({ mode: selectedCompanyMode, duration: selectedCompanyDuration, companyId: selectedCompany })}
                disabled={starting || !selectedCompany}
                className="w-full bg-transparent border border-white/20 text-white hover:bg-white hover:text-black font-black uppercase tracking-widest py-3.5 rounded-none text-xs"
              >
                {starting ? '// Initializing...' : `Start ${COMPANY_MODES.find((m) => m.value === selectedCompanyMode)?.label ?? 'Interview'}`}
              </Button>
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
}

export default Tutor;
