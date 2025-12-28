import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, Card, CardContent, Modal } from '../components';
import { projects as projectsApi, candidates as candidatesApi } from '../api/client';
import type {
  Project,
  ProjectCandidate,
  ProjectStats,
  ProjectStatus,
  CandidateStage,
  Candidate,
  ProjectUpdate,
  Outreach,
} from '../types';

const STAGES: { value: CandidateStage; label: string; color: string }[] = [
  { value: 'initial', label: 'Initial', color: 'bg-zinc-700' },
  { value: 'screening', label: 'Screening', color: 'bg-yellow-500/20 text-yellow-400' },
  { value: 'interview', label: 'Interview', color: 'bg-blue-500/20 text-blue-400' },
  { value: 'finalist', label: 'Finalist', color: 'bg-purple-500/20 text-purple-400' },
  { value: 'placed', label: 'Placed', color: 'bg-matcha-500/20 text-white' },
  { value: 'rejected', label: 'Rejected', color: 'bg-red-500/20 text-red-400' },
];

const STATUS_OPTIONS: ProjectStatus[] = ['draft', 'active', 'completed', 'cancelled'];

export function ProjectDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [project, setProject] = useState<Project | null>(null);
  const [candidates, setCandidates] = useState<ProjectCandidate[]>([]);
  const [stats, setStats] = useState<ProjectStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeStage, setActiveStage] = useState<CandidateStage | 'all'>('all');

  const [showAddModal, setShowAddModal] = useState(false);
  const [availableCandidates, setAvailableCandidates] = useState<Candidate[]>([]);
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<string[]>([]);
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [adding, setAdding] = useState(false);

  // Add modal filter state
  const [addSearch, setAddSearch] = useState('');
  const [addSkills, setAddSkills] = useState('');
  const [addMinExp, setAddMinExp] = useState('');
  const [addMaxExp, setAddMaxExp] = useState('');

  const [showEditModal, setShowEditModal] = useState(false);
  const [editData, setEditData] = useState<ProjectUpdate>({});
  const [saving, setSaving] = useState(false);

  // Outreach state
  const [outreachRecords, setOutreachRecords] = useState<Outreach[]>([]);
  const [showOutreachModal, setShowOutreachModal] = useState(false);
  const [outreachCandidateIds, setOutreachCandidateIds] = useState<string[]>([]);
  const [sendingOutreach, setSendingOutreach] = useState(false);
  const [customMessage, setCustomMessage] = useState('');

  // Screening invite state
  const [showScreeningModal, setShowScreeningModal] = useState(false);
  const [screeningCandidateIds, setScreeningCandidateIds] = useState<string[]>([]);
  const [sendingScreening, setSendingScreening] = useState(false);
  const [screeningMessage, setScreeningMessage] = useState('');

  const fetchProject = useCallback(async () => {
    if (!id) return;
    try {
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
    } catch (err) {
      console.error('Failed to fetch project:', err);
    }
  }, [id]);

  const fetchCandidates = useCallback(async () => {
    if (!id) return;
    try {
      const stage = activeStage === 'all' ? undefined : activeStage;
      const data = await projectsApi.listCandidates(id, stage);
      setCandidates(data);
    } catch (err) {
      console.error('Failed to fetch candidates:', err);
    }
  }, [id, activeStage]);

  const fetchStats = useCallback(async () => {
    if (!id) return;
    try {
      const data = await projectsApi.getStats(id);
      setStats(data);
    } catch (err) {
      console.error('Failed to fetch stats:', err);
    }
  }, [id]);

  const fetchOutreach = useCallback(async () => {
    if (!id) return;
    try {
      const data = await projectsApi.listOutreach(id);
      setOutreachRecords(data);
    } catch (err) {
      console.error('Failed to fetch outreach:', err);
    }
  }, [id]);

  useEffect(() => {
    const loadAll = async () => {
      setLoading(true);
      await Promise.all([fetchProject(), fetchCandidates(), fetchStats(), fetchOutreach()]);
      setLoading(false);
    };
    loadAll();
  }, [fetchProject, fetchCandidates, fetchStats, fetchOutreach]);

  useEffect(() => {
    fetchCandidates();
  }, [activeStage, fetchCandidates]);

  const openAddModal = async () => {
    setShowAddModal(true);
    setLoadingCandidates(true);
    setSelectedCandidateIds([]);
    // Reset filters
    setAddSearch('');
    setAddSkills('');
    setAddMinExp('');
    setAddMaxExp('');
    try {
      const all = await candidatesApi.list();
      // Filter out candidates already in this project
      const existingIds = new Set(candidates.map((c) => c.candidate_id));
      setAvailableCandidates(all.filter((c) => !existingIds.has(c.id)));
    } catch (err) {
      console.error('Failed to load candidates:', err);
    } finally {
      setLoadingCandidates(false);
    }
  };

  // Filter available candidates based on search criteria
  const filteredAvailableCandidates = availableCandidates.filter((c) => {
    // Search filter (name or email)
    if (addSearch.trim()) {
      const search = addSearch.toLowerCase();
      const nameMatch = c.name?.toLowerCase().includes(search);
      const emailMatch = c.email?.toLowerCase().includes(search);
      if (!nameMatch && !emailMatch) return false;
    }

    // Skills filter
    if (addSkills.trim()) {
      const searchSkills = addSkills.toLowerCase().split(',').map((s) => s.trim()).filter(Boolean);
      const candidateSkills = (c.skills || []).map((s) => s.toLowerCase());
      const hasAnySkill = searchSkills.some((skill) =>
        candidateSkills.some((cs) => cs.includes(skill))
      );
      if (!hasAnySkill) return false;
    }

    // Min experience filter
    if (addMinExp) {
      const min = parseInt(addMinExp);
      if (!c.experience_years || c.experience_years < min) return false;
    }

    // Max experience filter
    if (addMaxExp) {
      const max = parseInt(addMaxExp);
      if (!c.experience_years || c.experience_years > max) return false;
    }

    return true;
  });

  const handleSelectAll = () => {
    const filteredIds = filteredAvailableCandidates.map((c) => c.id);
    setSelectedCandidateIds(filteredIds);
  };

  const handleDeselectAll = () => {
    setSelectedCandidateIds([]);
  };

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

  // Get outreach status for a candidate
  const getOutreachStatus = (candidateId: string) => {
    return outreachRecords.find((o) => o.candidate_id === candidateId);
  };

  // Get candidates eligible for outreach (initial stage, no existing outreach)
  const getOutreachEligibleCandidates = () => {
    const outreachCandidateSet = new Set(outreachRecords.map((o) => o.candidate_id));
    return candidates.filter(
      (c) => c.stage === 'initial' && !outreachCandidateSet.has(c.candidate_id)
    );
  };

  // Get candidates eligible for screening invite (any stage, no existing outreach)
  const getScreeningEligibleCandidates = () => {
    const outreachCandidateSet = new Set(outreachRecords.map((o) => o.candidate_id));
    return candidates.filter((c) => !outreachCandidateSet.has(c.candidate_id));
  };

  // Open outreach modal with eligible candidates pre-selected
  const openOutreachModal = () => {
    const eligible = getOutreachEligibleCandidates();
    setOutreachCandidateIds(eligible.map((c) => c.candidate_id));
    setCustomMessage('');
    setShowOutreachModal(true);
  };

  // Open screening modal with eligible candidates pre-selected
  const openScreeningModal = () => {
    const eligible = getScreeningEligibleCandidates();
    setScreeningCandidateIds(eligible.map((c) => c.candidate_id));
    setScreeningMessage('');
    setShowScreeningModal(true);
  };

  // Send outreach to selected candidates
  const handleSendOutreach = async () => {
    if (!id || outreachCandidateIds.length === 0) return;
    setSendingOutreach(true);
    try {
      const result = await projectsApi.sendOutreach(id, {
        candidate_ids: outreachCandidateIds,
        custom_message: customMessage || undefined,
      });
      setShowOutreachModal(false);
      await fetchOutreach();
      alert(`Outreach sent: ${result.sent_count} successful, ${result.skipped_count} skipped, ${result.failed_count} failed`);
    } catch (err) {
      console.error('Failed to send outreach:', err);
      alert('Failed to send outreach. Please try again.');
    } finally {
      setSendingOutreach(false);
    }
  };

  // Send screening invites to selected candidates
  const handleSendScreening = async () => {
    if (!id || screeningCandidateIds.length === 0) return;
    setSendingScreening(true);
    try {
      const result = await projectsApi.sendScreeningInvite(id, {
        candidate_ids: screeningCandidateIds,
        custom_message: screeningMessage || undefined,
      });
      setShowScreeningModal(false);
      await fetchOutreach();
      alert(`Screening invites sent: ${result.sent_count} successful, ${result.skipped_count} skipped, ${result.failed_count} failed`);
    } catch (err) {
      console.error('Failed to send screening invites:', err);
      alert('Failed to send screening invites. Please try again.');
    } finally {
      setSendingScreening(false);
    }
  };

  // Outreach stats
  const outreachStats = {
    sent: outreachRecords.filter((o) => o.status === 'sent' || o.status === 'opened').length,
    interested: outreachRecords.filter((o) => o.status === 'interested' || o.status === 'screening_started').length,
    screened: outreachRecords.filter((o) => o.status === 'screening_complete').length,
    declined: outreachRecords.filter((o) => o.status === 'declined').length,
    total: outreachRecords.length,
  };

  const formatSalary = (min?: number | null, max?: number | null) => {
    if (!min && !max) return 'Not specified';
    const fmt = (n: number) => `$${n.toLocaleString()}`;
    if (min && max) return `${fmt(min)} - ${fmt(max)}`;
    if (min) return `${fmt(min)}+`;
    return `Up to ${fmt(max!)}`;
  };

  if (loading) {
    return <div className="text-center py-12 text-zinc-500">Loading...</div>;
  }

  if (!project) {
    return (
      <div className="text-center py-12">
        <p className="text-zinc-500">Project not found</p>
        <Button className="mt-4" onClick={() => navigate('/app/projects')}>
          Back to Projects
        </Button>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <button
            onClick={() => navigate('/app/projects')}
            className="text-sm text-zinc-500 hover:text-zinc-300 mb-2 flex items-center gap-1"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Back to Projects
          </button>
          <h1 className="text-3xl font-bold text-white tracking-tight">{project.name}</h1>
          <p className="text-zinc-500 mt-1">{project.company_name}</p>
        </div>
        <div className="flex gap-3">
          <Button variant="secondary" onClick={() => setShowEditModal(true)}>
            Edit
          </Button>
          <Button variant="secondary" onClick={openOutreachModal} disabled={getOutreachEligibleCandidates().length === 0}>
            Send Outreach
          </Button>
          <Button variant="secondary" onClick={openScreeningModal} disabled={getScreeningEligibleCandidates().length === 0}>
            Send Screening
          </Button>
          <Button onClick={openAddModal}>Add Candidates</Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Project Info */}
          <Card>
            <CardContent>
              <h2 className="text-lg font-semibold text-zinc-200 mb-4">Project Details</h2>
              <div className="grid grid-cols-2 gap-4 text-sm">
                {project.position_title && (
                  <div>
                    <span className="text-zinc-500">Position</span>
                    <p className="text-zinc-200">{project.position_title}</p>
                  </div>
                )}
                {project.location && (
                  <div>
                    <span className="text-zinc-500">Location</span>
                    <p className="text-zinc-200">{project.location}</p>
                  </div>
                )}
                <div>
                  <span className="text-zinc-500">Salary Range</span>
                  <p className="text-zinc-200">{formatSalary(project.salary_min, project.salary_max)}</p>
                </div>
              </div>
              {project.requirements && (
                <div className="mt-4">
                  <span className="text-sm text-zinc-500">Requirements</span>
                  <p className="text-sm text-zinc-300 mt-1 whitespace-pre-wrap">{project.requirements}</p>
                </div>
              )}
              {project.benefits && (
                <div className="mt-4">
                  <span className="text-sm text-zinc-500">Benefits</span>
                  <p className="text-sm text-zinc-300 mt-1 whitespace-pre-wrap">{project.benefits}</p>
                </div>
              )}
              {project.notes && (
                <div className="mt-4">
                  <span className="text-sm text-zinc-500">Notes</span>
                  <p className="text-sm text-zinc-300 mt-1 whitespace-pre-wrap">{project.notes}</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Candidate Pipeline */}
          <Card>
            <CardContent>
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-zinc-200">Candidate Pipeline</h2>
              </div>

              {/* Stage Tabs */}
              <div className="flex gap-1 mb-4 bg-zinc-900 p-1 rounded-lg overflow-x-auto">
                <button
                  onClick={() => setActiveStage('all')}
                  className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors whitespace-nowrap ${
                    activeStage === 'all' ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-zinc-300'
                  }`}
                >
                  All ({stats?.total || 0})
                </button>
                {STAGES.map((stage) => (
                  <button
                    key={stage.value}
                    onClick={() => setActiveStage(stage.value)}
                    className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors whitespace-nowrap ${
                      activeStage === stage.value ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-zinc-300'
                    }`}
                  >
                    {stage.label} ({stats?.[stage.value] || 0})
                  </button>
                ))}
              </div>

              {/* Candidate List */}
              {candidates.length === 0 ? (
                <div className="text-center py-8 text-zinc-500">
                  {activeStage === 'all' ? 'No candidates added yet' : `No candidates in ${activeStage} stage`}
                </div>
              ) : (
                <div className="space-y-3">
                  {candidates.map((pc) => {
                    const outreach = getOutreachStatus(pc.candidate_id);
                    return (
                    <div
                      key={pc.id}
                      className="flex items-center justify-between p-3 bg-zinc-900 rounded-lg border border-zinc-800"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="font-medium text-zinc-200 truncate">
                            {pc.candidate_name || 'Unknown'}
                          </p>
                          {outreach && (
                            <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                              outreach.status === 'screening_complete'
                                ? outreach.screening_recommendation === 'strong_pass' || outreach.screening_recommendation === 'pass'
                                  ? 'bg-matcha-500/20 text-white'
                                  : outreach.screening_recommendation === 'borderline'
                                  ? 'bg-yellow-500/20 text-yellow-400'
                                  : 'bg-red-500/20 text-red-400'
                                : outreach.status === 'interested' || outreach.status === 'screening_started'
                                ? 'bg-blue-500/20 text-blue-400'
                                : outreach.status === 'declined'
                                ? 'bg-red-500/20 text-red-400'
                                : 'bg-zinc-700 text-zinc-400'
                            }`}>
                              {outreach.status === 'screening_complete'
                                ? `${outreach.screening_recommendation} (${Math.round(outreach.screening_score || 0)}%)`
                                : outreach.status === 'interested'
                                ? 'Interested'
                                : outreach.status === 'screening_started'
                                ? 'Screening...'
                                : outreach.status === 'declined'
                                ? 'Declined'
                                : outreach.status === 'opened'
                                ? 'Opened'
                                : 'Sent'}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-3 text-xs text-zinc-500 mt-1">
                          {pc.candidate_email && <span>{pc.candidate_email}</span>}
                          {pc.candidate_experience_years && (
                            <span>{pc.candidate_experience_years} yrs exp</span>
                          )}
                        </div>
                        {pc.candidate_skills && pc.candidate_skills.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-2">
                            {pc.candidate_skills.slice(0, 4).map((skill) => (
                              <span
                                key={skill}
                                className="px-1.5 py-0.5 bg-zinc-800 text-zinc-400 rounded text-xs"
                              >
                                {skill}
                              </span>
                            ))}
                            {pc.candidate_skills.length > 4 && (
                              <span className="text-xs text-zinc-600">+{pc.candidate_skills.length - 4}</span>
                            )}
                          </div>
                        )}
                      </div>

                      <div className="flex items-center gap-2 ml-4">
                        <select
                          value={pc.stage}
                          onChange={(e) => handleStageChange(pc.candidate_id, e.target.value as CandidateStage)}
                          className="px-2 py-1 bg-zinc-800 border border-zinc-700 rounded text-xs text-zinc-200 focus:outline-none focus:border-white"
                        >
                          {STAGES.map((stage) => (
                            <option key={stage.value} value={stage.value}>
                              {stage.label}
                            </option>
                          ))}
                        </select>
                        <button
                          onClick={() => handleRemoveCandidate(pc.candidate_id)}
                          className="p-1 text-zinc-600 hover:text-red-400 transition-colors"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </div>
                    </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Status Card */}
          <Card>
            <CardContent>
              <h3 className="text-sm font-medium text-zinc-400 mb-3">Status</h3>
              <select
                value={project.status}
                onChange={(e) => handleStatusChange(e.target.value as ProjectStatus)}
                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-white"
              >
                {STATUS_OPTIONS.map((status) => (
                  <option key={status} value={status}>
                    {status.charAt(0).toUpperCase() + status.slice(1)}
                  </option>
                ))}
              </select>
            </CardContent>
          </Card>

          {/* Stats Card */}
          <Card>
            <CardContent>
              <h3 className="text-sm font-medium text-zinc-400 mb-3">Pipeline Stats</h3>
              <div className="space-y-2">
                {STAGES.filter((s) => s.value !== 'rejected').map((stage) => (
                  <div key={stage.value} className="flex justify-between text-sm">
                    <span className="text-zinc-500">{stage.label}</span>
                    <span className="text-zinc-200">{stats?.[stage.value] || 0}</span>
                  </div>
                ))}
                <div className="border-t border-zinc-800 pt-2 mt-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-zinc-500">Rejected</span>
                    <span className="text-red-400">{stats?.rejected || 0}</span>
                  </div>
                </div>
                <div className="border-t border-zinc-800 pt-2 mt-2">
                  <div className="flex justify-between text-sm font-medium">
                    <span className="text-zinc-400">Total</span>
                    <span className="text-zinc-200">{stats?.total || 0}</span>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Outreach Stats Card */}
          {outreachStats.total > 0 && (
            <Card>
              <CardContent>
                <h3 className="text-sm font-medium text-zinc-400 mb-3">Outreach Status</h3>
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-zinc-500">Pending Response</span>
                    <span className="text-zinc-200">{outreachStats.sent}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-zinc-500">Interested</span>
                    <span className="text-blue-400">{outreachStats.interested}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-zinc-500">Screened</span>
                    <span className="text-white">{outreachStats.screened}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-zinc-500">Declined</span>
                    <span className="text-red-400">{outreachStats.declined}</span>
                  </div>
                  <div className="border-t border-zinc-800 pt-2 mt-2">
                    <div className="flex justify-between text-sm font-medium">
                      <span className="text-zinc-400">Total Outreach</span>
                      <span className="text-zinc-200">{outreachStats.total}</span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Quick Actions */}
          <Card>
            <CardContent>
              <h3 className="text-sm font-medium text-zinc-400 mb-3">Quick Actions</h3>
              <div className="space-y-2">
                <Button variant="secondary" size="sm" className="w-full" onClick={openAddModal}>
                  Add Candidates
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  className="w-full"
                  onClick={openOutreachModal}
                  disabled={getOutreachEligibleCandidates().length === 0}
                >
                  Send Outreach ({getOutreachEligibleCandidates().length})
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  className="w-full"
                  onClick={openScreeningModal}
                  disabled={getScreeningEligibleCandidates().length === 0}
                >
                  Send Screening ({getScreeningEligibleCandidates().length})
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Add Candidates Modal */}
      <Modal isOpen={showAddModal} onClose={() => setShowAddModal(false)} title="Add Candidates">
        {loadingCandidates ? (
          <div className="text-center py-8 text-zinc-500">Loading candidates...</div>
        ) : availableCandidates.length === 0 ? (
          <div className="text-center py-8 text-zinc-500">
            No more candidates to add. All candidates are already in this project.
          </div>
        ) : (
          <>
            {/* Filters */}
            <div className="mb-4 p-3 bg-zinc-900 rounded-lg border border-zinc-800">
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div>
                  <label className="block text-xs text-zinc-500 mb-1">Search</label>
                  <input
                    type="text"
                    placeholder="Name or email..."
                    value={addSearch}
                    onChange={(e) => setAddSearch(e.target.value)}
                    className="w-full px-2 py-1.5 bg-zinc-800 border border-zinc-700 rounded text-xs text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-white"
                  />
                </div>
                <div>
                  <label className="block text-xs text-zinc-500 mb-1">Skills</label>
                  <input
                    type="text"
                    placeholder="python, react..."
                    value={addSkills}
                    onChange={(e) => setAddSkills(e.target.value)}
                    className="w-full px-2 py-1.5 bg-zinc-800 border border-zinc-700 rounded text-xs text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-white"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-zinc-500 mb-1">Min Experience</label>
                  <input
                    type="number"
                    placeholder="Years"
                    value={addMinExp}
                    onChange={(e) => setAddMinExp(e.target.value)}
                    className="w-full px-2 py-1.5 bg-zinc-800 border border-zinc-700 rounded text-xs text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-white"
                  />
                </div>
                <div>
                  <label className="block text-xs text-zinc-500 mb-1">Max Experience</label>
                  <input
                    type="number"
                    placeholder="Years"
                    value={addMaxExp}
                    onChange={(e) => setAddMaxExp(e.target.value)}
                    className="w-full px-2 py-1.5 bg-zinc-800 border border-zinc-700 rounded text-xs text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-white"
                  />
                </div>
              </div>
            </div>

            {/* Selection controls */}
            <div className="flex items-center justify-between mb-3">
              <div className="text-sm text-zinc-500">
                {filteredAvailableCandidates.length === availableCandidates.length
                  ? `${availableCandidates.length} candidates`
                  : `${filteredAvailableCandidates.length} of ${availableCandidates.length} candidates`}
                {selectedCandidateIds.length > 0 && ` (${selectedCandidateIds.length} selected)`}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={handleSelectAll}
                  className="text-xs text-white hover:text-white transition-colors"
                >
                  Select All ({filteredAvailableCandidates.length})
                </button>
                {selectedCandidateIds.length > 0 && (
                  <button
                    onClick={handleDeselectAll}
                    className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
                  >
                    Deselect All
                  </button>
                )}
              </div>
            </div>

            {/* Candidate list */}
            {filteredAvailableCandidates.length === 0 ? (
              <div className="text-center py-8 text-zinc-500">
                No candidates match your filters
              </div>
            ) : (
              <div className="max-h-72 overflow-y-auto space-y-2">
                {filteredAvailableCandidates.map((c) => (
                  <label
                    key={c.id}
                    className={`flex items-center p-3 rounded-lg border cursor-pointer transition-colors ${
                      selectedCandidateIds.includes(c.id)
                        ? 'bg-zinc-800 border-zinc-700'
                        : 'bg-zinc-900 border-zinc-800 hover:border-zinc-700'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={selectedCandidateIds.includes(c.id)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedCandidateIds([...selectedCandidateIds, c.id]);
                        } else {
                          setSelectedCandidateIds(selectedCandidateIds.filter((cid) => cid !== c.id));
                        }
                      }}
                      className="mr-3"
                    />
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-zinc-200 truncate">{c.name || 'Unknown'}</p>
                      <div className="flex items-center gap-3 text-xs text-zinc-500 mt-1">
                        {c.email && <span>{c.email}</span>}
                        {c.experience_years && <span>{c.experience_years} yrs exp</span>}
                      </div>
                      {c.skills && c.skills.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {c.skills.slice(0, 4).map((skill) => (
                            <span
                              key={skill}
                              className="px-1.5 py-0.5 bg-zinc-800 text-zinc-400 rounded text-xs"
                            >
                              {skill}
                            </span>
                          ))}
                          {c.skills.length > 4 && (
                            <span className="text-xs text-zinc-600">+{c.skills.length - 4}</span>
                          )}
                        </div>
                      )}
                    </div>
                  </label>
                ))}
              </div>
            )}

            <div className="flex justify-end gap-3 mt-4 pt-4 border-t border-zinc-800">
              <Button variant="secondary" onClick={() => setShowAddModal(false)}>
                Cancel
              </Button>
              <Button onClick={handleAddCandidates} disabled={adding || selectedCandidateIds.length === 0}>
                {adding ? 'Adding...' : `Add ${selectedCandidateIds.length} Candidate${selectedCandidateIds.length !== 1 ? 's' : ''}`}
              </Button>
            </div>
          </>
        )}
      </Modal>

      {/* Edit Project Modal */}
      <Modal isOpen={showEditModal} onClose={() => setShowEditModal(false)} title="Edit Project">
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Company Name</label>
              <input
                type="text"
                value={editData.company_name || ''}
                onChange={(e) => setEditData({ ...editData, company_name: e.target.value })}
                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-white"
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Project Name</label>
              <input
                type="text"
                value={editData.name || ''}
                onChange={(e) => setEditData({ ...editData, name: e.target.value })}
                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-white"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Position Title</label>
              <input
                type="text"
                value={editData.position_title || ''}
                onChange={(e) => setEditData({ ...editData, position_title: e.target.value })}
                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-white"
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Location</label>
              <input
                type="text"
                value={editData.location || ''}
                onChange={(e) => setEditData({ ...editData, location: e.target.value })}
                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-white"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Salary Min ($)</label>
              <input
                type="number"
                value={editData.salary_min || ''}
                onChange={(e) => setEditData({ ...editData, salary_min: e.target.value ? parseInt(e.target.value) : undefined })}
                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-white"
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Salary Max ($)</label>
              <input
                type="number"
                value={editData.salary_max || ''}
                onChange={(e) => setEditData({ ...editData, salary_max: e.target.value ? parseInt(e.target.value) : undefined })}
                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-white"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs text-zinc-500 mb-1">Requirements</label>
            <textarea
              value={editData.requirements || ''}
              onChange={(e) => setEditData({ ...editData, requirements: e.target.value })}
              rows={3}
              className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-white resize-none"
            />
          </div>

          <div>
            <label className="block text-xs text-zinc-500 mb-1">Benefits</label>
            <textarea
              value={editData.benefits || ''}
              onChange={(e) => setEditData({ ...editData, benefits: e.target.value })}
              rows={2}
              className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-white resize-none"
            />
          </div>

          <div>
            <label className="block text-xs text-zinc-500 mb-1">Notes</label>
            <textarea
              value={editData.notes || ''}
              onChange={(e) => setEditData({ ...editData, notes: e.target.value })}
              rows={2}
              className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-white resize-none"
            />
          </div>

          <div className="flex justify-end gap-3 pt-4">
            <Button variant="secondary" onClick={() => setShowEditModal(false)}>
              Cancel
            </Button>
            <Button onClick={handleSaveProject} disabled={saving}>
              {saving ? 'Saving...' : 'Save Changes'}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Send Outreach Modal */}
      <Modal isOpen={showOutreachModal} onClose={() => setShowOutreachModal(false)} title="Send Outreach">
        <div className="space-y-4">
          <p className="text-sm text-zinc-400">
            Send outreach emails to candidates in the Initial stage who haven't been contacted yet.
            They'll receive a link to express interest and complete a screening interview.
          </p>

          {/* Candidate selection */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="block text-xs text-zinc-500">
                Select Candidates ({outreachCandidateIds.length} selected)
              </label>
              <div className="flex gap-2">
                <button
                  onClick={() => setOutreachCandidateIds(getOutreachEligibleCandidates().map((c) => c.candidate_id))}
                  className="text-xs text-white hover:text-white transition-colors"
                >
                  Select All
                </button>
                {outreachCandidateIds.length > 0 && (
                  <button
                    onClick={() => setOutreachCandidateIds([])}
                    className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
                  >
                    Clear
                  </button>
                )}
              </div>
            </div>

            <div className="max-h-48 overflow-y-auto space-y-1 bg-zinc-900 p-2 rounded-lg border border-zinc-800">
              {getOutreachEligibleCandidates().map((pc) => (
                <label
                  key={pc.candidate_id}
                  className={`flex items-center p-2 rounded cursor-pointer transition-colors ${
                    outreachCandidateIds.includes(pc.candidate_id)
                      ? 'bg-zinc-800'
                      : 'hover:bg-zinc-800'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={outreachCandidateIds.includes(pc.candidate_id)}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setOutreachCandidateIds([...outreachCandidateIds, pc.candidate_id]);
                      } else {
                        setOutreachCandidateIds(outreachCandidateIds.filter((cid) => cid !== pc.candidate_id));
                      }
                    }}
                    className="mr-2"
                  />
                  <div className="flex-1 min-w-0">
                    <span className="text-sm text-zinc-200">{pc.candidate_name || 'Unknown'}</span>
                    {pc.candidate_email && (
                      <span className="text-xs text-zinc-500 ml-2">{pc.candidate_email}</span>
                    )}
                  </div>
                </label>
              ))}
              {getOutreachEligibleCandidates().length === 0 && (
                <p className="text-sm text-zinc-500 text-center py-4">
                  No candidates eligible for outreach
                </p>
              )}
            </div>
          </div>

          {/* Custom message */}
          <div>
            <label className="block text-xs text-zinc-500 mb-1">
              Custom Message (optional)
            </label>
            <textarea
              value={customMessage}
              onChange={(e) => setCustomMessage(e.target.value)}
              placeholder="Add a personalized note to the email..."
              rows={3}
              className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-white resize-none"
            />
          </div>

          {/* Preview info */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3">
            <h4 className="text-xs text-zinc-500 uppercase mb-2">Email will include:</h4>
            <ul className="text-sm text-zinc-400 space-y-1">
              <li>• Position: {project?.position_title || project?.name}</li>
              <li>• Company: {project?.company_name}</li>
              {project?.location && <li>• Location: {project.location}</li>}
              {(project?.salary_min || project?.salary_max) && (
                <li>• Salary: {formatSalary(project?.salary_min, project?.salary_max)}</li>
              )}
            </ul>
          </div>

          <div className="flex justify-end gap-3 pt-4">
            <Button variant="secondary" onClick={() => setShowOutreachModal(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleSendOutreach}
              disabled={sendingOutreach || outreachCandidateIds.length === 0}
            >
              {sendingOutreach
                ? 'Sending...'
                : `Send to ${outreachCandidateIds.length} Candidate${outreachCandidateIds.length !== 1 ? 's' : ''}`}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Send Screening Modal */}
      <Modal isOpen={showScreeningModal} onClose={() => setShowScreeningModal(false)} title="Send Screening Interview">
        <div className="space-y-4">
          <p className="text-sm text-zinc-400">
            Send screening interview invitations directly to candidates.
            They'll need to log in or create an account to complete the interview.
          </p>

          {/* Candidate selection */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="block text-xs text-zinc-500">
                Select Candidates ({screeningCandidateIds.length} selected)
              </label>
              <div className="flex gap-2">
                <button
                  onClick={() => setScreeningCandidateIds(getScreeningEligibleCandidates().map((c) => c.candidate_id))}
                  className="text-xs text-white hover:text-white transition-colors"
                >
                  Select All
                </button>
                {screeningCandidateIds.length > 0 && (
                  <button
                    onClick={() => setScreeningCandidateIds([])}
                    className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
                  >
                    Clear
                  </button>
                )}
              </div>
            </div>

            <div className="max-h-48 overflow-y-auto space-y-1 bg-zinc-900 p-2 rounded-lg border border-zinc-800">
              {getScreeningEligibleCandidates().map((pc) => (
                <label
                  key={pc.candidate_id}
                  className={`flex items-center p-2 rounded cursor-pointer transition-colors ${
                    screeningCandidateIds.includes(pc.candidate_id)
                      ? 'bg-zinc-800'
                      : 'hover:bg-zinc-800'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={screeningCandidateIds.includes(pc.candidate_id)}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setScreeningCandidateIds([...screeningCandidateIds, pc.candidate_id]);
                      } else {
                        setScreeningCandidateIds(screeningCandidateIds.filter((cid) => cid !== pc.candidate_id));
                      }
                    }}
                    className="mr-2"
                  />
                  <div className="flex-1 min-w-0">
                    <span className="text-sm text-zinc-200">{pc.candidate_name || 'Unknown'}</span>
                    {pc.candidate_email && (
                      <span className="text-xs text-zinc-500 ml-2">{pc.candidate_email}</span>
                    )}
                    <span className={`ml-2 px-1.5 py-0.5 rounded text-xs font-medium ${
                      pc.stage === 'interview' ? 'bg-blue-500/20 text-blue-400' :
                      pc.stage === 'screening' ? 'bg-yellow-500/20 text-yellow-400' :
                      pc.stage === 'finalist' ? 'bg-purple-500/20 text-purple-400' :
                      'bg-zinc-700 text-zinc-400'
                    }`}>
                      {pc.stage}
                    </span>
                  </div>
                </label>
              ))}
              {getScreeningEligibleCandidates().length === 0 && (
                <p className="text-sm text-zinc-500 text-center py-4">
                  No candidates eligible for screening
                </p>
              )}
            </div>
          </div>

          {/* Custom message */}
          <div>
            <label className="block text-xs text-zinc-500 mb-1">
              Custom Message (optional)
            </label>
            <textarea
              value={screeningMessage}
              onChange={(e) => setScreeningMessage(e.target.value)}
              placeholder="Add a personalized note to the email..."
              rows={3}
              className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-white resize-none"
            />
          </div>

          {/* Preview info */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3">
            <h4 className="text-xs text-zinc-500 uppercase mb-2">Email will include:</h4>
            <ul className="text-sm text-zinc-400 space-y-1">
              <li>• Position: {project?.position_title || project?.name}</li>
              <li>• Company: {project?.company_name}</li>
              {project?.location && <li>• Location: {project.location}</li>}
              {(project?.salary_min || project?.salary_max) && (
                <li>• Salary: {formatSalary(project?.salary_min, project?.salary_max)}</li>
              )}
              <li className="text-white">• Direct link to screening interview</li>
            </ul>
          </div>

          <div className="flex justify-end gap-3 pt-4">
            <Button variant="secondary" onClick={() => setShowScreeningModal(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleSendScreening}
              disabled={sendingScreening || screeningCandidateIds.length === 0}
            >
              {sendingScreening
                ? 'Sending...'
                : `Send to ${screeningCandidateIds.length} Candidate${screeningCandidateIds.length !== 1 ? 's' : ''}`}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

export default ProjectDetail;
