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
} from '../types';

const STAGES: { value: CandidateStage; label: string; color: string }[] = [
  { value: 'initial', label: 'Initial', color: 'bg-zinc-700' },
  { value: 'screening', label: 'Screening', color: 'bg-yellow-500/20 text-yellow-400' },
  { value: 'interview', label: 'Interview', color: 'bg-blue-500/20 text-blue-400' },
  { value: 'finalist', label: 'Finalist', color: 'bg-purple-500/20 text-purple-400' },
  { value: 'placed', label: 'Placed', color: 'bg-matcha-500/20 text-matcha-400' },
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

  const [showEditModal, setShowEditModal] = useState(false);
  const [editData, setEditData] = useState<ProjectUpdate>({});
  const [saving, setSaving] = useState(false);

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

  useEffect(() => {
    const loadAll = async () => {
      setLoading(true);
      await Promise.all([fetchProject(), fetchCandidates(), fetchStats()]);
      setLoading(false);
    };
    loadAll();
  }, [fetchProject, fetchCandidates, fetchStats]);

  useEffect(() => {
    fetchCandidates();
  }, [activeStage, fetchCandidates]);

  const openAddModal = async () => {
    setShowAddModal(true);
    setLoadingCandidates(true);
    setSelectedCandidateIds([]);
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
                  {candidates.map((pc) => (
                    <div
                      key={pc.id}
                      className="flex items-center justify-between p-3 bg-zinc-900 rounded-lg border border-zinc-800"
                    >
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-zinc-200 truncate">
                          {pc.candidate_name || 'Unknown'}
                        </p>
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
                          className="px-2 py-1 bg-zinc-800 border border-zinc-700 rounded text-xs text-zinc-200 focus:outline-none focus:border-matcha-500"
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
                  ))}
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
                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-matcha-500"
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

          {/* Quick Actions */}
          <Card>
            <CardContent>
              <h3 className="text-sm font-medium text-zinc-400 mb-3">Quick Actions</h3>
              <div className="space-y-2">
                <Button variant="secondary" size="sm" className="w-full" onClick={openAddModal}>
                  Add Candidates
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
            <div className="mb-4 text-sm text-zinc-500">
              Select candidates to add to this project ({selectedCandidateIds.length} selected)
            </div>
            <div className="max-h-96 overflow-y-auto space-y-2">
              {availableCandidates.map((c) => (
                <label
                  key={c.id}
                  className={`flex items-center p-3 rounded-lg border cursor-pointer transition-colors ${
                    selectedCandidateIds.includes(c.id)
                      ? 'bg-matcha-500/10 border-matcha-500/30'
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
                        setSelectedCandidateIds(selectedCandidateIds.filter((id) => id !== c.id));
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
                  </div>
                </label>
              ))}
            </div>
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
                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-matcha-500"
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Project Name</label>
              <input
                type="text"
                value={editData.name || ''}
                onChange={(e) => setEditData({ ...editData, name: e.target.value })}
                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-matcha-500"
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
                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-matcha-500"
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Location</label>
              <input
                type="text"
                value={editData.location || ''}
                onChange={(e) => setEditData({ ...editData, location: e.target.value })}
                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-matcha-500"
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
                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-matcha-500"
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Salary Max ($)</label>
              <input
                type="number"
                value={editData.salary_max || ''}
                onChange={(e) => setEditData({ ...editData, salary_max: e.target.value ? parseInt(e.target.value) : undefined })}
                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-matcha-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs text-zinc-500 mb-1">Requirements</label>
            <textarea
              value={editData.requirements || ''}
              onChange={(e) => setEditData({ ...editData, requirements: e.target.value })}
              rows={3}
              className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-matcha-500 resize-none"
            />
          </div>

          <div>
            <label className="block text-xs text-zinc-500 mb-1">Benefits</label>
            <textarea
              value={editData.benefits || ''}
              onChange={(e) => setEditData({ ...editData, benefits: e.target.value })}
              rows={2}
              className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-matcha-500 resize-none"
            />
          </div>

          <div>
            <label className="block text-xs text-zinc-500 mb-1">Notes</label>
            <textarea
              value={editData.notes || ''}
              onChange={(e) => setEditData({ ...editData, notes: e.target.value })}
              rows={2}
              className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-matcha-500 resize-none"
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
    </div>
  );
}
