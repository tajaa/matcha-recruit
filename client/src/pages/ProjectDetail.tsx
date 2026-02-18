import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { projects as projectsApi, candidates as candidatesApi, api } from '../api/client';
import type {
  Project,
  ProjectCandidate,
  ProjectStats,
  ProjectStatus,
  CandidateStage,
  Candidate,
  ProjectUpdate,
  Outreach,
  RankedCandidate,
  ReachOutDraft,
} from '../types';
import {
  ArrowLeft, Send, Mail, BarChart2, Loader2, X, ChevronRight,
  CheckCircle2, Clock, AlertCircle, XCircle, UserPlus, RefreshCw,
  ShieldCheck, Star,
} from 'lucide-react';

// ─── Config ─────────────────────────────────────────────────────────────────

const STAGES: { value: CandidateStage; label: string }[] = [
  { value: 'initial',   label: 'Initial'   },
  { value: 'screening', label: 'Screening' },
  { value: 'interview', label: 'Interview' },
  { value: 'finalist',  label: 'Finalist'  },
  { value: 'placed',    label: 'Placed'    },
  { value: 'rejected',  label: 'Rejected'  },
];

const STAGE_STYLE: Record<CandidateStage, string> = {
  initial:   'text-zinc-400 bg-zinc-800 border-zinc-700',
  screening: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
  interview: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
  finalist:  'text-violet-400 bg-violet-500/10 border-violet-500/20',
  placed:    'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
  rejected:  'text-red-400 bg-red-500/10 border-red-500/20',
};

const STATUS_OPTIONS: ProjectStatus[] = ['draft', 'active', 'completed', 'cancelled'];

function formatSalary(min?: number | null, max?: number | null): string {
  if (!min && !max) return 'Not specified';
  const fmt = (n: number) => `$${n.toLocaleString()}`;
  if (min && max) return `${fmt(min)} – ${fmt(max)}`;
  if (min) return `${fmt(min)}+`;
  return `Up to ${fmt(max!)}`;
}

