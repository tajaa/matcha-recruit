import { useState, useEffect } from 'react';
import { getAccessToken } from '../api/client';
import { Plus, X, Edit2, Trash2, CheckCircle, FileText, Laptop, GraduationCap, Settings, AlertTriangle, RotateCcw } from 'lucide-react';
import { useIsLightMode } from '../hooks/useIsLightMode';

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

const LT = {
  card: 'bg-stone-100 rounded-2xl',
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  textDim: 'text-stone-600',
  border: 'border-stone-200',
  input: 'bg-white border border-stone-300 text-zinc-900 rounded-xl placeholder:text-stone-400 focus:outline-none focus:border-stone-400',
  select: 'bg-white border border-stone-300 text-zinc-900 rounded-xl focus:outline-none focus:border-stone-400',
  textarea: 'bg-stone-50 border border-stone-300 text-zinc-900 rounded-xl placeholder:text-stone-400 focus:outline-none focus:border-stone-400 resize-none',
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800',
  btnGhost: 'text-stone-500 hover:text-zinc-900',
  btnDanger: 'text-stone-400 hover:text-red-600',
  modalBg: 'bg-stone-100 rounded-2xl',
  modalHeader: 'border-b border-stone-200',
  tabActive: 'border-zinc-900 text-zinc-900',
  tabInactive: 'border-transparent text-stone-400 hover:text-stone-600 hover:border-stone-400',
  rowBg: 'bg-stone-50',
  rowHover: 'hover:bg-stone-100',
  rowBorder: 'bg-stone-200 border border-stone-200',
  emptyBorder: 'border border-dashed border-stone-300 bg-stone-100',
  badge: 'bg-stone-200 text-stone-500 border border-stone-200',
  label: 'text-stone-500',
  checkboxCls: 'w-4 h-4 bg-white border border-stone-300 rounded',
  alertError: 'bg-red-50 border border-red-200 rounded-xl',
  alertErrorText: 'text-red-700',
  actionBtn: 'text-stone-400 hover:text-zinc-900 hover:bg-stone-200',
  actionBtnDanger: 'text-stone-400 hover:text-red-600 hover:bg-red-50',
  toggleActive: 'text-emerald-600 hover:bg-emerald-50',
  toggleInactive: 'text-stone-400 hover:bg-stone-200',
} as const;

const DK = {
  card: 'bg-zinc-900/50 border border-white/10 rounded-2xl',
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  textDim: 'text-zinc-400',
  border: 'border-white/10',
  input: 'bg-zinc-900 border border-zinc-800 text-white rounded-xl placeholder:text-zinc-600 focus:outline-none focus:border-white/20',
  select: 'bg-zinc-900 border border-zinc-800 text-white rounded-xl focus:outline-none focus:border-white/20',
  textarea: 'bg-zinc-900 border border-zinc-800 text-white rounded-xl placeholder:text-zinc-600 focus:outline-none focus:border-white/20 resize-none',
  btnPrimary: 'bg-white text-black hover:bg-zinc-200',
  btnGhost: 'text-zinc-500 hover:text-white',
  btnDanger: 'text-zinc-400 hover:text-red-400',
  modalBg: 'bg-zinc-950 border border-zinc-800 rounded-2xl',
  modalHeader: 'border-b border-white/10',
  tabActive: 'border-white text-white',
  tabInactive: 'border-transparent text-zinc-500 hover:text-zinc-300 hover:border-zinc-800',
  rowBg: 'bg-zinc-950',
  rowHover: 'hover:bg-zinc-900',
  rowBorder: 'bg-white/10 border border-white/10',
  emptyBorder: 'border border-dashed border-white/10 bg-white/5',
  badge: 'bg-zinc-800 text-zinc-500 border border-zinc-700',
  label: 'text-zinc-500',
  checkboxCls: 'w-4 h-4 bg-zinc-900 border border-zinc-800 rounded',
  alertError: 'bg-red-500/10 border border-red-500/20 rounded-xl',
  alertErrorText: 'text-red-400',
  actionBtn: 'text-zinc-400 hover:text-white hover:bg-zinc-800',
  actionBtnDanger: 'text-zinc-400 hover:text-red-400 hover:bg-red-500/10',
  toggleActive: 'text-emerald-400 hover:bg-emerald-500/10',
  toggleInactive: 'text-zinc-500 hover:bg-zinc-800',
} as const;

