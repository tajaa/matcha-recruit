import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { projects as projectsApi, companies as companiesApi } from '../api/client';
import { useAuth } from '../context/AuthContext';
import type { Project, ProjectStatus, ProjectCreate, Company } from '../types';
import { Plus, Trash2, FolderOpen, Loader2, X } from 'lucide-react';

const STATUS_TABS: { label: string; value: ProjectStatus | 'all' }[] = [
  { label: 'All', value: 'all' },
  { label: 'Active', value: 'active' },
  { label: 'Draft', value: 'draft' },
  { label: 'Completed', value: 'completed' },
];

const STATUS_STYLE: Record<ProjectStatus, string> = {
  draft:     'text-zinc-400 bg-zinc-800 border-zinc-700',
  active:    'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
  closing:   'text-amber-400 bg-amber-500/10 border-amber-500/20',
  completed: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
  cancelled: 'text-red-400 bg-red-500/10 border-red-500/20',
};

function formatSalary(min?: number | null, max?: number | null): string | null {
  if (!min && !max) return null;
  const fmt = (n: number) => `$${(n / 1000).toFixed(0)}k`;
  if (min && max) return `${fmt(min)}–${fmt(max)}`;
  if (min) return `${fmt(min)}+`;
  return `Up to ${fmt(max!)}`;
}