function OutreachBadge({ outreach }: { outreach: Outreach }) {
  if (outreach.status === 'screening_complete') {
    const rec = outreach.screening_recommendation;
    if (rec === 'strong_pass' || rec === 'pass') {
      return (
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
          <CheckCircle2 size={9} /> {rec === 'strong_pass' ? 'Strong Pass' : 'Pass'} · {Math.round(outreach.screening_score || 0)}
        </span>
      );
    }
    if (rec === 'borderline') {
      return (
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider bg-amber-500/10 border border-amber-500/20 text-amber-400">
          <AlertCircle size={9} /> Borderline · {Math.round(outreach.screening_score || 0)}
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider bg-red-500/10 border border-red-500/20 text-red-400">
        <XCircle size={9} /> Fail · {Math.round(outreach.screening_score || 0)}
      </span>
    );
  }
  if (outreach.status === 'screening_started' || outreach.status === 'interested') {
    return (
      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider bg-blue-500/10 border border-blue-500/20 text-blue-400">
        <Clock size={9} /> {outreach.status === 'screening_started' ? 'In Progress' : 'Interested'}
      </span>
    );
  }
  if (outreach.status === 'declined') {
    return (
      <span className="px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider bg-zinc-800 border border-zinc-700 text-zinc-500">
        Declined
      </span>
    );
  }
  if (outreach.status === 'screening_invited') {
    return (
      <span className="px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider bg-violet-500/10 border border-violet-500/20 text-violet-400">
        Invite Sent
      </span>
    );
  }
  return (
    <span className="px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider bg-zinc-800 border border-zinc-700 text-zinc-500">
      {outreach.status === 'opened' ? 'Opened' : 'Sent'}
    </span>
  );
}

// ─── Component ───────────────────────────────────────────────────────────────

export function ProjectDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [project, setProject] = useState<Project | null>(null);
  const [candidateList, setCandidateList] = useState<ProjectCandidate[]>([]);
  const [stats, setStats] = useState<ProjectStats | null>(null);
  const [outreachRecords, setOutreachRecords] = useState<Outreach[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeStage, setActiveStage] = useState<CandidateStage | 'all'>('all');

  // Add candidates modal
  const [showAddModal, setShowAddModal] = useState(false);
  const [availableCandidates, setAvailableCandidates] = useState<Candidate[]>([]);
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<string[]>([]);
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [adding, setAdding] = useState(false);
  const [addSearch, setAddSearch] = useState('');

  // Edit modal
  const [showEditModal, setShowEditModal] = useState(false);
  const [editData, setEditData] = useState<ProjectUpdate>({});
  const [saving, setSaving] = useState(false);

  // Outreach modal
  const [showOutreachModal, setShowOutreachModal] = useState(false);
  const [outreachCandidateIds, setOutreachCandidateIds] = useState<string[]>([]);
  const [sendingOutreach, setSendingOutreach] = useState(false);
  const [customMessage, setCustomMessage] = useState('');
  const [outreachResult, setOutreachResult] = useState<string | null>(null);

  // Screening modal
  const [showScreeningModal, setShowScreeningModal] = useState(false);
  const [screeningCandidateIds, setScreeningCandidateIds] = useState<string[]>([]);
  const [sendingScreening, setSendingScreening] = useState(false);
  const [screeningMessage, setScreeningMessage] = useState('');
  const [screeningResult, setScreeningResult] = useState<string | null>(null);

  // Rankings
  const [rankings, setRankings] = useState<RankedCandidate[]>([]);
  const [rankingsLoading, setRankingsLoading] = useState(false);
  const [rankingsRunning, setRankingsRunning] = useState(false);

  // Reach-out modal (within rankings)
  const [reachOutTarget, setReachOutTarget] = useState<RankedCandidate | null>(null);
  const [reachOutDraft, setReachOutDraft] = useState<ReachOutDraft | null>(null);
  const [reachOutLoading, setReachOutLoading] = useState(false);
  const [reachOutSending, setReachOutSending] = useState(false);
  const [reachOutSent, setReachOutSent] = useState<Set<string>>(new Set());
  const [editedSubject, setEditedSubject] = useState('');
  const [editedBody, setEditedBody] = useState('');

  // ─── Data fetching ──────────────────────────────────────────────────────────

  const fetchProject = useCallback(async () => {
    if (!id) return;
    const data = await projectsApi.get(id);
    setProject(data);
    setEditData({
      company_name: data.company_name,
      name: data.name,
      position_title: data.position_title || '',
      location: data.location || '',
      salary_min: data.salary_min || undefined,
      salary_max: data.salary_max || undefined,
      benefits: data.benefits || '',
      requirements: data.requirements || '',
      notes: data.notes || '',
      status: data.status,
    });
  }, [id]);

  const fetchCandidates = useCallback(async () => {
    if (!id) return;
    const stage = activeStage === 'all' ? undefined : activeStage;
    const data = await projectsApi.listCandidates(id, stage);
    setCandidateList(data);
  }, [id, activeStage]);

  const fetchStats = useCallback(async () => {
    if (!id) return;
    const data = await projectsApi.getStats(id);
    setStats(data);
  }, [id]);

  const fetchOutreach = useCallback(async () => {
    if (!id) return;
    const data = await projectsApi.listOutreach(id);
    setOutreachRecords(data);
  }, [id]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        await Promise.all([fetchProject(), fetchCandidates(), fetchStats(), fetchOutreach()]);
      } catch (err) {
        console.error('Failed to load project:', err);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [fetchProject, fetchCandidates, fetchStats, fetchOutreach]);

  useEffect(() => { fetchCandidates(); }, [activeStage, fetchCandidates]);

  // ─── Helpers ────────────────────────────────────────────────────────────────

  const getOutreachStatus = (candidateId: string) =>
    outreachRecords.find(o => o.candidate_id === candidateId);

  const outreachCandidateSet = new Set(outreachRecords.map(o => o.candidate_id));

  const outreachEligible = candidateList.filter(
    c => c.stage === 'initial' && !outreachCandidateSet.has(c.candidate_id)
  );

  const screeningEligible = candidateList.filter(
    c => !outreachCandidateSet.has(c.candidate_id)
  );

  const outreachStats = {
    sent:       outreachRecords.filter(o => o.status === 'sent' || o.status === 'opened').length,
    interested: outreachRecords.filter(o => o.status === 'interested' || o.status === 'screening_started').length,
    screened:   outreachRecords.filter(o => o.status === 'screening_complete').length,
    invited:    outreachRecords.filter(o => o.status === 'screening_invited').length,
    declined:   outreachRecords.filter(o => o.status === 'declined').length,
    total:      outreachRecords.length,
  };

  // ─── Handlers ────────────────────────────────────────────────────────────────

  const openAddModal = async () => {
    setShowAddModal(true);
    setLoadingCandidates(true);
    setSelectedCandidateIds([]);
    setAddSearch('');
    try {
      const all = await candidatesApi.list();
      const existingIds = new Set(candidateList.map(c => c.candidate_id));
      setAvailableCandidates(all.filter(c => !existingIds.has(c.id)));
    } catch (err) {
      console.error('Failed to load candidates:', err);
    } finally {
      setLoadingCandidates(false);
    }
  };

  const filteredAvailable = availableCandidates.filter(c => {
    if (!addSearch.trim()) return true;
    const s = addSearch.toLowerCase();
    return c.name?.toLowerCase().includes(s) || c.email?.toLowerCase().includes(s);
  });

  const handleAddCandidates = async () => {
    if (!id || selectedCandidateIds.length === 0) return;
    setAdding(true);
    try {
      await projectsApi.bulkAddCandidates(id, { candidate_ids: selectedCandidateIds });
      setShowAddModal(false);
      setSelectedCandidateIds([]);
      await Promise.all([fetchCandidates(), fetchStats()]);
    } catch (err) {
      console.error('Failed to add candidates:', err);
    } finally {
      setAdding(false);
    }
  };

  const handleStageChange = async (candidateId: string, newStage: CandidateStage) => {
    if (!id) return;
    try {
      await projectsApi.updateCandidate(id, candidateId, { stage: newStage });
      await Promise.all([fetchCandidates(), fetchStats()]);
    } catch (err) {
      console.error('Failed to update stage:', err);
    }
  };

  const handleRemoveCandidate = async (candidateId: string) => {
    if (!id || !confirm('Remove this candidate from the project?')) return;
    try {
      await projectsApi.removeCandidate(id, candidateId);
      await Promise.all([fetchCandidates(), fetchStats()]);
    } catch (err) {
      console.error('Failed to remove candidate:', err);
    }
  };

  const handleSaveProject = async () => {
    if (!id) return;
    setSaving(true);
    try {
      await projectsApi.update(id, editData);
      await fetchProject();
      setShowEditModal(false);
    } catch (err) {
      console.error('Failed to save project:', err);
    } finally {
      setSaving(false);
    }
  };

  const handleStatusChange = async (newStatus: ProjectStatus) => {
    if (!id) return;
    try {
      await projectsApi.update(id, { status: newStatus });
      await fetchProject();
    } catch (err) {
      console.error('Failed to update status:', err);
    }
  };

  const fetchRankings = async (companyId: string) => {
    setRankingsLoading(true);
    try {
      // Filter to only candidates in this project
      const projectCandidateIds = new Set(candidateList.map(c => c.candidate_id));
      const all = await api.rankings.list(companyId);
      setRankings(all.filter(r => projectCandidateIds.has(r.candidate_id)));
    } catch (err) {
      console.error('Failed to fetch rankings:', err);
    } finally {
      setRankingsLoading(false);
    }
  };

  const handleRunRankings = async () => {
    if (!project?.company_id) return;
    setRankingsRunning(true);
    try {
      const candidateIds = candidateList.map(c => c.candidate_id);
      const result = await api.rankings.run(project.company_id, candidateIds);
      setRankings(result.rankings);
    } catch (err) {
      console.error('Failed to run rankings:', err);
    } finally {
      setRankingsRunning(false);
    }
  };

  const handleOpenReachOut = async (candidate: RankedCandidate) => {
    if (!project?.company_id) return;
    setReachOutTarget(candidate);
    setReachOutDraft(null);
    setEditedSubject('');
    setEditedBody('');
    setReachOutLoading(true);
    try {
      const draft = await api.reachOut.draft(project.company_id, candidate.candidate_id);
      setReachOutDraft(draft);
      setEditedSubject(draft.subject);
      setEditedBody(draft.body);
    } catch (err) {
      console.error('Failed to draft reach-out:', err);
      setReachOutTarget(null);
    } finally {
      setReachOutLoading(false);
    }
  };

  const handleSendReachOut = async () => {
    if (!reachOutTarget || !reachOutDraft || !project?.company_id) return;
    setReachOutSending(true);
    try {
      await api.reachOut.send(project.company_id, reachOutTarget.candidate_id, {
        to_email: reachOutDraft.to_email,
        subject: editedSubject,
        body: editedBody,
      });
      setReachOutSent(prev => new Set(prev).add(reachOutTarget.candidate_id));
      setReachOutTarget(null);
      setReachOutDraft(null);
    } catch (err) {
      console.error('Failed to send reach-out:', err);
    } finally {
      setReachOutSending(false);
    }
  };

  const openOutreachModal = () => {
    setOutreachCandidateIds(outreachEligible.map(c => c.candidate_id));
    setCustomMessage('');
    setOutreachResult(null);
    setShowOutreachModal(true);
  };

  const openScreeningModal = () => {
    setScreeningCandidateIds(screeningEligible.map(c => c.candidate_id));
    setScreeningMessage('');
    setScreeningResult(null);
    setShowScreeningModal(true);
  };

  const handleSendOutreach = async () => {
    if (!id || outreachCandidateIds.length === 0) return;
    setSendingOutreach(true);
    setOutreachResult(null);
    try {
      const result = await projectsApi.sendOutreach(id, {
        candidate_ids: outreachCandidateIds,
        custom_message: customMessage || undefined,
      });
      setOutreachResult(`✓ Sent ${result.sent_count} · Skipped ${result.skipped_count} · Failed ${result.failed_count}`);
      await fetchOutreach();
      setTimeout(() => setShowOutreachModal(false), 2000);
    } catch (err) {
      console.error('Failed to send outreach:', err);
      setOutreachResult('Failed to send outreach. Please try again.');
    } finally {
      setSendingOutreach(false);
    }
  };

  const handleSendScreening = async () => {
    if (!id || screeningCandidateIds.length === 0) return;
    setSendingScreening(true);
    setScreeningResult(null);
    try {
      const result = await projectsApi.sendScreeningInvite(id, {
        candidate_ids: screeningCandidateIds,
        custom_message: screeningMessage || undefined,
      });
      setScreeningResult(`✓ Sent ${result.sent_count} · Skipped ${result.skipped_count} · Failed ${result.failed_count}`);
      await fetchOutreach();
      setTimeout(() => setShowScreeningModal(false), 2000);
    } catch (err) {
      console.error('Failed to send screening invites:', err);
      setScreeningResult('Failed to send invites. Please try again.');
    } finally {
      setSendingScreening(false);
    }
  };

  // ─── Render ─────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <Loader2 size={20} className="animate-spin text-zinc-500" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="text-center py-16">
        <div className="text-xs text-zinc-500 uppercase tracking-wider mb-4">Project not found</div>
        <button
          onClick={() => navigate('/app/projects')}
          className="text-[10px] text-zinc-400 hover:text-white uppercase tracking-widest underline underline-offset-4"
        >
          Back to Projects
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto space-y-8">

      {/* Header */}
      <div className="border-b border-white/10 pb-8">
        <button
          onClick={() => navigate('/app/projects')}
          className="inline-flex items-center gap-1.5 text-[10px] text-zinc-500 hover:text-white uppercase tracking-widest mb-4 transition-colors"
        >
          <ArrowLeft size={12} /> Projects
        </button>

        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">{project.name}</h1>
            <p className="text-sm text-zinc-500 mt-1 font-mono">{project.company_name}</p>
            {project.position_title && (
              <p className="text-xs text-zinc-600 mt-1 uppercase tracking-widest">{project.position_title}</p>
            )}
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            {/* Status selector */}
            <select
              value={project.status}
              onChange={e => handleStatusChange(e.target.value as ProjectStatus)}
              className="px-3 py-1.5 bg-zinc-900 border border-zinc-700 text-[10px] text-zinc-300 uppercase tracking-widest outline-none focus:border-zinc-500"
            >
              {STATUS_OPTIONS.map(s => (
                <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
              ))}
            </select>

            <button
              onClick={() => setShowEditModal(true)}
              className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest text-zinc-300 hover:text-white bg-zinc-900 border border-zinc-700 hover:border-zinc-500 transition-colors"
            >
              Edit
            </button>

            <button
              onClick={openOutreachModal}
              disabled={outreachEligible.length === 0}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest text-zinc-300 hover:text-white bg-zinc-900 border border-zinc-700 hover:border-zinc-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              title="Send outreach email with interest link"
            >
              <Mail size={11} /> Outreach ({outreachEligible.length})
            </button>

            <button
              onClick={openScreeningModal}
              disabled={screeningEligible.length === 0}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest bg-white text-black hover:bg-zinc-200 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              title="Send direct screening interview invite"
            >
              <Send size={11} /> Send Screening ({screeningEligible.length})
            </button>
          </div>
        </div>

        {/* Quick stats strip */}
        <div className="flex items-center gap-6 mt-6 pt-6 border-t border-white/5">
          <div className="text-center">
            <div className="text-2xl font-bold text-white font-mono">{stats?.total || 0}</div>
            <div className="text-[9px] text-zinc-500 uppercase tracking-widest mt-0.5">Candidates</div>
          </div>
          {outreachStats.total > 0 && (
            <>
              <div className="w-px h-8 bg-white/10" />
              <div className="text-center">
                <div className="text-2xl font-bold text-zinc-300 font-mono">{outreachStats.total}</div>
                <div className="text-[9px] text-zinc-500 uppercase tracking-widest mt-0.5">Contacted</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-emerald-400 font-mono">{outreachStats.screened}</div>
                <div className="text-[9px] text-zinc-500 uppercase tracking-widest mt-0.5">Screened</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-red-400 font-mono">{outreachStats.declined}</div>
                <div className="text-[9px] text-zinc-500 uppercase tracking-widest mt-0.5">Declined</div>
              </div>
            </>
          )}
          <div className="ml-auto">
            <button
              onClick={() => navigate('/app/admin/candidate-metrics')}
              className="inline-flex items-center gap-1.5 text-[10px] text-zinc-500 hover:text-white uppercase tracking-widest transition-colors"
            >
              <BarChart2 size={11} /> View Metrics <ChevronRight size={10} />
            </button>
          </div>
        </div>
      </div>

      {/* Pipeline */}
      <div className="space-y-4">
        {/* Stage tabs + Add button */}
        <div className="flex items-center justify-between">
          <div className="flex gap-6 border-b border-white/10 pb-px flex-1">
            {[{ value: 'all' as const, label: 'All' }, ...STAGES].map(stage => (
              <button
                key={stage.value}
                onClick={() => setActiveStage(stage.value as CandidateStage | 'all')}
                className={`pb-3 text-[10px] font-bold uppercase tracking-widest transition-colors border-b-2 whitespace-nowrap ${
                  activeStage === stage.value
                    ? 'border-white text-white'
                    : 'border-transparent text-zinc-500 hover:text-zinc-300'
                }`}
              >
                {stage.label}
                {stage.value !== 'all' && stats && (
                  <span className="ml-1.5 text-zinc-600">({stats[stage.value as CandidateStage] || 0})</span>
                )}
                {stage.value === 'all' && (
                  <span className="ml-1.5 text-zinc-600">({stats?.total || 0})</span>
                )}
              </button>
            ))}
          </div>
          <button
            onClick={openAddModal}
            className="ml-6 inline-flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest text-zinc-300 hover:text-white bg-zinc-900 border border-zinc-700 hover:border-zinc-500 transition-colors flex-shrink-0"
          >
            <UserPlus size={11} /> Add Candidates
          </button>
        </div>

        {/* Candidate list */}
        {candidateList.length === 0 ? (
          <div className="p-12 text-center bg-zinc-950 border border-white/10">
            <div className="text-xs text-zinc-500 uppercase tracking-wider mb-2">
              {activeStage === 'all' ? 'No candidates added yet' : `No candidates in ${activeStage} stage`}
            </div>
            {activeStage === 'all' && (
              <button
                onClick={openAddModal}
                className="mt-3 text-[10px] text-zinc-400 hover:text-white uppercase tracking-widest underline underline-offset-4"
              >
                Add your first candidate
              </button>
            )}
          </div>
        ) : (
          <div className="space-y-px bg-white/10 border border-white/10">
            {/* Header row */}
            <div className="grid grid-cols-[2fr_1fr_1fr_120px_140px_32px] gap-4 px-6 py-3 bg-zinc-950 text-[10px] text-zinc-500 uppercase tracking-widest border-b border-white/10">
              <div>Candidate</div>
              <div>Experience</div>
              <div>Interview Status</div>
              <div>Stage</div>
              <div>Actions</div>
              <div />
            </div>

            {candidateList.map(pc => {
              const outreach = getOutreachStatus(pc.candidate_id);
              return (
                <div
                  key={pc.id}
                  className="grid grid-cols-[2fr_1fr_1fr_120px_140px_32px] gap-4 px-6 py-4 bg-zinc-950 hover:bg-zinc-900 transition-colors items-center"
                >
                  {/* Name */}
                  <div className="min-w-0">
                    <div className="text-sm font-bold text-white truncate">{pc.candidate_name || 'Unknown'}</div>
                    <div className="text-xs text-zinc-500 font-mono truncate mt-0.5">{pc.candidate_email}</div>
                    {pc.candidate_skills && pc.candidate_skills.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1.5">
                        {pc.candidate_skills.slice(0, 3).map(skill => (
                          <span key={skill} className="px-1.5 py-0.5 bg-zinc-900 border border-zinc-800 text-[9px] text-zinc-500 uppercase tracking-wider">
                            {skill}
                          </span>
                        ))}
                        {pc.candidate_skills.length > 3 && (
                          <span className="text-[9px] text-zinc-700">+{pc.candidate_skills.length - 3}</span>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Experience */}
                  <div className="text-xs text-zinc-400 font-mono">
                    {pc.candidate_experience_years ? `${pc.candidate_experience_years} yrs` : '—'}
                  </div>

                  {/* Outreach status */}
                  <div>
                    {outreach ? <OutreachBadge outreach={outreach} /> : (
                      <span className="text-[9px] text-zinc-700 uppercase tracking-wider">Not contacted</span>
                    )}
                  </div>

                  {/* Stage dropdown */}
                  <div>
                    <select
                      value={pc.stage}
                      onChange={e => handleStageChange(pc.candidate_id, e.target.value as CandidateStage)}
                      className={`w-full px-2 py-1 text-[9px] font-bold uppercase tracking-wider border outline-none cursor-pointer ${STAGE_STYLE[pc.stage]}`}
                      style={{ background: 'transparent' }}
                    >
                      {STAGES.map(stage => (
                        <option key={stage.value} value={stage.value} className="bg-zinc-900 text-zinc-200">
                          {stage.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2">
                    {outreach?.status === 'screening_complete' && (
                      <button
                        onClick={() => navigate(`/app/analysis/${outreach.interview_id}`)}
                        className="text-[9px] text-zinc-400 hover:text-white uppercase tracking-widest underline underline-offset-2 transition-colors whitespace-nowrap"
                      >
                        View Analysis
                      </button>
                    )}
                  </div>

                  {/* Remove */}
                  <button
                    onClick={() => handleRemoveCandidate(pc.candidate_id)}
                    className="p-1 text-zinc-700 hover:text-red-400 transition-colors"
                    title="Remove from project"
                  >
                    <X size={13} />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ─── Rankings section ─────────────────────────────────────────────────── */}
      {project.company_id ? (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold mb-1 flex items-center gap-2">
                <Star size={11} /> Candidate Rankings
              </div>
              <div className="text-xs text-zinc-600">Scoring · Culture alignment · Conversation quality</div>
            </div>
            <button
              onClick={handleRunRankings}
              disabled={rankingsRunning || candidateList.length === 0}
              className="inline-flex items-center gap-2 px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest bg-zinc-900 border border-zinc-700 hover:border-zinc-500 text-zinc-300 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {rankingsRunning
                ? <><Loader2 size={11} className="animate-spin" /> Scoring…</>
                : <><RefreshCw size={11} /> Run Rankings</>}
            </button>
          </div>

          {rankings.length === 0 && !rankingsLoading ? (
            <div className="p-10 text-center bg-zinc-950 border border-white/10">
              <div className="text-xs text-zinc-500 uppercase tracking-wider mb-2">No rankings yet</div>
              <div className="text-xs text-zinc-600 mb-4">
                {candidateList.length === 0
                  ? 'Add candidates to this project first'
                  : 'Click "Run Rankings" to score candidates against this company\'s culture profile'}
              </div>
              {rankings.length === 0 && candidateList.length > 0 && (
                <button
                  onClick={() => project.company_id && fetchRankings(project.company_id)}
                  className="text-[10px] text-zinc-400 hover:text-white uppercase tracking-widest underline underline-offset-4"
                >
                  Load existing rankings
                </button>
              )}
            </div>
          ) : rankingsLoading ? (
            <div className="p-10 text-center bg-zinc-950 border border-white/10">
              <Loader2 size={16} className="animate-spin text-zinc-500 mx-auto" />
            </div>
          ) : (
            <div className="space-y-px bg-white/10 border border-white/10">
              {/* Header */}
              <div className="grid grid-cols-[36px_2fr_80px_200px_120px] gap-4 px-6 py-3 bg-zinc-950 text-[10px] text-zinc-500 uppercase tracking-widest border-b border-white/10">
                <div>#</div>
                <div>Candidate</div>
                <div className="text-right">Score</div>
                <div>Signals</div>
                <div className="text-right">Action</div>
              </div>

              {rankings.map((r, idx) => (
                <div key={r.id} className="grid grid-cols-[36px_2fr_80px_200px_120px] gap-4 px-6 py-4 bg-zinc-950 hover:bg-zinc-900 transition-colors items-center">
                  {/* Rank badge */}
                  <div className={`w-8 h-8 rounded border flex items-center justify-center text-[10px] font-bold font-mono flex-shrink-0 ${
                    idx === 0 ? 'bg-amber-500/20 border-amber-400/40 text-amber-300'
                    : idx === 1 ? 'bg-zinc-400/10 border-zinc-400/30 text-zinc-300'
                    : idx === 2 ? 'bg-orange-700/20 border-orange-600/30 text-orange-400'
                    : 'bg-zinc-800/60 border-zinc-700/50 text-zinc-500'
                  }`}>
                    {idx + 1}
                  </div>

                  {/* Name */}
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-bold text-white truncate">{r.candidate_name || 'Unknown'}</span>
                      {r.has_interview_data && (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider bg-teal-500/10 border border-teal-500/20 text-teal-400">
                          <ShieldCheck size={9} /> Verified
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Score */}
                  <div className="text-right">
                    <span className={`text-xl font-bold font-mono ${
                      r.overall_rank_score >= 80 ? 'text-emerald-400'
                      : r.overall_rank_score >= 60 ? 'text-amber-400'
                      : 'text-red-400'
                    }`}>
                      {Math.round(r.overall_rank_score)}
                    </span>
                  </div>

                  {/* Signal bars */}
                  <div className="space-y-1">
                    {[
                      { label: 'Screening', score: r.screening_score, color: 'bg-emerald-500' },
                      { label: 'Culture', score: r.culture_alignment_score, color: 'bg-violet-500' },
                      { label: 'Conversation', score: r.conversation_score, color: 'bg-cyan-500' },
                    ].map(({ label, score, color }) => (
                      <div key={label} className="space-y-0.5">
                        <div className="flex justify-between text-[9px]">
                          <span className="text-zinc-600 uppercase tracking-wider">{label}</span>
                          <span className="font-mono text-zinc-500">{score !== null ? Math.round(score) : '—'}</span>
                        </div>
                        <div className="h-0.5 bg-zinc-800 rounded-full overflow-hidden">
                          {score !== null && <div className={`h-full ${color}`} style={{ width: `${Math.min(score, 100)}%` }} />}
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Reach Out action */}
                  <div className="flex justify-end">
                    {reachOutSent.has(r.candidate_id) ? (
                      <span className="inline-flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider text-teal-400">
                        <CheckCircle2 size={10} /> Sent
                      </span>
                    ) : (
                      <button
                        onClick={() => handleOpenReachOut(r)}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-[9px] font-bold uppercase tracking-wider text-zinc-300 hover:text-white bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 hover:border-zinc-500 transition-colors"
                      >
                        <Mail size={10} /> Reach Out
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="p-6 bg-zinc-950 border border-white/10 flex items-center gap-4">
          <Star size={16} className="text-zinc-700 flex-shrink-0" />
          <div>
            <div className="text-xs text-zinc-500 uppercase tracking-wider mb-1">Rankings not available</div>
            <div className="text-xs text-zinc-600">
              Link this project to a company profile to enable candidate rankings.
              Edit the project and select a company to activate this feature.
            </div>
          </div>
        </div>
      )}

      {/* Reach-out modal */}
      {reachOutTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
          <div className="relative bg-zinc-950 border border-white/15 shadow-2xl w-full max-w-2xl mx-4">
            <div className="flex items-center justify-between px-6 py-4 border-b border-white/10">
              <div>
                <div className="text-xs font-bold text-white uppercase tracking-wider">
                  {reachOutTarget.candidate_name || 'Candidate'}
                </div>
                <div className="text-[10px] text-zinc-500 uppercase tracking-widest mt-0.5">Draft Reach-Out Message</div>
              </div>
              <button onClick={() => { setReachOutTarget(null); setReachOutDraft(null); }} className="p-1.5 text-zinc-500 hover:text-white hover:bg-zinc-800 rounded transition-colors">
                <X size={16} />
              </button>
            </div>
            <div className="px-6 py-5 space-y-4">
              <div className="text-sm text-zinc-400 font-mono bg-zinc-900 border border-zinc-800 px-3 py-2">
                {reachOutDraft ? `${reachOutDraft.to_name} <${reachOutDraft.to_email}>` : <span className="text-zinc-600 italic">Loading…</span>}
              </div>
              {reachOutDraft && (
                <div className="inline-flex items-center gap-1.5 px-2 py-1 bg-violet-500/10 border border-violet-500/20 text-violet-400 text-[9px] font-bold uppercase tracking-widest">
                  ✦ AI-generated — edit as needed
                </div>
              )}
              <div>
                <label className="block text-[10px] text-zinc-500 uppercase tracking-widest mb-1.5">Subject</label>
                {reachOutLoading
                  ? <div className="h-9 bg-zinc-800 animate-pulse" />
                  : <input type="text" value={editedSubject} onChange={e => setEditedSubject(e.target.value)} className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 focus:border-zinc-500 text-sm text-white outline-none" />}
              </div>
              <div>
                <label className="block text-[10px] text-zinc-500 uppercase tracking-widest mb-1.5">Message</label>
                {reachOutLoading
                  ? <div className="h-48 bg-zinc-800 animate-pulse" />
                  : <textarea value={editedBody} onChange={e => setEditedBody(e.target.value)} rows={10} className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 focus:border-zinc-500 text-sm text-white outline-none resize-none leading-relaxed" />}
              </div>
            </div>
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-white/10">
              <button onClick={() => { setReachOutTarget(null); setReachOutDraft(null); }} className="px-4 py-2 text-[10px] font-bold uppercase tracking-widest text-zinc-400 hover:text-white">
                Cancel
              </button>
              <button
                onClick={handleSendReachOut}
                disabled={reachOutLoading || reachOutSending || !reachOutDraft}
                className="inline-flex items-center gap-2 px-4 py-2 text-[10px] font-bold uppercase tracking-widest bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white transition-colors"
              >
                {reachOutSending ? <><Loader2 size={11} className="animate-spin" /> Sending…</> : <><Mail size={11} /> Send Message</>}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── Project details strip ─────────────────────────────────────────────── */}
      {(project.requirements || project.benefits || project.notes) && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-px bg-white/10 border border-white/10">
          {project.requirements && (
            <div className="bg-zinc-950 p-6">
              <div className="text-[9px] uppercase tracking-widest text-zinc-500 font-bold mb-3">Requirements</div>
              <p className="text-xs text-zinc-400 whitespace-pre-wrap leading-relaxed">{project.requirements}</p>
            </div>
          )}
          {project.benefits && (
            <div className="bg-zinc-950 p-6">
              <div className="text-[9px] uppercase tracking-widest text-zinc-500 font-bold mb-3">Benefits</div>
              <p className="text-xs text-zinc-400 whitespace-pre-wrap leading-relaxed">{project.benefits}</p>
            </div>
          )}
          {project.notes && (
            <div className="bg-zinc-950 p-6">
              <div className="text-[9px] uppercase tracking-widest text-zinc-500 font-bold mb-3">Internal Notes</div>
              <p className="text-xs text-zinc-400 whitespace-pre-wrap leading-relaxed">{project.notes}</p>
            </div>
          )}
        </div>
      )}

      {/* ─── Modals ────────────────────────────────────────────────────────────── */}

      {/* Add Candidates Modal */}
      {showAddModal && (
        <Modal title="Add Candidates" subtitle="Select from your candidate database" onClose={() => setShowAddModal(false)}>
          {loadingCandidates ? (
            <div className="py-12 flex justify-center"><Loader2 size={18} className="animate-spin text-zinc-500" /></div>
          ) : (
            <>
              <input
                type="text"
                placeholder="Search by name or email…"
                value={addSearch}
                onChange={e => setAddSearch(e.target.value)}
                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 focus:border-zinc-500 text-sm text-white placeholder-zinc-600 outline-none mb-3"
              />

              <div className="flex items-center justify-between mb-2 text-[10px] text-zinc-500 uppercase tracking-widest">
                <span>
                  {filteredAvailable.length === availableCandidates.length
                    ? `${availableCandidates.length} candidates`
                    : `${filteredAvailable.length} of ${availableCandidates.length}`}
                  {selectedCandidateIds.length > 0 && ` · ${selectedCandidateIds.length} selected`}
                </span>
                <div className="flex gap-3">
                  <button onClick={() => setSelectedCandidateIds(filteredAvailable.map(c => c.id))} className="text-white hover:text-zinc-300">
                    Select All
                  </button>
                  {selectedCandidateIds.length > 0 && (
                    <button onClick={() => setSelectedCandidateIds([])} className="hover:text-zinc-300">
                      Clear
                    </button>
                  )}
                </div>
              </div>

              {filteredAvailable.length === 0 ? (
                <div className="py-8 text-center text-xs text-zinc-600">
                  {availableCandidates.length === 0 ? 'All candidates are already in this project' : 'No candidates match your search'}
                </div>
              ) : (
                <div className="max-h-72 overflow-y-auto space-y-px bg-white/5 border border-white/10">
                  {filteredAvailable.map(c => (
                    <label
                      key={c.id}
                      className={`flex items-center gap-3 px-4 py-3 cursor-pointer transition-colors ${
                        selectedCandidateIds.includes(c.id) ? 'bg-zinc-800' : 'bg-zinc-950 hover:bg-zinc-900'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={selectedCandidateIds.includes(c.id)}
                        onChange={e => {
                          setSelectedCandidateIds(e.target.checked
                            ? [...selectedCandidateIds, c.id]
                            : selectedCandidateIds.filter(id => id !== c.id));
                        }}
                        className="accent-white"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="text-sm text-white truncate">{c.name || 'Unknown'}</div>
                        <div className="text-[10px] text-zinc-500 font-mono truncate">{c.email}</div>
                      </div>
                      {c.experience_years && (
                        <div className="text-[10px] text-zinc-600 font-mono">{c.experience_years}y</div>
                      )}
                    </label>
                  ))}
                </div>
              )}

              <div className="flex justify-end gap-3 mt-4 pt-4 border-t border-white/10">
                <button onClick={() => setShowAddModal(false)} className="px-4 py-2 text-[10px] font-bold uppercase tracking-widest text-zinc-400 hover:text-white">
                  Cancel
                </button>
                <button
                  onClick={handleAddCandidates}
                  disabled={adding || selectedCandidateIds.length === 0}
                  className="inline-flex items-center gap-2 px-4 py-2 text-[10px] font-bold uppercase tracking-widest bg-white text-black hover:bg-zinc-200 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  {adding ? <><Loader2 size={11} className="animate-spin" /> Adding…</> : `Add ${selectedCandidateIds.length || ''} Candidate${selectedCandidateIds.length !== 1 ? 's' : ''}`}
                </button>
              </div>
            </>
          )}
        </Modal>
      )}

      {/* Edit Project Modal */}
      {showEditModal && (
        <Modal title="Edit Project" onClose={() => setShowEditModal(false)}>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <Field label="Company Name">
                <input type="text" value={editData.company_name || ''} onChange={e => setEditData({ ...editData, company_name: e.target.value })} className={inputCls} />
              </Field>
              <Field label="Project Name">
                <input type="text" value={editData.name || ''} onChange={e => setEditData({ ...editData, name: e.target.value })} className={inputCls} />
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Position Title">
                <input type="text" value={editData.position_title || ''} onChange={e => setEditData({ ...editData, position_title: e.target.value })} className={inputCls} />
              </Field>
              <Field label="Location">
                <input type="text" value={editData.location || ''} onChange={e => setEditData({ ...editData, location: e.target.value })} className={inputCls} />
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Salary Min ($)">
                <input type="number" value={editData.salary_min || ''} onChange={e => setEditData({ ...editData, salary_min: e.target.value ? parseInt(e.target.value) : undefined })} className={inputCls} />
              </Field>
              <Field label="Salary Max ($)">
                <input type="number" value={editData.salary_max || ''} onChange={e => setEditData({ ...editData, salary_max: e.target.value ? parseInt(e.target.value) : undefined })} className={inputCls} />
              </Field>
            </div>
            <Field label="Requirements">
              <textarea rows={3} value={editData.requirements || ''} onChange={e => setEditData({ ...editData, requirements: e.target.value })} className={`${inputCls} resize-none`} />
            </Field>
            <Field label="Benefits">
              <textarea rows={2} value={editData.benefits || ''} onChange={e => setEditData({ ...editData, benefits: e.target.value })} className={`${inputCls} resize-none`} />
            </Field>
            <Field label="Internal Notes">
              <textarea rows={2} value={editData.notes || ''} onChange={e => setEditData({ ...editData, notes: e.target.value })} className={`${inputCls} resize-none`} />
            </Field>
            <div className="flex justify-end gap-3 pt-2 border-t border-white/10">
              <button onClick={() => setShowEditModal(false)} className="px-4 py-2 text-[10px] font-bold uppercase tracking-widest text-zinc-400 hover:text-white">Cancel</button>
              <button
                onClick={handleSaveProject}
                disabled={saving}
                className="inline-flex items-center gap-2 px-4 py-2 text-[10px] font-bold uppercase tracking-widest bg-white text-black hover:bg-zinc-200 disabled:opacity-40 transition-colors"
              >
                {saving ? <><Loader2 size={11} className="animate-spin" /> Saving…</> : 'Save Changes'}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Outreach Modal */}
      {showOutreachModal && (
        <Modal
          title="Send Outreach Email"
          subtitle="Candidates receive an interest link → AI screening interview"
          onClose={() => setShowOutreachModal(false)}
        >
          <div className="space-y-4">
            <CandidateCheckList
              candidates={outreachEligible}
              selected={outreachCandidateIds}
              onChange={setOutreachCandidateIds}
              getLabel={c => `${c.candidate_name || 'Unknown'} · ${c.candidate_email || ''}`}
              getId={c => c.candidate_id}
              emptyText="No candidates eligible (all already contacted)"
            />

            <Field label="Custom Message (optional)">
              <textarea
                rows={3}
                value={customMessage}
                onChange={e => setCustomMessage(e.target.value)}
                placeholder="Add a personalized note to the outreach email…"
                className={`${inputCls} resize-none`}
              />
            </Field>

            <EmailPreviewBox project={project} note="Candidates click a link to express interest, then take the AI screening interview. No account required." />

            {outreachResult && (
              <div className={`px-4 py-3 text-[10px] font-mono border ${outreachResult.startsWith('✓') ? 'text-emerald-400 border-emerald-500/20 bg-emerald-500/10' : 'text-red-400 border-red-500/20 bg-red-500/10'}`}>
                {outreachResult}
              </div>
            )}

            <div className="flex justify-end gap-3 pt-2 border-t border-white/10">
              <button onClick={() => setShowOutreachModal(false)} className="px-4 py-2 text-[10px] font-bold uppercase tracking-widest text-zinc-400 hover:text-white">Cancel</button>
              <button
                onClick={handleSendOutreach}
                disabled={sendingOutreach || outreachCandidateIds.length === 0}
                className="inline-flex items-center gap-2 px-4 py-2 text-[10px] font-bold uppercase tracking-widest bg-white text-black hover:bg-zinc-200 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {sendingOutreach
                  ? <><Loader2 size={11} className="animate-spin" /> Sending…</>
                  : <><Mail size={11} /> Send to {outreachCandidateIds.length}</>}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Screening Modal */}
      {showScreeningModal && (
        <Modal
          title="Send Screening Interview"
          subtitle="Candidates receive a direct link to the AI screening interview"
          onClose={() => setShowScreeningModal(false)}
        >
          <div className="space-y-4">
            <CandidateCheckList
              candidates={screeningEligible}
              selected={screeningCandidateIds}
              onChange={setScreeningCandidateIds}
              getLabel={c => `${c.candidate_name || 'Unknown'} · ${c.candidate_email || ''} · ${c.stage}`}
              getId={c => c.candidate_id}
              emptyText="No candidates eligible for screening"
            />

            <Field label="Custom Message (optional)">
              <textarea
                rows={3}
                value={screeningMessage}
                onChange={e => setScreeningMessage(e.target.value)}
                placeholder="Add a personalized note to the screening invite…"
                className={`${inputCls} resize-none`}
              />
            </Field>

            <EmailPreviewBox project={project} note="Candidates need an account to access the interview. Direct link skips the interest confirmation step." highlight />

            {screeningResult && (
              <div className={`px-4 py-3 text-[10px] font-mono border ${screeningResult.startsWith('✓') ? 'text-emerald-400 border-emerald-500/20 bg-emerald-500/10' : 'text-red-400 border-red-500/20 bg-red-500/10'}`}>
                {screeningResult}
              </div>
            )}

            <div className="flex justify-end gap-3 pt-2 border-t border-white/10">
              <button onClick={() => setShowScreeningModal(false)} className="px-4 py-2 text-[10px] font-bold uppercase tracking-widest text-zinc-400 hover:text-white">Cancel</button>
              <button
                onClick={handleSendScreening}
                disabled={sendingScreening || screeningCandidateIds.length === 0}
                className="inline-flex items-center gap-2 px-4 py-2 text-[10px] font-bold uppercase tracking-widest bg-white text-black hover:bg-zinc-200 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {sendingScreening
                  ? <><Loader2 size={11} className="animate-spin" /> Sending…</>
                  : <><Send size={11} /> Send to {screeningCandidateIds.length}</>}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

// ─── Shared sub-components ───────────────────────────────────────────────────

const inputCls = 'w-full px-3 py-2 bg-zinc-900 border border-zinc-700 focus:border-zinc-500 text-sm text-white placeholder-zinc-600 outline-none transition-colors';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-[10px] text-zinc-500 uppercase tracking-widest mb-1.5">{label}</label>
      {children}
    </div>
  );
}

function Modal({ title, subtitle, onClose, children }: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="relative bg-zinc-950 border border-white/15 shadow-2xl w-full max-w-2xl mx-4 max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/10 flex-shrink-0">
          <div>
            <div className="text-xs font-bold text-white uppercase tracking-wider">{title}</div>
            {subtitle && <div className="text-[10px] text-zinc-500 uppercase tracking-widest mt-0.5">{subtitle}</div>}
          </div>
          <button onClick={onClose} className="p-1.5 text-zinc-500 hover:text-white hover:bg-zinc-800 rounded transition-colors">
            <X size={16} />
          </button>
        </div>
        <div className="px-6 py-5 overflow-y-auto flex-1">{children}</div>
      </div>
    </div>
  );
}

function CandidateCheckList<T>({
  candidates, selected, onChange, getLabel, getId, emptyText,
}: {
  candidates: T[];
  selected: string[];
  onChange: (ids: string[]) => void;
  getLabel: (c: T) => string;
  getId: (c: T) => string;
  emptyText: string;
}) {
  if (candidates.length === 0) {
    return <div className="py-6 text-center text-xs text-zinc-600">{emptyText}</div>;
  }
  return (
    <div>
      <div className="flex items-center justify-between mb-2 text-[10px] text-zinc-500 uppercase tracking-widest">
        <span>{selected.length} of {candidates.length} selected</span>
        <div className="flex gap-3">
          <button onClick={() => onChange(candidates.map(getId))} className="text-white hover:text-zinc-300">Select All</button>
          {selected.length > 0 && <button onClick={() => onChange([])} className="hover:text-zinc-300">Clear</button>}
        </div>
      </div>
      <div className="max-h-48 overflow-y-auto space-y-px bg-white/5 border border-white/10">
        {candidates.map(c => {
          const cid = getId(c);
          return (
            <label
              key={cid}
              className={`flex items-center gap-3 px-4 py-2.5 cursor-pointer transition-colors ${selected.includes(cid) ? 'bg-zinc-800' : 'bg-zinc-950 hover:bg-zinc-900'}`}
            >
              <input
                type="checkbox"
                checked={selected.includes(cid)}
                onChange={e => onChange(e.target.checked ? [...selected, cid] : selected.filter(id => id !== cid))}
                className="accent-white"
              />
              <span className="text-xs text-zinc-200 font-mono truncate">{getLabel(c)}</span>
            </label>
          );
        })}
      </div>
    </div>
  );
}

function EmailPreviewBox({ project, note, highlight }: { project: Project; note: string; highlight?: boolean }) {
  return (
    <div className={`p-4 border text-xs space-y-1 ${highlight ? 'bg-violet-500/5 border-violet-500/20' : 'bg-zinc-900 border-white/5'}`}>
      <div className="text-[9px] uppercase tracking-widest text-zinc-500 font-bold mb-2">Email will include</div>
      <div className="text-zinc-400">Position: <span className="text-zinc-200">{project.position_title || project.name}</span></div>
      <div className="text-zinc-400">Company: <span className="text-zinc-200">{project.company_name}</span></div>
      {project.location && <div className="text-zinc-400">Location: <span className="text-zinc-200">{project.location}</span></div>}
      {(project.salary_min || project.salary_max) && (
        <div className="text-zinc-400">Salary: <span className="text-zinc-200">{formatSalary(project.salary_min, project.salary_max)}</span></div>
      )}
      <div className={`pt-2 mt-2 border-t border-white/5 text-[10px] ${highlight ? 'text-violet-400' : 'text-zinc-500'}`}>{note}</div>
    </div>
  );
}

export default ProjectDetail;