export default function OnboardingTemplates() {
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;

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
        <div className={`text-xs ${t.textMuted} uppercase tracking-wider animate-pulse`}>Loading templates...</div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className={`flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b ${t.border} pb-8`}>
        <div>
          <h1 className={`text-3xl md:text-4xl font-bold tracking-tighter ${t.textMain} uppercase text-center sm:text-left`}>Onboarding Templates</h1>
          <p className={`text-xs ${t.textMuted} mt-2 font-mono tracking-wide uppercase text-center sm:text-left`}>
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
          className={`flex items-center justify-center gap-2 px-6 py-2 ${t.btnPrimary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors w-full sm:w-auto`}
        >
          <Plus size={14} />
          Add Template
        </button>
      </div>

      {/* Error message */}
      {error && (
        <div className={`${t.alertError} p-4 flex items-center justify-between gap-4`}>
          <div className="flex items-center gap-3">
            <AlertTriangle className={`${t.alertErrorText} shrink-0`} size={16} />
            <p className={`text-sm ${t.alertErrorText} font-mono`}>{error}</p>
          </div>
          <button
            onClick={() => setError(null)}
            className={`text-xs ${t.alertErrorText} uppercase tracking-wider font-bold shrink-0`}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Category filter */}
      <div className={`border-b ${t.border} -mx-4 px-4 sm:mx-0 sm:px-0`}>
        <nav className="-mb-px flex space-x-8 overflow-x-auto pb-px no-scrollbar">
          {[{ value: '', label: 'All' }, ...CATEGORIES].map((cat) => (
            <button
              key={cat.value}
              onClick={() => setCategoryFilter(cat.value)}
              className={`pb-4 px-1 border-b-2 text-xs font-bold uppercase tracking-wider transition-colors whitespace-nowrap ${
                categoryFilter === cat.value ? t.tabActive : t.tabInactive
              }`}
            >
              {cat.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Templates grouped by category */}
      {templates.length === 0 ? (
        <div className={`text-center py-24 ${t.emptyBorder} rounded-2xl`}>
          <div className={`w-16 h-16 mx-auto mb-6 rounded-full ${t.card} flex items-center justify-center`}>
            <CheckCircle size={24} className={t.textFaint} />
          </div>
          <h3 className={`${t.textMain} text-sm font-bold mb-1 uppercase tracking-wide`}>Create your first template</h3>
          <p className={`${t.textMuted} text-xs mb-6 font-mono uppercase`}>You haven't defined any onboarding tasks yet. Build your first checklist to get started.</p>
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
                  <h2 className={`text-sm font-bold uppercase tracking-wider ${t.textMain}`}>{cat.label}</h2>
                  <span className={`text-xs ${t.textMuted} font-mono`}>({categoryTemplates.length})</span>
                </div>
                <div className={`space-y-px ${t.rowBorder} rounded-2xl overflow-hidden`}>
                  {categoryTemplates.map((template) => (
                    <div
                      key={template.id}
                      className={`group ${t.rowBg} ${t.rowHover} transition-colors p-4 flex flex-col sm:flex-row sm:items-center gap-4 ${
                        !template.is_active ? 'opacity-50' : ''
                      }`}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className={`text-sm font-bold ${t.textMain} truncate`}>{template.title}</p>
                          {!template.is_active && (
                            <span className={`text-[10px] px-2 py-0.5 ${t.badge} uppercase tracking-wider rounded-lg`}>
                              Inactive
                            </span>
                          )}
                        </div>
                        {template.description && (
                          <p className={`text-xs ${t.textMuted} truncate mt-1`}>{template.description}</p>
                        )}
                      </div>
                      <div className={`flex items-center justify-between sm:justify-end gap-4 md:gap-8 border-t ${t.border} pt-3 sm:border-0 sm:pt-0`}>
                        <div className="text-left sm:text-right">
                          <p className={`text-[10px] ${t.textMuted} uppercase tracking-wider`}>Due</p>
                          <p className={`text-xs ${t.textDim} font-mono`}>{template.due_days} days</p>
                        </div>
                        <div className="text-left sm:text-right">
                          <p className={`text-[10px] ${t.textMuted} uppercase tracking-wider`}>Assigned to</p>
                          <p className={`text-xs ${t.textDim}`}>
                            {template.is_employee_task ? 'Employee' : 'HR/Manager'}
                          </p>
                        </div>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => handleToggleActive(template)}
                            className={`p-2 rounded-lg transition-colors ${
                              template.is_active ? t.toggleActive : t.toggleInactive
                            }`}
                            title={template.is_active ? 'Deactivate' : 'Activate'}
                          >
                            <CheckCircle size={16} />
                          </button>
                          <button
                            onClick={() => openEditModal(template)}
                            className={`p-2 ${t.actionBtn} rounded-lg transition-colors`}
                            title="Edit"
                          >
                            <Edit2 size={16} />
                          </button>
                          <button
                            onClick={() => handleDelete(template.id)}
                            className={`p-2 ${t.actionBtnDanger} rounded-lg transition-colors`}
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className={`w-full max-w-lg ${t.modalBg} shadow-2xl`}>
            <div className={`flex items-center justify-between p-6 ${t.modalHeader}`}>
              <h3 className={`text-xl font-bold ${t.textMain} uppercase tracking-tight`}>
                {editingTemplate ? 'Edit Template' : 'Add Template'}
              </h3>
              <button
                onClick={() => setShowModal(false)}
                className={`${t.btnGhost} transition-colors`}
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="p-8 space-y-6">
              <div>
                <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1.5`}>
                  Title <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={formData.title}
                  onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                  className={`w-full px-3 py-2 ${t.input} text-sm transition-colors`}
                />
              </div>

              <div>
                <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1.5`}>
                  Description
                </label>
                <textarea
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  rows={3}
                  className={`w-full px-3 py-2 ${t.textarea} text-sm transition-colors`}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1.5`}>
                    Category
                  </label>
                  <select
                    value={formData.category}
                    onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                    className={`w-full px-3 py-2 ${t.select} text-sm transition-colors`}
                  >
                    {CATEGORIES.map((cat) => (
                      <option key={cat.value} value={cat.value}>
                        {cat.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1.5`}>
                    Due (days from start)
                  </label>
                  <input
                    type="number"
                    min="0"
                    value={formData.due_days}
                    onChange={(e) => setFormData({ ...formData, due_days: parseInt(e.target.value) || 0 })}
                    className={`w-full px-3 py-2 ${t.input} text-sm transition-colors`}
                  />
                </div>
              </div>

              <div className="flex items-center gap-3">
                <input
                  type="checkbox"
                  id="is_employee_task"
                  checked={formData.is_employee_task}
                  onChange={(e) => setFormData({ ...formData, is_employee_task: e.target.checked })}
                  className={t.checkboxCls}
                />
                <label htmlFor="is_employee_task" className={`text-sm ${t.textDim}`}>
                  Employee completes this task (vs HR/Manager)
                </label>
              </div>

              <div className={`flex justify-end gap-3 pt-6 border-t ${t.border}`}>
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className={`px-4 py-2 ${t.btnGhost} text-xs font-bold uppercase tracking-wider transition-colors`}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className={`px-6 py-2 ${t.btnPrimary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors disabled:opacity-50`}
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
