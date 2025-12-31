import { useState, useEffect, useCallback } from 'react';
import { Button, Card, CardContent, Modal } from '../components';
import { adminBeta } from '../api/client';
import type { CandidateBetaInfo, CandidateSessionSummary } from '../types';

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
    <div className="min-h-screen">
      {/* Header */}
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight">Interview Prep Beta</h1>
          <p className="text-zinc-500 text-sm mt-1 font-mono">
            Manage candidate access and tokens
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="px-3 py-1.5 bg-zinc-900 border border-zinc-800 text-xs text-zinc-400 font-mono">
            {candidates.filter(c => c.beta_features.interview_prep).length} active
          </div>
        </div>
      </div>

      {/* Main Table */}
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <div className="w-5 h-5 border-2 border-zinc-700 border-t-white rounded-full animate-spin" />
            </div>
          ) : candidates.length === 0 ? (
            <div className="text-center py-16 text-zinc-500 font-mono text-sm">
              No candidates found
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-zinc-800">
                    <th className="text-left px-5 py-3 text-[10px] font-medium text-zinc-500 uppercase tracking-widest">
                      Candidate
                    </th>
                    <th className="text-center px-4 py-3 text-[10px] font-medium text-zinc-500 uppercase tracking-widest">
                      Beta Access
                    </th>
                    <th className="text-center px-4 py-3 text-[10px] font-medium text-zinc-500 uppercase tracking-widest">
                      Tokens
                    </th>
                    <th className="text-left px-4 py-3 text-[10px] font-medium text-zinc-500 uppercase tracking-widest">
                      Allowed Roles
                    </th>
                    <th className="text-center px-4 py-3 text-[10px] font-medium text-zinc-500 uppercase tracking-widest">
                      Sessions
                    </th>
                    <th className="text-center px-4 py-3 text-[10px] font-medium text-zinc-500 uppercase tracking-widest">
                      Avg Score
                    </th>
                    <th className="text-right px-5 py-3 text-[10px] font-medium text-zinc-500 uppercase tracking-widest">
                      Last Session
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
                          className={`border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors cursor-pointer ${
                            isExpanded ? 'bg-zinc-800/20' : ''
                          }`}
                          onClick={() => handleExpandRow(candidate.user_id)}
                        >
                          {/* Name & Email */}
                          <td className="px-5 py-4">
                            <div className="flex items-center gap-3">
                              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-zinc-700 to-zinc-800 flex items-center justify-center text-xs text-zinc-400 font-medium uppercase">
                                {candidate.name?.[0] || candidate.email[0]}
                              </div>
                              <div>
                                <div className="text-sm text-white font-medium">
                                  {candidate.name || 'Unnamed'}
                                </div>
                                <div className="text-xs text-zinc-500 font-mono">
                                  {candidate.email}
                                </div>
                              </div>
                            </div>
                          </td>

                          {/* Beta Toggle */}
                          <td className="px-4 py-4 text-center" onClick={e => e.stopPropagation()}>
                            <button
                              onClick={() => handleToggleBeta(candidate.user_id, hasBeta)}
                              className={`relative w-10 h-5 rounded-full transition-colors ${
                                hasBeta ? 'bg-emerald-500/20' : 'bg-zinc-800'
                              }`}
                            >
                              <span
                                className={`absolute top-0.5 w-4 h-4 rounded-full transition-all ${
                                  hasBeta
                                    ? 'left-5.5 bg-emerald-400 shadow-lg shadow-emerald-500/30'
                                    : 'left-0.5 bg-zinc-600'
                                }`}
                                style={{ left: hasBeta ? '22px' : '2px' }}
                              />
                            </button>
                          </td>

                          {/* Tokens */}
                          <td className="px-4 py-4 text-center" onClick={e => e.stopPropagation()}>
                            <div className="inline-flex items-center gap-2">
                              <span className={`font-mono text-sm ${
                                candidate.interview_prep_tokens > 0 ? 'text-white' : 'text-zinc-600'
                              }`}>
                                {candidate.interview_prep_tokens}
                              </span>
                              <button
                                onClick={() => handleOpenTokenModal(candidate.user_id)}
                                className="w-5 h-5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-white flex items-center justify-center transition-colors"
                              >
                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                                </svg>
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
                                    className={`px-2 py-0.5 text-[10px] rounded transition-colors ${
                                      isSelected
                                        ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                                        : 'bg-zinc-800 text-zinc-500 border border-zinc-700 hover:border-zinc-600'
                                    }`}
                                  >
                                    {role.label}
                                  </button>
                                );
                              })}
                            </div>
                          </td>

                          {/* Sessions Count */}
                          <td className="px-4 py-4 text-center">
                            <span className="text-sm text-zinc-300 font-mono">
                              {candidate.total_sessions}
                            </span>
                          </td>

                          {/* Avg Score */}
                          <td className="px-4 py-4 text-center">
                            <span className={`text-sm font-mono ${getScoreColor(candidate.avg_score)}`}>
                              {candidate.avg_score !== null ? `${candidate.avg_score}%` : '—'}
                            </span>
                          </td>

                          {/* Last Session */}
                          <td className="px-5 py-4 text-right">
                            <span className="text-xs text-zinc-500 font-mono">
                              {formatDate(candidate.last_session_at)}
                            </span>
                          </td>
                        </tr>

                        {/* Expanded Sessions */}
                        {isExpanded && (
                          <tr key={`${candidate.user_id}-expanded`}>
                            <td colSpan={7} className="bg-zinc-950/50 border-b border-zinc-800">
                              <div className="px-5 py-4">
                                {loadingSessions ? (
                                  <div className="flex items-center gap-2 text-zinc-500 text-sm">
                                    <div className="w-3 h-3 border border-zinc-600 border-t-zinc-400 rounded-full animate-spin" />
                                    Loading sessions...
                                  </div>
                                ) : sessions.length === 0 ? (
                                  <div className="text-zinc-600 text-sm font-mono">
                                    No sessions yet
                                  </div>
                                ) : (
                                  <div className="space-y-2">
                                    <div className="text-[10px] uppercase tracking-widest text-zinc-600 mb-3">
                                      Session History
                                    </div>
                                    <div className="grid gap-2">
                                      {sessions.map(session => (
                                        <div
                                          key={session.session_id}
                                          className="flex items-center justify-between px-4 py-3 bg-zinc-900/50 border border-zinc-800/50 rounded"
                                        >
                                          <div className="flex items-center gap-4">
                                            <div className="text-xs text-zinc-500 font-mono w-24">
                                              {formatDate(session.created_at)}
                                            </div>
                                            <div className="text-sm text-zinc-300">
                                              {session.interview_role || 'Interview Prep'}
                                            </div>
                                            <div className="text-xs text-zinc-600 font-mono">
                                              {session.duration_minutes}min
                                            </div>
                                          </div>
                                          <div className="flex items-center gap-6">
                                            <div className="text-right">
                                              <div className="text-[10px] uppercase text-zinc-600">Response</div>
                                              <div className={`text-sm font-mono ${getScoreColor(session.response_quality_score)}`}>
                                                {session.response_quality_score !== null
                                                  ? `${session.response_quality_score}%`
                                                  : '—'}
                                              </div>
                                            </div>
                                            <div className="text-right">
                                              <div className="text-[10px] uppercase text-zinc-600">Communication</div>
                                              <div className={`text-sm font-mono ${getScoreColor(session.communication_score)}`}>
                                                {session.communication_score !== null
                                                  ? `${session.communication_score}%`
                                                  : '—'}
                                              </div>
                                            </div>
                                            <div className={`px-2 py-0.5 text-[10px] uppercase tracking-wide rounded ${
                                              session.status === 'completed'
                                                ? 'bg-emerald-500/10 text-emerald-400'
                                                : session.status === 'analyzing'
                                                ? 'bg-amber-500/10 text-amber-400'
                                                : 'bg-zinc-700/50 text-zinc-400'
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
        </CardContent>
      </Card>

      {/* Token Award Modal */}
      <Modal
        isOpen={tokenModalOpen}
        onClose={() => setTokenModalOpen(false)}
        title="Award Tokens"
      >
        <div className="space-y-4">
          <p className="text-sm text-zinc-400">
            Each token allows one interview prep session (5 or 8 minutes).
          </p>
          <div>
            <label className="block text-xs text-zinc-500 uppercase tracking-wide mb-2">
              Number of tokens
            </label>
            <input
              type="number"
              min="1"
              value={tokenAmount}
              onChange={e => setTokenAmount(e.target.value)}
              className="w-full px-4 py-3 bg-zinc-950 border border-zinc-700 text-white font-mono text-center text-lg focus:outline-none focus:border-zinc-500 transition-colors"
            />
          </div>
          <div className="flex gap-3 pt-2">
            <Button
              variant="secondary"
              onClick={() => setTokenModalOpen(false)}
              className="flex-1"
            >
              Cancel
            </Button>
            <Button
              onClick={handleAwardTokens}
              disabled={awarding || !tokenAmount || parseInt(tokenAmount) <= 0}
              className="flex-1"
            >
              {awarding ? 'Awarding...' : `Award ${tokenAmount} Token${parseInt(tokenAmount) !== 1 ? 's' : ''}`}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

export default InterviewPrepAdmin;