export function Projects() {
  const navigate = useNavigate();
  const { user, profile } = useAuth();
  const [projectList, setProjectList] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<ProjectStatus | 'all'>('all');
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [companyList, setCompanyList] = useState<Company[]>([]);

  // For client users, extract their company_id from profile
  const clientCompanyId = user?.role === 'client'
    ? (profile as { company_id?: string } | null)?.company_id ?? null
    : null;

  const [form, setForm] = useState<ProjectCreate>({
    company_name: '',
    name: '',
    company_id: clientCompanyId ?? undefined,
    position_title: '',
    location: '',
    salary_min: undefined,
    salary_max: undefined,
    salary_hidden: false,
    is_public: false,
    description: '',
    currency: 'USD',
    closing_date: undefined,
    benefits: '',
    requirements: '',
    notes: '',
  });

  const fetchProjects = useCallback(async () => {
    try {
      setLoading(true);
      const data = await projectsApi.list(activeTab !== 'all' ? { status: activeTab } : {});
      setProjectList(data);
    } catch (err) {
      console.error('Failed to fetch projects:', err);
    } finally {
      setLoading(false);
    }
  }, [activeTab]);

  useEffect(() => { fetchProjects(); }, [fetchProjects]);

  // Admins can link to any company; fetch the list once
  useEffect(() => {
    if (user?.role === 'admin') {
      companiesApi.list().then(setCompanyList).catch(() => {});
    }
  }, [user?.role]);

  const handleCreate = async () => {
    if (!form.company_name.trim() || !form.name.trim()) return;
    setCreating(true);
    try {
      const created = await projectsApi.create({
        ...form,
        salary_min: form.salary_min || undefined,
        salary_max: form.salary_max || undefined,
      });
      setShowCreate(false);
      setForm({ company_name: '', name: '', company_id: clientCompanyId ?? undefined, position_title: '', location: '', salary_min: undefined, salary_max: undefined, salary_hidden: false, is_public: false, description: '', currency: 'USD', closing_date: undefined, benefits: '', requirements: '', notes: '' });
      navigate(`/app/projects/${created.id}`);
    } catch (err) {
      console.error('Failed to create project:', err);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Delete this project and all its data?')) return;
    setDeletingId(id);
    try {
      await projectsApi.delete(id);
      setProjectList(prev => prev.filter(p => p.id !== id));
    } catch (err) {
      console.error('Failed to delete project:', err);
    } finally {
      setDeletingId(null);
    }
  };

  const displayed = projectList;

  return (
    <div className="max-w-7xl mx-auto space-y-10">
      {/* Header */}
      <div className="flex justify-between items-start border-b border-white/10 pb-8">
        <div>
          <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">Recruiting Projects</h1>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">
            Create pipelines · Send interview invites · Track candidate progress
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-white text-black text-[10px] font-bold uppercase tracking-widest hover:bg-zinc-200 transition-colors"
        >
          <Plus size={12} /> New Project
        </button>
      </div>

      {/* Status tabs */}
      <div className="flex gap-8 border-b border-white/10 pb-px">
        {STATUS_TABS.map(tab => (
          <button
            key={tab.value}
            onClick={() => setActiveTab(tab.value)}
            className={`pb-3 text-[10px] font-bold uppercase tracking-widest transition-colors border-b-2 ${
              activeTab === tab.value
                ? 'border-white text-white'
                : 'border-transparent text-zinc-500 hover:text-zinc-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {loading ? (
        <div className="p-16 text-center">
          <Loader2 size={20} className="animate-spin text-zinc-500 mx-auto" />
        </div>
      ) : displayed.length === 0 ? (
        <div className="p-16 text-center bg-zinc-950 border border-white/10">
          <FolderOpen size={32} className="text-zinc-700 mx-auto mb-4" />
          <div className="text-xs text-zinc-500 uppercase tracking-wider mb-2">
            {activeTab === 'all' ? 'No projects yet' : `No ${activeTab} projects`}
          </div>
          <div className="text-xs text-zinc-600 mb-6">
            Create a project to start building your candidate pipeline and sending interview invites.
          </div>
          <button
            onClick={() => setShowCreate(true)}
            className="px-4 py-2 text-[10px] font-bold uppercase tracking-widest text-black bg-white hover:bg-zinc-200 transition-colors"
          >
            Create First Project
          </button>
        </div>
      ) : (
        <div className="space-y-px bg-white/10 border border-white/10">
          {/* Table header */}
          <div className="grid grid-cols-[2fr_1fr_1fr_80px_80px_36px] gap-4 px-6 py-3 bg-zinc-950 text-[10px] text-zinc-500 uppercase tracking-widest border-b border-white/10">
            <div>Project / Company</div>
            <div>Position</div>
            <div>Location · Salary</div>
            <div className="text-center">Status</div>
            <div className="text-center">Candidates</div>
            <div />
          </div>

          {displayed.map(project => (
            <div
              key={project.id}
              onClick={() => navigate(`/app/projects/${project.id}`)}
              className="grid grid-cols-[2fr_1fr_1fr_80px_80px_36px] gap-4 px-6 py-4 bg-zinc-950 hover:bg-zinc-900 transition-colors cursor-pointer items-center"
            >
              <div className="min-w-0">
                <div className="text-sm font-bold text-white truncate">{project.name}</div>
                <div className="text-xs text-zinc-500 font-mono truncate mt-0.5">{project.company_name}</div>
              </div>

              <div className="text-xs text-zinc-400 truncate">
                {project.position_title || <span className="text-zinc-700">—</span>}
              </div>

              <div className="min-w-0">
                <div className="text-xs text-zinc-400 truncate">{project.location || <span className="text-zinc-700">—</span>}</div>
                {formatSalary(project.salary_min, project.salary_max) && (
                  <div className="text-[10px] text-zinc-600 font-mono mt-0.5">
                    {formatSalary(project.salary_min, project.salary_max)}
                  </div>
                )}
              </div>

              <div className="flex justify-center">
                <span className={`px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider border rounded-sm ${STATUS_STYLE[project.status]}`}>
                  {project.status}
                </span>
              </div>

              <div className="text-center text-sm font-mono text-zinc-300">
                {project.candidate_count}
              </div>

              <div className="flex justify-end">
                <button
                  onClick={(e) => handleDelete(project.id, e)}
                  disabled={deletingId === project.id}
                  className="p-1.5 text-zinc-600 hover:text-red-400 hover:bg-red-500/10 rounded transition-colors disabled:opacity-50"
                >
                  {deletingId === project.id
                    ? <Loader2 size={14} className="animate-spin" />
                    : <Trash2 size={14} />}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
          <div className="relative bg-zinc-950 border border-white/15 shadow-2xl w-full max-w-2xl mx-4 max-h-[90vh] flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-white/10 flex-shrink-0">
              <div>
                <div className="text-xs font-bold text-white uppercase tracking-wider">New Project</div>
                <div className="text-[10px] text-zinc-500 uppercase tracking-widest mt-0.5">Define the role and company details</div>
              </div>
              <button onClick={() => setShowCreate(false)} className="p-1.5 text-zinc-500 hover:text-white hover:bg-zinc-800 rounded transition-colors">
                <X size={16} />
              </button>
            </div>

            {/* Body */}
            <div className="px-6 py-5 space-y-4 overflow-y-auto flex-1">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-[10px] text-zinc-500 uppercase tracking-widest mb-1.5">Company Name *</label>
                  <input
                    type="text"
                    value={form.company_name}
                    onChange={e => setForm({ ...form, company_name: e.target.value })}
                    placeholder="e.g., Acme Corp"
                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 focus:border-zinc-500 text-sm text-white placeholder-zinc-600 outline-none transition-colors"
                  />
                </div>
                <div>
                  <label className="block text-[10px] text-zinc-500 uppercase tracking-widest mb-1.5">Project Name *</label>
                  <input
                    type="text"
                    value={form.name}
                    onChange={e => setForm({ ...form, name: e.target.value })}
                    placeholder="e.g., Senior Engineer Search"
                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 focus:border-zinc-500 text-sm text-white placeholder-zinc-600 outline-none transition-colors"
                  />
                </div>
              </div>

              {/* Company link — admins pick from list, clients auto-linked */}
              {user?.role === 'admin' && companyList.length > 0 && (
                <div>
                  <label className="block text-[10px] text-zinc-500 uppercase tracking-widest mb-1.5">
                    Link to Company Profile
                    <span className="ml-2 text-zinc-700 normal-case tracking-normal">for rankings</span>
                  </label>
                  <select
                    value={form.company_id ?? ''}
                    onChange={e => {
                      const val = e.target.value;
                      const company = companyList.find(c => c.id === val);
                      setForm({
                        ...form,
                        company_id: val || undefined,
                        company_name: company?.name ?? form.company_name,
                      });
                    }}
                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 focus:border-zinc-500 text-sm text-white outline-none transition-colors"
                  >
                    <option value="">— No company link —</option>
                    {companyList.map(c => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                  <p className="text-[9px] text-zinc-600 mt-1">Linking enables candidate rankings scoped to this project</p>
                </div>
              )}
              {user?.role === 'client' && clientCompanyId && (
                <div className="px-3 py-2 bg-emerald-500/5 border border-emerald-500/20 text-[10px] text-emerald-400 uppercase tracking-widest">
                  ✓ Linked to your company — rankings will be available
                </div>
              )}

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-[10px] text-zinc-500 uppercase tracking-widest mb-1.5">Position Title</label>
                  <input
                    type="text"
                    value={form.position_title || ''}
                    onChange={e => setForm({ ...form, position_title: e.target.value })}
                    placeholder="e.g., Software Engineer"
                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 focus:border-zinc-500 text-sm text-white placeholder-zinc-600 outline-none transition-colors"
                  />
                </div>
                <div>
                  <label className="block text-[10px] text-zinc-500 uppercase tracking-widest mb-1.5">Location</label>
                  <input
                    type="text"
                    value={form.location || ''}
                    onChange={e => setForm({ ...form, location: e.target.value })}
                    placeholder="e.g., Los Angeles, CA"
                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 focus:border-zinc-500 text-sm text-white placeholder-zinc-600 outline-none transition-colors"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-[10px] text-zinc-500 uppercase tracking-widest mb-1.5">Salary Min</label>
                  <input
                    type="number"
                    value={form.salary_min || ''}
                    onChange={e => setForm({ ...form, salary_min: e.target.value ? parseInt(e.target.value) : undefined })}
                    placeholder="80000"
                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 focus:border-zinc-500 text-sm text-white placeholder-zinc-600 outline-none transition-colors"
                  />
                </div>
                <div>
                  <label className="block text-[10px] text-zinc-500 uppercase tracking-widest mb-1.5">Salary Max</label>
                  <input
                    type="number"
                    value={form.salary_max || ''}
                    onChange={e => setForm({ ...form, salary_max: e.target.value ? parseInt(e.target.value) : undefined })}
                    placeholder="120000"
                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 focus:border-zinc-500 text-sm text-white placeholder-zinc-600 outline-none transition-colors"
                  />
                </div>
              </div>

              {/* Salary options row */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-[10px] text-zinc-500 uppercase tracking-widest mb-1.5">Currency</label>
                  <select
                    value={form.currency || 'USD'}
                    onChange={e => setForm({ ...form, currency: e.target.value })}
                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 focus:border-zinc-500 text-sm text-white outline-none transition-colors"
                  >
                    <option value="USD">USD ($)</option>
                    <option value="EUR">EUR (€)</option>
                    <option value="GBP">GBP (£)</option>
                    <option value="CAD">CAD (CA$)</option>
                    <option value="AUD">AUD (AU$)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] text-zinc-500 uppercase tracking-widest mb-1.5">Applications Close</label>
                  <input
                    type="date"
                    value={form.closing_date ? form.closing_date.split('T')[0] : ''}
                    onChange={e => setForm({ ...form, closing_date: e.target.value ? e.target.value + 'T23:59:59' : undefined })}
                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 focus:border-zinc-500 text-sm text-white outline-none transition-colors"
                  />
                </div>
              </div>

              {/* Public toggles */}
              <div className="flex items-center gap-6">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form.is_public || false}
                    onChange={e => setForm({ ...form, is_public: e.target.checked })}
                    className="w-4 h-4 accent-matcha-500"
                  />
                  <span className="text-[10px] text-zinc-400 uppercase tracking-widest">Accept public applications</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form.salary_hidden || false}
                    onChange={e => setForm({ ...form, salary_hidden: e.target.checked })}
                    className="w-4 h-4 accent-matcha-500"
                  />
                  <span className="text-[10px] text-zinc-400 uppercase tracking-widest">Hide salary</span>
                </label>
              </div>

              <div>
                <label className="block text-[10px] text-zinc-500 uppercase tracking-widest mb-1.5">Description</label>
                <textarea
                  value={form.description || ''}
                  onChange={e => setForm({ ...form, description: e.target.value })}
                  placeholder="Describe the role and what the candidate will work on..."
                  rows={3}
                  className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 focus:border-zinc-500 text-sm text-white placeholder-zinc-600 outline-none transition-colors resize-none"
                />
              </div>

              <div>
                <label className="block text-[10px] text-zinc-500 uppercase tracking-widest mb-1.5">Requirements</label>
                <textarea
                  value={form.requirements || ''}
                  onChange={e => setForm({ ...form, requirements: e.target.value })}
                  placeholder="Skills, experience, qualifications..."
                  rows={3}
                  className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 focus:border-zinc-500 text-sm text-white placeholder-zinc-600 outline-none transition-colors resize-none"
                />
              </div>

              <div>
                <label className="block text-[10px] text-zinc-500 uppercase tracking-widest mb-1.5">Benefits</label>
                <textarea
                  value={form.benefits || ''}
                  onChange={e => setForm({ ...form, benefits: e.target.value })}
                  placeholder="Health, 401k, equity..."
                  rows={2}
                  className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 focus:border-zinc-500 text-sm text-white placeholder-zinc-600 outline-none transition-colors resize-none"
                />
              </div>

              <div>
                <label className="block text-[10px] text-zinc-500 uppercase tracking-widest mb-1.5">Internal Notes</label>
                <textarea
                  value={form.notes || ''}
                  onChange={e => setForm({ ...form, notes: e.target.value })}
                  placeholder="Private notes visible only to admins..."
                  rows={2}
                  className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 focus:border-zinc-500 text-sm text-white placeholder-zinc-600 outline-none transition-colors resize-none"
                />
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-white/10 flex-shrink-0">
              <button
                onClick={() => setShowCreate(false)}
                className="px-4 py-2 text-[10px] font-bold uppercase tracking-widest text-zinc-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={creating || !form.company_name.trim() || !form.name.trim()}
                className="inline-flex items-center gap-2 px-4 py-2 text-[10px] font-bold uppercase tracking-widest bg-white text-black hover:bg-zinc-200 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {creating ? <><Loader2 size={11} className="animate-spin" /> Creating…</> : 'Create Project'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default Projects;
