import { useState, useEffect } from 'react';
import { getAccessToken } from '../api/client';
import { Plus, X, Edit2, Trash2, CheckCircle, FileText, Laptop, GraduationCap, Settings, AlertTriangle, RotateCcw } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

interface OnboardingTemplate {
  id: string;
  title: string;
  description: string | null;
  category: 'documents' | 'equipment' | 'training' | 'admin' | 'return_to_work';
  is_employee_task: boolean;
  due_days: number;
  is_active: boolean;
  sort_order: number;
  created_at: string;
}

interface NewTemplate {
  title: string;
  description: string;
  category: string;
  is_employee_task: boolean;
  due_days: number;
  sort_order: number;
}

const CATEGORIES = [
  { value: 'documents', label: 'Documents', icon: FileText, color: 'text-blue-400' },
  { value: 'equipment', label: 'Equipment', icon: Laptop, color: 'text-purple-400' },
  { value: 'training', label: 'Training', icon: GraduationCap, color: 'text-amber-400' },
  { value: 'admin', label: 'Admin', icon: Settings, color: 'text-zinc-400' },
  { value: 'return_to_work', label: 'Return to Work', icon: RotateCcw, color: 'text-emerald-400' },
];

export default function OnboardingTemplates() {
  const [templates, setTemplates] = useState<OnboardingTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<OnboardingTemplate | null>(null);
  const [categoryFilter, setCategoryFilter] = useState<string>('');
  const [submitting, setSubmitting] = useState(false);

  const [formData, setFormData] = useState<NewTemplate>({
    title: '',
    description: '',
    category: 'admin',
    is_employee_task: true,
    due_days: 7,
    sort_order: 0,
  });

  const fetchTemplates = async () => {
    try {
      const token = getAccessToken();
      const url = categoryFilter
        ? `${API_BASE}/onboarding/templates?category=${categoryFilter}`
        : `${API_BASE}/onboarding/templates`;

      const response = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to fetch templates');
      }
      const data = await response.json();
      setTemplates(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTemplates();
  }, [categoryFilter]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);

    try {
      const token = getAccessToken();
      const url = editingTemplate
        ? `${API_BASE}/onboarding/templates/${editingTemplate.id}`
        : `${API_BASE}/onboarding/templates`;

      const response = await fetch(url, {
        method: editingTemplate ? 'PUT' : 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to save template');
      }

      setShowModal(false);
      setEditingTemplate(null);
      setFormData({
        title: '',
        description: '',
        category: 'admin',
        is_employee_task: true,
        due_days: 7,
        sort_order: 0,
      });
      fetchTemplates();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (templateId: string) => {
    if (!confirm('Are you sure you want to delete this template?')) return;

    try {
      const token = getAccessToken();
      const response = await fetch(`${API_BASE}/onboarding/templates/${templateId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!response.ok) throw new Error('Failed to delete template');
      fetchTemplates();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    }
  };

  const handleToggleActive = async (template: OnboardingTemplate) => {
    try {
      const token = getAccessToken();
      const response = await fetch(`${API_BASE}/onboarding/templates/${template.id}`, {
        method: 'PUT',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ is_active: !template.is_active }),
      });

      if (!response.ok) throw new Error('Failed to update template');
      fetchTemplates();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    }
  };

  const openEditModal = (template: OnboardingTemplate) => {
    setEditingTemplate(template);
    setFormData({
      title: template.title,
      description: template.description || '',
      category: template.category,
      is_employee_task: template.is_employee_task,
      due_days: template.due_days,
      sort_order: template.sort_order,
    });
    setShowModal(true);
  };

  const groupedTemplates = templates.reduce((acc, template) => {
    const cat = template.category;
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(template);
    return acc;
  }, {} as Record<string, OnboardingTemplate[]>);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-xs text-zinc-500 light:text-black/60 uppercase tracking-wider animate-pulse">Loading templates...</div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/10 pb-8">
        <div>
          <h1 className="text-3xl md:text-4xl font-bold tracking-tighter text-white light:text-black uppercase text-center sm:text-left">Onboarding Templates</h1>
          <p className="text-xs text-zinc-500 light:text-black/60 mt-2 font-mono tracking-wide uppercase text-center sm:text-left">
            Manage tasks assigned to new employees
          </p>
        </div>
        <button
          onClick={() => {
            setEditingTemplate(null);
            setFormData({
              title: '',
              description: '',
              category: 'admin',
              is_employee_task: true,
              due_days: 7,
              sort_order: 0,
            });
            setShowModal(true);
          }}
          className="flex items-center justify-center gap-2 px-6 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors w-full sm:w-auto"
        >
          <Plus size={14} />
          Add Template
        </button>
      </div>

      {/* Error message */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded p-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <AlertTriangle className="text-red-400 shrink-0" size={16} />
            <p className="text-sm text-red-400 font-mono">{error}</p>
          </div>
          <button
            onClick={() => setError(null)}
            className="text-xs text-red-400 hover:text-red-300 uppercase tracking-wider font-bold shrink-0"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Category filter */}
      <div className="border-b border-white/10 -mx-4 px-4 sm:mx-0 sm:px-0">
        <nav className="-mb-px flex space-x-8 overflow-x-auto pb-px no-scrollbar">
          {[{ value: '', label: 'All' }, ...CATEGORIES].map((cat) => (
            <button
              key={cat.value}
              onClick={() => setCategoryFilter(cat.value)}
              className={`pb-4 px-1 border-b-2 text-xs font-bold uppercase tracking-wider transition-colors whitespace-nowrap ${
                categoryFilter === cat.value
                  ? 'border-white text-white light:text-black'
                  : 'border-transparent text-zinc-500 light:text-black/60 hover:text-zinc-300 hover:border-zinc-800'
              }`}
            >
              {cat.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Templates grouped by category */}
      {templates.length === 0 ? (
        <div className="text-center py-24 border border-dashed border-white/10 bg-white/5">
          <div className="w-16 h-16 mx-auto mb-6 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center">
            <CheckCircle size={24} className="text-zinc-600" />
          </div>
          <h3 className="text-white light:text-black text-sm font-bold mb-1 uppercase tracking-wide">Create your first template</h3>
          <p className="text-zinc-500 light:text-black/60 text-xs mb-6 font-mono uppercase">You haven't defined any onboarding tasks yet. Build your first checklist to get started.</p>
        </div>
      ) : (
        <div className="space-y-8">
          {CATEGORIES.filter(cat => !categoryFilter || cat.value === categoryFilter).map((cat) => {
            const categoryTemplates = groupedTemplates[cat.value] || [];
            if (categoryTemplates.length === 0) return null;

            return (
              <div key={cat.value}>
                <div className="flex items-center gap-2 mb-4">
                  <cat.icon size={16} className={cat.color} />
                  <h2 className="text-sm font-bold uppercase tracking-wider text-white light:text-black">{cat.label}</h2>
                  <span className="text-xs text-zinc-500 light:text-black/60 font-mono">({categoryTemplates.length})</span>
                </div>
                <div className="space-y-px bg-white/10 border border-white/10">
                  {categoryTemplates.map((template) => (
                    <div
                      key={template.id}
                      className={`group bg-zinc-950 hover:bg-zinc-900 transition-colors p-4 flex flex-col sm:flex-row sm:items-center gap-4 ${
                        !template.is_active ? 'opacity-50' : ''
                      }`}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-bold text-white light:text-black truncate">{template.title}</p>
                          {!template.is_active && (
                            <span className="text-[10px] px-2 py-0.5 bg-zinc-800 text-zinc-500 light:text-black/60 uppercase tracking-wider rounded">
                              Inactive
                            </span>
                          )}
                        </div>
                        {template.description && (
                          <p className="text-xs text-zinc-500 light:text-black/60 truncate mt-1">{template.description}</p>
                        )}
                      </div>
                      <div className="flex items-center justify-between sm:justify-end gap-4 md:gap-8 border-t border-white/5 pt-3 sm:border-0 sm:pt-0">
                        <div className="text-left sm:text-right">
                          <p className="text-[10px] text-zinc-500 light:text-black/60 uppercase tracking-wider">Due</p>
                          <p className="text-xs text-zinc-400 font-mono">{template.due_days} days</p>
                        </div>
                        <div className="text-left sm:text-right">
                          <p className="text-[10px] text-zinc-500 light:text-black/60 uppercase tracking-wider">Assigned to</p>
                          <p className="text-xs text-zinc-400">
                            {template.is_employee_task ? 'Employee' : 'HR/Manager'}
                          </p>
                        </div>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => handleToggleActive(template)}
                            className={`p-2 rounded transition-colors ${
                              template.is_active
                                ? 'text-emerald-400 hover:bg-emerald-500/10'
                                : 'text-zinc-500 light:text-black/60 hover:bg-zinc-800'
                            }`}
                            title={template.is_active ? 'Deactivate' : 'Activate'}
                          >
                            <CheckCircle size={16} />
                          </button>
                          <button
                            onClick={() => openEditModal(template)}
                            className="p-2 text-zinc-400 hover:text-white light:text-black hover:bg-zinc-800 rounded transition-colors"
                            title="Edit"
                          >
                            <Edit2 size={16} />
                          </button>
                          <button
                            onClick={() => handleDelete(template.id)}
                            className="p-2 text-zinc-400 hover:text-red-400 hover:bg-red-500/10 rounded transition-colors"
                            title="Delete"
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Add/Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg bg-zinc-950 border border-zinc-800 shadow-2xl rounded-sm">
            <div className="flex items-center justify-between p-6 border-b border-white/10">
              <h3 className="text-xl font-bold text-white light:text-black uppercase tracking-tight">
                {editingTemplate ? 'Edit Template' : 'Add Template'}
              </h3>
              <button
                onClick={() => setShowModal(false)}
                className="text-zinc-500 light:text-black/60 hover:text-white light:text-black transition-colors"
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="p-8 space-y-6">
              <div>
                <label className="block text-[10px] uppercase tracking-wider text-zinc-500 light:text-black/60 mb-1.5">
                  Title <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={formData.title}
                  onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                  className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white light:text-black text-sm focus:outline-none focus:border-white/20 transition-colors"
                />
              </div>

              <div>
                <label className="block text-[10px] uppercase tracking-wider text-zinc-500 light:text-black/60 mb-1.5">
                  Description
                </label>
                <textarea
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  rows={3}
                  className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white light:text-black text-sm focus:outline-none focus:border-white/20 transition-colors resize-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-[10px] uppercase tracking-wider text-zinc-500 light:text-black/60 mb-1.5">
                    Category
                  </label>
                  <select
                    value={formData.category}
                    onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white light:text-black text-sm focus:outline-none focus:border-white/20 transition-colors"
                  >
                    {CATEGORIES.map((cat) => (
                      <option key={cat.value} value={cat.value}>
                        {cat.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-wider text-zinc-500 light:text-black/60 mb-1.5">
                    Due (days from start)
                  </label>
                  <input
                    type="number"
                    min="0"
                    value={formData.due_days}
                    onChange={(e) => setFormData({ ...formData, due_days: parseInt(e.target.value) || 0 })}
                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white light:text-black text-sm focus:outline-none focus:border-white/20 transition-colors"
                  />
                </div>
              </div>

              <div className="flex items-center gap-3">
                <input
                  type="checkbox"
                  id="is_employee_task"
                  checked={formData.is_employee_task}
                  onChange={(e) => setFormData({ ...formData, is_employee_task: e.target.checked })}
                  className="w-4 h-4 bg-zinc-900 border border-zinc-800 rounded"
                />
                <label htmlFor="is_employee_task" className="text-sm text-zinc-400">
                  Employee completes this task (vs HR/Manager)
                </label>
              </div>

              <div className="flex justify-end gap-3 pt-6 border-t border-white/10">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 text-zinc-500 light:text-black/60 hover:text-white light:text-black text-xs font-bold uppercase tracking-wider transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-6 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors disabled:opacity-50"
                >
                  {submitting ? 'Saving...' : editingTemplate ? 'Update' : 'Create'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
