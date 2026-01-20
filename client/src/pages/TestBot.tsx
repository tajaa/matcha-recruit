import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAudioInterview } from '../hooks/useAudioInterview';
import { companies, interviews } from '../api/client';
import type { Company, InterviewType } from '../types';
import { Mic, Square, RefreshCcw, Radio, Users, Search, Target } from 'lucide-react';

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

  useEffect(() => {
    loadCompanies();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const loadCompanies = async () => {
    try {
      const list = await companies.list();
      setCompaniesList(list);
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
    if (interviewId) {
      navigate(`/app/analysis/${interviewId}`);
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
    <div className="max-w-5xl mx-auto space-y-12">
      {/* Header */}
      <div className="border-b border-white/10 pb-8">
        <h1 className="text-4xl font-bold tracking-tighter text-white uppercase flex items-center gap-4">
          <div className="w-10 h-10 bg-zinc-900 border border-zinc-800 flex items-center justify-center">
             <Radio className="w-5 h-5 text-white" />
          </div>
          Test Bot
        </h1>
        <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase pl-[56px]">
          AI Interviewer Sandbox & Diagnostics
        </p>
      </div>

      {!interviewId ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-2 space-y-8">
             <div className="bg-zinc-950 border border-zinc-800 p-8">
                <h2 className="text-sm font-bold text-white uppercase tracking-wider mb-6">Select Interview Mode</h2>
                <div className="space-y-4">
                  {[
                    { id: 'culture', label: 'Culture Interview', desc: 'Test as HR representative', icon: Users, activeClass: 'border-white bg-zinc-900' },
                    { id: 'screening', label: 'Screening Interview', desc: 'First-round filtering', icon: Search, activeClass: 'border-amber-500/50 bg-amber-900/10' },
                    { id: 'candidate', label: 'Culture Fit Interview', desc: 'Requires culture profile', icon: Target, activeClass: 'border-blue-500/50 bg-blue-900/10' }
                  ].map((option) => (
                    <button
                      key={option.id}
                      onClick={() => setMode(option.id as InterviewType)}
                      className={`w-full p-6 border text-left transition-all group ${
                        mode === option.id 
                          ? option.activeClass 
                          : 'border-zinc-800 hover:border-zinc-700 bg-zinc-950'
                      }`}
                    >
                      <div className="flex items-center gap-4">
                        <div className={`p-2 rounded-none border ${
                           mode === option.id ? 'border-white/20 bg-white/10 text-white' : 'border-zinc-800 bg-zinc-900 text-zinc-500 group-hover:text-zinc-300'
                        }`}>
                           <option.icon size={20} />
                        </div>
                        <div>
                          <h3 className={`font-bold uppercase tracking-wider text-xs mb-1 ${
                             mode === option.id ? 'text-white' : 'text-zinc-400 group-hover:text-zinc-200'
                          }`}>
                            {option.label}
                          </h3>
                          <p className="text-[10px] text-zinc-500 font-mono">{option.desc}</p>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
             </div>

             <div className="bg-zinc-900/30 border border-zinc-800 p-8">
                <div className="mb-6">
                  <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-wider mb-2">Target Company</label>
                  <select
                    value={selectedCompany}
                    onChange={(e) => setSelectedCompany(e.target.value)}
                    className="w-full px-4 py-3 bg-zinc-950 border border-zinc-800 text-white text-sm focus:outline-none focus:border-white/20 transition-colors font-mono"
                  >
                    {companiesList.map((company) => (
                      <option key={company.id} value={company.id}>
                        {company.name} {company.culture_profile ? '[HAS PROFILE]' : ''}
                      </option>
                    ))}
                  </select>
                </div>

                {error && (
                  <div className="mb-6 p-4 bg-red-500/10 border border-red-500/20 text-red-400 text-xs font-mono">
                    ERROR: {error}
                  </div>
                )}

                <button
                  onClick={handleStartSession}
                  disabled={!selectedCompany || isCreating}
                  className="w-full py-4 bg-white text-black hover:bg-zinc-200 text-sm font-bold uppercase tracking-widest transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isCreating ? 'INITIALIZING SESSION...' : 'START SESSION'}
                </button>
             </div>
          </div>

          <div className="border border-zinc-800 bg-zinc-900/20 p-8 h-fit">
             <h3 className="text-xs font-bold text-white uppercase tracking-wider mb-4 border-b border-white/10 pb-4">
                Protocol: {mode.toUpperCase()}
             </h3>
             <div className="text-xs text-zinc-400 space-y-4 font-mono leading-relaxed">
                {mode === 'culture' && (
                  <>
                    <p>ROLE: Act as an HR representative.</p>
                    <p>OBJECTIVE: Describe your company's culture, values, and working style.</p>
                    <p>OUTPUT: System will generate a culture profile based on your inputs.</p>
                  </>
                )}
                {mode === 'screening' && (
                  <>
                    <p>ROLE: Act as a job candidate.</p>
                    <p>OBJECTIVE: Respond to screening questions about your experience.</p>
                    <p>METRICS: Communication, engagement, professionalism.</p>
                  </>
                )}
                {mode === 'candidate' && (
                  <>
                    <p>ROLE: Act as a job candidate.</p>
                    <p>OBJECTIVE: Determine alignment with {selectedCompanyName}'s culture profile.</p>
                    <p>FOCUS: Work preferences, values, team dynamics.</p>
                  </>
                )}
             </div>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 h-[calc(100vh-200px)]">
          {/* Main Interface */}
          <div className="lg:col-span-2 flex flex-col bg-zinc-950 border border-zinc-800 relative overflow-hidden">
             {/* Status Bar */}
             <div className="flex items-center justify-between p-4 border-b border-zinc-800 bg-zinc-900/50">
                <div className="flex items-center gap-4">
                   <div className={`flex items-center gap-2 px-3 py-1 border text-[10px] font-bold uppercase tracking-wider ${
                      isConnected ? 'border-emerald-900/50 bg-emerald-900/20 text-emerald-400' : 'border-red-900/50 bg-red-900/20 text-red-400'
                   }`}>
                      <div className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-emerald-500 animate-pulse' : 'bg-red-500'}`} />
                      {isConnected ? 'LIVE FEED' : 'OFFLINE'}
                   </div>
                   {isRecording && (
                      <span className="text-[10px] font-bold text-red-500 uppercase tracking-wider animate-pulse">REC ●</span>
                   )}
                </div>
                <div className="text-[10px] font-mono text-zinc-500">
                   SESSION ID: {interviewId.slice(0, 8)}...
                </div>
             </div>

             {/* Chat Area */}
             <div className="flex-1 overflow-y-auto p-6 space-y-6 font-mono text-sm bg-black/50">
                {messages.length === 0 ? (
                   <div className="h-full flex flex-col items-center justify-center text-zinc-600 space-y-4">
                      <Radio size={48} className="opacity-20" />
                      <p className="uppercase tracking-widest text-xs">Awaiting Audio Stream...</p>
                   </div>
                ) : (
                   messages.map((msg, idx) => (
                      <div key={idx} className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}>
                         <div className={`max-w-[80%] p-4 border ${
                            msg.type === 'user' 
                               ? 'bg-zinc-900 border-zinc-700 text-white' 
                               : msg.type === 'assistant'
                                  ? 'bg-zinc-950 border-white/20 text-emerald-400'
                                  : 'bg-transparent border-dashed border-zinc-800 text-zinc-500 text-xs w-full text-center'
                         }`}>
                            {msg.type !== 'system' && msg.type !== 'status' && (
                               <div className="text-[9px] uppercase tracking-widest mb-2 opacity-50">
                                  {msg.type === 'user' ? 'SUBJECT' : 'AI AGENT'}
                               </div>
                            )}
                            {msg.content}
                         </div>
                      </div>
                   ))
                )}
                <div ref={messagesEndRef} />
             </div>

             {/* Controls */}
             <div className="p-6 border-t border-zinc-800 bg-zinc-900/30">
                {!isConnected ? (
                   <button 
                      onClick={connect} 
                      className="w-full py-4 bg-white text-black hover:bg-zinc-200 text-sm font-bold uppercase tracking-widest flex items-center justify-center gap-3 transition-colors"
                   >
                      <Radio size={18} /> Initialize Connection
                   </button>
                ) : (
                   <div className="flex gap-4">
                      {!isRecording ? (
                         <button 
                            onClick={startRecording} 
                            className="flex-1 py-4 bg-white text-black hover:bg-zinc-200 text-sm font-bold uppercase tracking-widest flex items-center justify-center gap-3 transition-colors"
                         >
                            <Mic size={18} /> Start Speaking
                         </button>
                      ) : (
                         <button 
                            onClick={stopRecording} 
                            className="flex-1 py-4 bg-red-500 hover:bg-red-600 text-white text-sm font-bold uppercase tracking-widest flex items-center justify-center gap-3 transition-colors"
                         >
                            <Square size={18} /> Stop Speaking
                         </button>
                      )}
                      <button 
                         onClick={handleEndSession} 
                         className="px-8 border border-zinc-700 text-zinc-400 hover:text-white hover:border-white hover:bg-zinc-900 transition-colors uppercase tracking-widest text-xs font-bold"
                      >
                         End
                      </button>
                   </div>
                )}
             </div>
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
             <div className="border border-zinc-800 bg-zinc-900/20 p-6">
                <h3 className="text-xs font-bold text-white uppercase tracking-wider mb-4 border-b border-white/10 pb-4">
                   Session Metadata
                </h3>
                <div className="space-y-4">
                   <div>
                      <label className="text-[10px] text-zinc-500 uppercase tracking-wider block mb-1">Company</label>
                      <div className="text-sm text-white font-mono">{selectedCompanyName}</div>
                   </div>
                   <div>
                      <label className="text-[10px] text-zinc-500 uppercase tracking-wider block mb-1">Mode</label>
                      <div className="text-sm text-white font-mono uppercase">{mode}</div>
                   </div>
                   <div>
                      <label className="text-[10px] text-zinc-500 uppercase tracking-wider block mb-1">Status</label>
                      <div className={`text-sm font-mono uppercase ${isConnected ? 'text-emerald-500' : 'text-zinc-500'}`}>
                         {isConnected ? 'Active' : 'Standby'}
                      </div>
                   </div>
                </div>
             </div>

             <button 
                onClick={handleReset}
                className="w-full py-3 border border-zinc-800 text-zinc-500 hover:text-white hover:border-white transition-colors text-xs font-bold uppercase tracking-wider flex items-center justify-center gap-2"
             >
                <RefreshCcw size={14} /> Reset System
             </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default TestBot;