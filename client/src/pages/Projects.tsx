import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Card, CardContent, Modal } from '../components';
import { projects as projectsApi, type ProjectFilters } from '../api/client';
import type { Project, ProjectStatus, ProjectCreate } from '../types';

const STATUS_TABS: { label: string; value: ProjectStatus | 'all' }[] = [
  { label: 'All', value: 'all' },
  { label: 'Draft', value: 'draft' },
  { label: 'Active', value: 'active' },
  { label: 'Completed', value: 'completed' },
];

const STATUS_COLORS: Record<ProjectStatus, string> = {
  draft: 'bg-zinc-700 text-zinc-300',
  active: 'bg-matcha-500/20 text-white',
  completed: 'bg-blue-500/20 text-blue-400',
  cancelled: 'bg-red-500/20 text-red-400',
};

export function Projects() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<ProjectStatus | 'all'>('all');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [creating, setCreating] = useState(false);

  // Form state
  const [formData, setFormData] = useState<ProjectCreate>({
    company_name: '',
    name: '',
    position_title: '',
    location: '',
    salary_min: undefined,
    salary_max: undefined,
    benefits: '',
    requirements: '',
    notes: '',
  });

  const fetchProjects = useCallback(async () => {
    try {
      setLoading(true);
      const filters: ProjectFilters = {};
      if (activeTab !== 'all') {
        filters.status = activeTab;
      }
      const data = await projectsApi.list(filters);
      setProjects(data);
    } catch (err) {
      console.error('Failed to fetch projects:', err);
    } finally {
      setLoading(false);
    }
  }, [activeTab]);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  const handleCreate = async () => {
    if (!formData.company_name.trim() || !formData.name.trim()) return;

    setCreating(true);
    try {
      const created = await projectsApi.create({
        ...formData,
        salary_min: formData.salary_min || undefined,
        salary_max: formData.salary_max || undefined,
      });
      setShowCreateModal(false);
      setFormData({
        company_name: '',
        name: '',
        position_title: '',
        location: '',
        salary_min: undefined,
        salary_max: undefined,
        benefits: '',
        requirements: '',
        notes: '',
      });
      navigate(`/app/projects/${created.id}`);
    } catch (err) {
      console.error('Failed to create project:', err);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Delete this project?')) return;
    try {
      await projectsApi.delete(id);
      fetchProjects();
    } catch (err) {
      console.error('Failed to delete project:', err);
    }
  };

  const formatSalary = (min?: number | null, max?: number | null) => {
    if (!min && !max) return null;
    const fmt = (n: number) => `$${(n / 1000).toFixed(0)}k`;
    if (min && max) return `${fmt(min)} - ${fmt(max)}`;
    if (min) return `${fmt(min)}+`;
    return `Up to ${fmt(max!)}`;
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold text-white tracking-tight">Projects</h1>
        <Button onClick={() => setShowCreateModal(true)}>New Project</Button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 bg-zinc-900 p-1 rounded-lg w-fit">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setActiveTab(tab.value)}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
              activeTab === tab.value
                ? 'bg-zinc-800 text-white'
                : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-center py-12 text-zinc-500">Loading...</div>
      ) : projects.length === 0 ? (
        <Card>
          <CardContent className="text-center py-12">
            <svg
              className="mx-auto h-12 w-12 text-zinc-600"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
              />
            </svg>
            <p className="mt-4 text-zinc-500">
              {activeTab === 'all' ? 'No projects yet' : `No ${activeTab} projects`}
            </p>
            <Button className="mt-4" onClick={() => setShowCreateModal(true)}>
              Create Your First Project
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
          {/* Table Header */}
          <div className="grid grid-cols-[1.5fr_1fr_1fr_100px_80px_100px_50px] gap-4 px-4 py-3 bg-zinc-800/50 border-b border-zinc-700 text-xs font-medium text-zinc-400 uppercase tracking-wider">
            <div>Project</div>
            <div>Position</div>
            <div>Location</div>
            <div>Salary</div>
            <div>Status</div>
            <div>Candidates</div>
            <div></div>
          </div>

          {/* Table Body */}
          <div className="divide-y divide-zinc-800">
            {projects.map((project) => (
              <div
                key={project.id}
                onClick={() => navigate(`/app/projects/${project.id}`)}
                className="grid grid-cols-[1.5fr_1fr_1fr_100px_80px_100px_50px] gap-4 px-4 py-3 items-center hover:bg-zinc-800/30 transition-colors cursor-pointer"
              >
                <div className="min-w-0">
                  <div className="font-medium text-zinc-100 truncate">{project.name}</div>
                  <div className="text-sm text-zinc-500 truncate">{project.company_name}</div>
                </div>
                <div className="text-zinc-400 text-sm truncate">
                  {project.position_title || '-'}
                </div>
                <div className="text-zinc-400 text-sm truncate">
                  {project.location || '-'}
                </div>
                <div className="text-zinc-400 text-sm">
                  {formatSalary(project.salary_min, project.salary_max) || '-'}
                </div>
                <div>
                  <span className={`px-2 py-0.5 text-xs font-medium rounded ${STATUS_COLORS[project.status]}`}>
                    {project.status}
                  </span>
                </div>
                <div className="text-zinc-400 text-sm">
                  {project.candidate_count}
                </div>
                <div className="flex justify-end">
                  <button
                    onClick={(e) => handleDelete(project.id, e)}
                    className="text-zinc-600 hover:text-red-400 transition-colors p-1"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                      />
                    </svg>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Create Project Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="New Project"
      >
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Company Name *</label>
              <input
                type="text"
                value={formData.company_name}
                onChange={(e) => setFormData({ ...formData, company_name: e.target.value })}
                placeholder="e.g., Urth Caffe"
                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-white"
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Project Name *</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="e.g., General Manager Search"
                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-white"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Position Title</label>
              <input
                type="text"
                value={formData.position_title || ''}
                onChange={(e) => setFormData({ ...formData, position_title: e.target.value })}
                placeholder="e.g., General Manager"
                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-white"
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Location</label>
              <input
                type="text"
                value={formData.location || ''}
                onChange={(e) => setFormData({ ...formData, location: e.target.value })}
                placeholder="e.g., Los Angeles, CA"
                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-white"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Salary Min ($)</label>
              <input
                type="number"
                value={formData.salary_min || ''}
                onChange={(e) => setFormData({ ...formData, salary_min: e.target.value ? parseInt(e.target.value) : undefined })}
                placeholder="e.g., 80000"
                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-white"
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Salary Max ($)</label>
              <input
                type="number"
                value={formData.salary_max || ''}
                onChange={(e) => setFormData({ ...formData, salary_max: e.target.value ? parseInt(e.target.value) : undefined })}
                placeholder="e.g., 100000"
                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-white"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs text-zinc-500 mb-1">Requirements</label>
            <textarea
              value={formData.requirements || ''}
              onChange={(e) => setFormData({ ...formData, requirements: e.target.value })}
              placeholder="What the company is looking for..."
              rows={3}
              className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-white resize-none"
            />
          </div>

          <div>
            <label className="block text-xs text-zinc-500 mb-1">Benefits</label>
            <textarea
              value={formData.benefits || ''}
              onChange={(e) => setFormData({ ...formData, benefits: e.target.value })}
              placeholder="Health insurance, 401k, etc..."
              rows={2}
              className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-white resize-none"
            />
          </div>

          <div>
            <label className="block text-xs text-zinc-500 mb-1">Notes</label>
            <textarea
              value={formData.notes || ''}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
              placeholder="Internal notes..."
              rows={2}
              className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-white resize-none"
            />
          </div>

          <div className="flex justify-end gap-3 pt-4">
            <Button variant="secondary" onClick={() => setShowCreateModal(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleCreate}
              disabled={creating || !formData.company_name.trim() || !formData.name.trim()}
            >
              {creating ? 'Creating...' : 'Create Project'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

export default Projects;
