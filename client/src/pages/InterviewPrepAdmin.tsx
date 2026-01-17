import { useState, useEffect, useCallback } from 'react';
import { Button, Modal } from '../components';
import { adminBeta } from '../api/client';
import type { CandidateBetaInfo, CandidateSessionSummary } from '../types';
import { History } from 'lucide-react';

const INTERVIEW_ROLES = [
  { value: 'Junior Engineer', label: 'Jr Eng' },
  { value: 'CTO', label: 'CTO' },
  { value: 'VP of People', label: 'VP People' },
  { value: 'Head of Marketing', label: 'Marketing' },
];

export function InterviewPrepAdmin() {
  const [candidates, setCandidates] = useState<CandidateBetaInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedUserId, setExpandedUserId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<CandidateSessionSummary[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);

  // Token award modal
  const [tokenModalOpen, setTokenModalOpen] = useState(false);
  const [tokenAmount, setTokenAmount] = useState('5');
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [awarding, setAwarding] = useState(false);

  const fetchCandidates = useCallback(async () => {
    try {
      setLoading(true);
      const data = await adminBeta.listCandidates();
      setCandidates(data.candidates);
    } catch (err) {
      console.error('Failed to fetch candidates:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCandidates();
  }, [fetchCandidates]);

  const handleToggleBeta = async (userId: string, currentEnabled: boolean) => {
    try {
      await adminBeta.toggleBetaAccess(userId, 'interview_prep', !currentEnabled);
      setCandidates(prev =>
        prev.map(c =>
          c.user_id === userId
            ? { ...c, beta_features: { ...c.beta_features, interview_prep: !currentEnabled } }
            : c
        )
      );
    } catch (err) {
      console.error('Failed to toggle beta:', err);
    }
  };

  const handleOpenTokenModal = (userId: string) => {
    setSelectedUserId(userId);
    setTokenAmount('5');
    setTokenModalOpen(true);
  };

  const handleAwardTokens = async () => {
    if (!selectedUserId) return;
    const amount = parseInt(tokenAmount);
    if (isNaN(amount) || amount <= 0) return;

    try {
      setAwarding(true);
      const result = await adminBeta.awardTokens(selectedUserId, amount);
      setCandidates(prev =>
        prev.map(c =>
          c.user_id === selectedUserId
            ? { ...c, interview_prep_tokens: result.new_total }
            : c
        )
      );
      setTokenModalOpen(false);
    } catch (err) {
      console.error('Failed to award tokens:', err);
    } finally {
      setAwarding(false);
    }
  };

  const handleToggleRole = async (userId: string, role: string, currentRoles: string[]) => {
    const newRoles = currentRoles.includes(role)
      ? currentRoles.filter(r => r !== role)
      : [...currentRoles, role];

    try {
      await adminBeta.updateAllowedRoles(userId, newRoles);
      setCandidates(prev =>
        prev.map(c =>
          c.user_id === userId
            ? { ...c, allowed_interview_roles: newRoles }
            : c
        )
      );
    } catch (err) {
      console.error('Failed to update roles:', err);
    }
  };

  const handleExpandRow = async (userId: string) => {
    if (expandedUserId === userId) {
      setExpandedUserId(null);
      setSessions([]);
      return;
    }

    setExpandedUserId(userId);
    setLoadingSessions(true);
    try {
      const data = await adminBeta.getCandidateSessions(userId);
      setSessions(data);
    } catch (err) {
      console.error('Failed to fetch sessions:', err);
      setSessions([]);
    } finally {
      setLoadingSessions(false);
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '—';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  };

  const getScoreColor = (score: number | null) => {
    if (score === null) return 'text-zinc-500';
    if (score >= 80) return 'text-emerald-400';
    if (score >= 60) return 'text-amber-400';
    return 'text-red-400';
  };

  return (
    <div className="max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex justify-between items-end border-b border-white/10 pb-8">
        <div>
          <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">Beta Administration</h1>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">
            Manage Interview Prep Access
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-zinc-900 border border-zinc-800 text-xs text-zinc-400 font-mono">
            <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
            {candidates.filter(c => c.beta_features.interview_prep).length} Active Users
          </div>
        </div>
      </div>

      {/* Main Table */}
      <div className="border border-white/10 bg-zinc-900/30">
          {loading ? (
            <div className="flex items-center justify-center py-24">
              <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Loading data...</div>
            </div>
          ) : candidates.length === 0 ? (
            <div className="text-center py-24 text-zinc-500 font-mono text-sm uppercase tracking-wider">
              No candidates found
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/10 bg-zinc-950">
                    <th className="text-left px-6 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                      Candidate
                    </th>
                    <th className="text-center px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                      Access
                    </th>
                    <th className="text-center px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                      Tokens
                    </th>
                    <th className="text-left px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                      Roles
                    </th>
                    <th className="text-center px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                      Stats
                    </th>
                    <th className="text-right px-6 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                      Last Active
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {candidates.map(candidate => {
                    const isExpanded = expandedUserId === candidate.user_id;
                    const hasBeta = candidate.beta_features.interview_prep || false;

                    return (
                      <>
                        <tr
                          key={candidate.user_id}
                          className={`border-b border-white/5 hover:bg-white/5 transition-colors cursor-pointer group ${
                            isExpanded ? 'bg-zinc-900' : 'bg-zinc-950'
                          }`}
                          onClick={() => handleExpandRow(candidate.user_id)}
                        >
                          {/* Name & Email */}
                          <td className="px-6 py-4">
                            <div className="flex items-center gap-4">
                              <div className="w-8 h-8 bg-zinc-800 border border-zinc-700 flex items-center justify-center text-xs text-white font-bold">
                                {candidate.name?.[0] || candidate.email[0]}
                              </div>
                              <div>
                                <div className="text-sm text-white font-bold group-hover:text-zinc-200 transition-colors">
                                  {candidate.name || 'Unknown'}
                                </div>
                                <div className="text-[10px] text-zinc-500 font-mono mt-0.5">
                                  {candidate.email}
                                </div>
                              </div>
                            </div>
                          </td>

                          {/* Beta Toggle */}
                          <td className="px-4 py-4 text-center" onClick={e => e.stopPropagation()}>
                            <button
                              onClick={() => handleToggleBeta(candidate.user_id, hasBeta)}
                              className={`relative w-8 h-4 transition-colors border ${
                                hasBeta ? 'bg-emerald-500/20 border-emerald-500/50' : 'bg-zinc-900 border-zinc-700'
                              }`}
                            >
                              <div
                                className={`absolute top-0.5 w-2.5 h-2.5 transition-all ${
                                  hasBeta ? 'left-4.5 bg-emerald-400' : 'left-0.5 bg-zinc-600'
                                }`}
                              />
                            </button>
                          </td>

                          {/* Tokens */}
                          <td className="px-4 py-4 text-center" onClick={e => e.stopPropagation()}>
                            <div className="inline-flex items-center gap-2 border border-zinc-800 bg-zinc-900 px-2 py-1">
                              <span className={`font-mono text-xs font-bold ${
                                candidate.interview_prep_tokens > 0 ? 'text-white' : 'text-zinc-600'
                              }`}>
                                {candidate.interview_prep_tokens}
                              </span>
                              <button
                                onClick={() => handleOpenTokenModal(candidate.user_id)}
                                className="text-zinc-500 hover:text-white transition-colors"
                              >
                                <PlusIcon className="w-3 h-3" />
                              </button>
                            </div>
                          </td>

                          {/* Allowed Roles */}
                          <td className="px-4 py-4" onClick={e => e.stopPropagation()}>
                            <div className="flex flex-wrap gap-1">
                              {INTERVIEW_ROLES.map(role => {
                                const isSelected = candidate.allowed_interview_roles?.includes(role.value);
                                return (
                                  <button
                                    key={role.value}
                                    onClick={() => handleToggleRole(candidate.user_id, role.value, candidate.allowed_interview_roles || [])}
                                    className={`px-1.5 py-0.5 text-[9px] uppercase tracking-wide border transition-colors ${
                                      isSelected
                                        ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20 hover:bg-emerald-500/20'
                                        : 'bg-zinc-900 text-zinc-600 border-zinc-800 hover:border-zinc-700 hover:text-zinc-400'
                                    }`}
                                  >
                                    {role.label}
                                  </button>
                                );
                              })}
                            </div>
                          </td>

                          {/* Stats */}
                          <td className="px-4 py-4 text-center">
                            <div className="flex flex-col items-center gap-1">
                               <span className="text-xs text-white font-mono">{candidate.total_sessions} <span className="text-zinc-600 text-[9px]">SESSIONS</span></span>
                               <span className={`text-xs font-mono font-bold ${getScoreColor(candidate.avg_score)}`}>
                                  {candidate.avg_score !== null ? `${candidate.avg_score}%` : '-'}
                               </span>
                            </div>
                          </td>

                          {/* Last Session */}
                          <td className="px-6 py-4 text-right">
                            <span className="text-[10px] text-zinc-500 font-mono uppercase">
                              {formatDate(candidate.last_session_at)}
                            </span>
                          </td>
                        </tr>

                        {/* Expanded Sessions */}
                        {isExpanded && (
                          <tr key={`${candidate.user_id}-expanded`}>
                            <td colSpan={7} className="bg-zinc-900 border-b border-white/10 p-0">
                              <div className="px-6 py-6 border-l-2 border-zinc-800 ml-6 my-2">
                                {loadingSessions ? (
                                  <div className="flex items-center gap-2 text-zinc-500 text-xs uppercase tracking-wider">
                                    <div className="w-3 h-3 border-2 border-zinc-600 border-t-transparent rounded-full animate-spin" />
                                    Retrieving history...
                                  </div>
                                ) : sessions.length === 0 ? (
                                  <div className="text-zinc-600 text-xs font-mono uppercase tracking-wider">
                                    No session history available
                                  </div>
                                ) : (
                                  <div className="space-y-4">
                                    <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold flex items-center gap-2">
                                      <History size={12} /> Session Log
                                    </div>
                                    <div className="grid gap-1">
                                      {sessions.map(session => (
                                        <div
                                          key={session.session_id}
                                          className="flex items-center justify-between px-4 py-3 bg-zinc-950 border border-zinc-800 hover:border-zinc-700 transition-colors group"
                                        >
                                          <div className="flex items-center gap-6">
                                            <div className="text-[10px] text-zinc-500 font-mono w-24">
                                              {formatDate(session.created_at)}
                                            </div>
                                            <div className="text-sm text-white font-bold w-48">
                                              {session.interview_role || 'General Prep'}
                                            </div>
                                            <div className="text-xs text-zinc-500 font-mono flex items-center gap-1">
                                              <span className="text-zinc-300">{session.duration_minutes}</span> min
                                            </div>
                                          </div>
                                          <div className="flex items-center gap-8">
                                            <div className="text-right w-24">
                                              <div className="text-[9px] uppercase text-zinc-600 tracking-wider">Response</div>
                                              <div className={`text-xs font-mono font-bold ${getScoreColor(session.response_quality_score)}`}>
                                                {session.response_quality_score !== null
                                                  ? `${session.response_quality_score}%`
                                                  : '—'}
                                              </div>
                                            </div>
                                            <div className="text-right w-24">
                                              <div className="text-[9px] uppercase text-zinc-600 tracking-wider">Comms</div>
                                              <div className={`text-xs font-mono font-bold ${getScoreColor(session.communication_score)}`}>
                                                {session.communication_score !== null
                                                  ? `${session.communication_score}%`
                                                  : '—'}
                                              </div>
                                            </div>
                                            <div className={`px-2 py-1 text-[9px] uppercase tracking-widest font-bold border ${
                                              session.status === 'completed'
                                                ? 'bg-emerald-900/20 text-emerald-400 border-emerald-900/50'
                                                : session.status === 'analyzing'
                                                ? 'bg-amber-900/20 text-amber-400 border-amber-900/50'
                                                : 'bg-zinc-800 text-zinc-500 border-zinc-700'
                                            }`}>
                                              {session.status}
                                            </div>
                                          </div>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </div>
                            </td>
                          </tr>
                        )}
                      </>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
      </div>

      {/* Token Award Modal */}
      <Modal
        isOpen={tokenModalOpen}
        onClose={() => setTokenModalOpen(false)}
        title="Grant Access Tokens"
      >
        <div className="space-y-6">
          <div className="p-4 bg-zinc-900 border border-zinc-800 text-xs text-zinc-400 leading-relaxed">
            Tokens grant candidates access to AI interview sessions. Each token is valid for one complete session (interview + analysis).
          </div>
          
          <div>
            <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-wider mb-2">
              Quantity
            </label>
            <div className="flex items-center gap-4">
               <button onClick={() => setTokenAmount(Math.max(1, parseInt(tokenAmount) - 1).toString())} className="w-10 h-10 border border-zinc-700 hover:bg-zinc-800 text-zinc-400 hover:text-white flex items-center justify-center transition-colors">-</button>
               <input
                 type="number"
                 min="1"
                 value={tokenAmount}
                 onChange={e => setTokenAmount(e.target.value)}
                 className="flex-1 h-10 bg-zinc-950 border border-zinc-800 text-white font-mono text-center text-lg focus:outline-none focus:border-zinc-600"
               />
               <button onClick={() => setTokenAmount((parseInt(tokenAmount) + 1).toString())} className="w-10 h-10 border border-zinc-700 hover:bg-zinc-800 text-zinc-400 hover:text-white flex items-center justify-center transition-colors">+</button>
            </div>
          </div>

          <div className="flex gap-3 pt-4">
            <Button
              variant="secondary"
              onClick={() => setTokenModalOpen(false)}
              className="flex-1 bg-transparent border-zinc-700 text-zinc-400 hover:text-white hover:bg-zinc-800"
            >
              Cancel
            </Button>
            <Button
              onClick={handleAwardTokens}
              disabled={awarding || !tokenAmount || parseInt(tokenAmount) <= 0}
              className="flex-1 bg-white text-black hover:bg-zinc-200 font-bold uppercase tracking-wider"
            >
              {awarding ? 'Processing...' : 'Confirm Grant'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

function PlusIcon({ className }: { className?: string }) {
   return (
      <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
         <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
      </svg>
   )
}

export default InterviewPrepAdmin;