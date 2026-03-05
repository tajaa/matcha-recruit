import { useState, useEffect, useRef } from 'react';
import { Plus, Trash2, Edit2, CheckSquare, X, AlertTriangle, Star, Link, FileText, BookOpen, Globe, ChevronDown, Layers } from 'lucide-react';
import { onboarding, policies, handbooks, type OnboardingTemplate } from '../api/client';
import type { Policy, HandbookListItem } from '../types';
import { useIsLightMode } from '../hooks/useIsLightMode';

type LinkType = 'policy' | 'handbook' | 'url' | 'template' | null;

interface FormState {
  title: string;
  description: string;
  due_days: number;
  link_type: LinkType;
  link_id: string;
  link_label: string;
  link_url: string;
}

const EMPTY_FORM: FormState = {
  title: '',
  description: '',
  due_days: 7,
  link_type: null,
  link_id: '',
  link_label: '',
  link_url: '',
};

const LINK_TYPE_META: Record<Exclude<LinkType, null>, { label: string; icon: React.ElementType; color: string }> = {
  policy: { label: 'Policy / Document', icon: FileText, color: 'text-blue-400' },
  handbook: { label: 'Handbook', icon: BookOpen, color: 'text-purple-400' },
  url: { label: 'External URL', icon: Globe, color: 'text-emerald-400' },
  template: { label: 'Template', icon: Layers, color: 'text-amber-400' },
};

const LT = {
  card: 'bg-stone-100 rounded-2xl',
  cardLight: 'bg-stone-100 rounded-2xl',
  cardDark: 'bg-zinc-900 rounded-2xl',
  cardDarkHover: 'hover:bg-zinc-800',
  cardDarkGhost: 'text-zinc-800',
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  textDim: 'text-stone-600',
  border: 'border-stone-200',
  input: 'bg-white border border-stone-300 text-zinc-900 rounded-xl placeholder:text-stone-400 focus:outline-none focus:border-stone-400',
  select: 'bg-white border border-stone-300 text-zinc-900 rounded-xl focus:outline-none focus:border-stone-400',
  textarea: 'bg-stone-50 border border-stone-300 text-zinc-900 rounded-xl placeholder:text-stone-400 focus:outline-none focus:border-stone-400 resize-none',
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800',
  btnSecondary: 'border border-stone-300 bg-stone-100 text-stone-600 hover:text-zinc-900',
  btnGhost: 'text-stone-500 hover:text-zinc-900',
  modalBg: 'bg-stone-100 rounded-2xl',
  modalHeader: 'border-b border-stone-200',
  rowActive: 'border-stone-200 bg-stone-100 hover:bg-stone-50',
  rowInactive: 'border-stone-200/60 bg-stone-100/60 opacity-50',
  emptyBorder: 'border border-dashed border-stone-300 bg-stone-100',
  dropdownBg: 'bg-stone-100 border border-stone-200',
  dropdownHover: 'hover:bg-stone-50',
  dropdownBorder: 'border-stone-200',
  linkPreview: 'bg-stone-200 border border-stone-200',
  alertError: 'border border-red-300 bg-red-50 text-red-700',
  selectorActive: 'border-zinc-900 bg-zinc-900/10 text-zinc-900',
  selectorInactive: 'border-stone-300 text-stone-500 hover:text-stone-700 hover:border-stone-400',
  toggleActive: 'border-emerald-300 text-emerald-700 hover:bg-emerald-50',
  toggleInactive: 'border-stone-300 text-stone-400 hover:text-stone-600',
  actionBtn: 'text-stone-400 hover:text-zinc-900',
  actionBtnDanger: 'text-stone-400 hover:text-red-600',
} as const;

const DK = {
  card: 'bg-zinc-900/50 border border-white/10 rounded-2xl',
  cardLight: 'bg-zinc-900/50 border border-white/10 rounded-2xl',
  cardDark: 'bg-zinc-800 rounded-2xl',
  cardDarkHover: 'hover:bg-zinc-700',
  cardDarkGhost: 'text-zinc-700',
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  textDim: 'text-zinc-400',
  border: 'border-white/10',
  input: 'bg-zinc-900 border border-white/10 text-white rounded-xl placeholder:text-zinc-600 focus:outline-none focus:border-white/30',
  select: 'bg-zinc-900 border border-white/10 text-white rounded-xl focus:outline-none focus:border-white/30',
  textarea: 'bg-zinc-900 border border-white/10 text-white rounded-xl placeholder:text-zinc-600 focus:outline-none focus:border-white/30 resize-none',
  btnPrimary: 'bg-white text-black hover:bg-zinc-100',
  btnSecondary: 'border border-white/10 bg-white/5 text-zinc-400 hover:text-white hover:bg-white/10',
  btnGhost: 'text-zinc-400 hover:text-white',
  modalBg: 'bg-zinc-950 border border-white/10 rounded-2xl',
  modalHeader: 'border-b border-white/10',
  rowActive: 'border-white/10 bg-zinc-900/40 hover:bg-zinc-900/70',
  rowInactive: 'border-white/5 bg-zinc-900/20 opacity-50',
  emptyBorder: 'border border-dashed border-white/10',
  dropdownBg: 'bg-zinc-950 border border-white/15',
  dropdownHover: 'hover:bg-white/5',
  dropdownBorder: 'border-white/10',
  linkPreview: 'bg-zinc-900/60 border border-white/5',
  alertError: 'border border-red-500/30 bg-red-500/10 text-red-300',
  selectorActive: 'border-white/30 bg-white/10 text-white',
  selectorInactive: 'border-white/10 text-zinc-600 hover:text-zinc-300 hover:border-white/20',
  toggleActive: 'border-emerald-500/30 text-emerald-400 hover:bg-emerald-950/40',
  toggleInactive: 'border-zinc-700 text-zinc-600 hover:text-zinc-300',
  actionBtn: 'text-zinc-500 hover:text-white',
  actionBtnDanger: 'text-zinc-600 hover:text-red-400',
} as const;

type Theme = typeof LT | typeof DK;

export default function OnboardingPriorities() {
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;

  const [templates, setTemplates] = useState<OnboardingTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState<OnboardingTemplate | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // "From template" dropdown
  const [showTemplateDropdown, setShowTemplateDropdown] = useState(false);
  const [allTemplates, setAllTemplates] = useState<OnboardingTemplate[]>([]);
  const [loadingAllTemplates, setLoadingAllTemplates] = useState(false);
  const templateDropdownRef = useRef<HTMLDivElement>(null);

  // Resource lists for pickers
  const [policyList, setPolicyList] = useState<Policy[]>([]);
  const [handbookList, setHandbookList] = useState<HandbookListItem[]>([]);
  const [loadingResources, setLoadingResources] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await onboarding.getPriorityTemplates();
      setTemplates(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load priorities');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (templateDropdownRef.current && !templateDropdownRef.current.contains(e.target as Node)) {
        setShowTemplateDropdown(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const loadAllTemplates = async () => {
    if (allTemplates.length > 0) return;
    setLoadingAllTemplates(true);
    try {
      const data = await onboarding.getTemplates();
      setAllTemplates(data.filter(t => t.category !== 'priority' && t.is_active));
    } catch { /* ignore */ } finally {
      setLoadingAllTemplates(false);
    }
  };

  const openTemplateDropdown = () => {
    setShowTemplateDropdown(v => !v);
    loadAllTemplates();
  };

  const openCreateFromTemplate = (tmpl: OnboardingTemplate) => {
    setShowTemplateDropdown(false);
    setEditing(null);
    setForm({
      title: tmpl.title,
      description: tmpl.description || '',
      due_days: tmpl.due_days,
      link_type: (tmpl.link_type as LinkType) || null,
      link_id: tmpl.link_id || '',
      link_label: tmpl.link_label || '',
      link_url: tmpl.link_url || '',
    });
    setSaveError(null);
    setShowModal(true);
    loadResources();
  };

  const loadResources = async () => {
    if (policyList.length > 0 || handbookList.length > 0) return;
    setLoadingResources(true);
    try {
      const [p, h] = await Promise.all([
        policies.list('active').catch(() => [] as Policy[]),
        handbooks.list().catch(() => [] as HandbookListItem[]),
      ]);
      setPolicyList(p);
      setHandbookList(h);
    } finally {
      setLoadingResources(false);
    }
    loadAllTemplates();
  };

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setSaveError(null);
    setShowModal(true);
    loadResources();
  };

  const openEdit = (tmpl: OnboardingTemplate) => {
    setEditing(tmpl);
    setForm({
      title: tmpl.title,
      description: tmpl.description || '',
      due_days: tmpl.due_days,
      link_type: (tmpl.link_type as LinkType) || null,
      link_id: tmpl.link_id || '',
      link_label: tmpl.link_label || '',
      link_url: tmpl.link_url || '',
    });
    setSaveError(null);
    setShowModal(true);
    loadResources();
  };

  const closeModal = () => {
    setShowModal(false);
    setEditing(null);
    setSaveError(null);
  };

  const handleSave = async () => {
    if (!form.title.trim()) { setSaveError('Title is required'); return; }
    if (form.link_type === 'url' && !form.link_url.trim()) { setSaveError('URL is required'); return; }
    if ((form.link_type === 'policy' || form.link_type === 'handbook' || form.link_type === 'template') && !form.link_id) {
      setSaveError('Please select a resource'); return;
    }

    const linkPayload = form.link_type ? {
      link_type: form.link_type,
      link_id: form.link_type !== 'url' ? form.link_id || null : null,
      link_label: form.link_label || null,
      link_url: form.link_type === 'url' ? form.link_url.trim() : null,
    } : {
      link_type: null as null,
      link_id: null as null,
      link_label: null as null,
      link_url: null as null,
    };

    setSaving(true);
    setSaveError(null);
    try {
      if (editing) {
        await onboarding.updatePriorityTemplate(editing.id, {
          title: form.title.trim(),
          description: form.description.trim() || undefined,
          due_days: form.due_days,
          ...linkPayload,
        });
      } else {
        await onboarding.createPriorityTemplate({
          title: form.title.trim(),
          description: form.description.trim() || undefined,
          due_days: form.due_days,
          ...linkPayload,
        });
      }
      closeModal();
      await load();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  const handleToggleActive = async (tmpl: OnboardingTemplate) => {
    try {
      await onboarding.updatePriorityTemplate(tmpl.id, { is_active: !tmpl.is_active });
      await load();
    } catch { /* ignore */ }
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm('Delete this priority? It will no longer be assigned to new hires.')) return;
    setDeletingId(id);
    try {
      await onboarding.deletePriorityTemplate(id);
      await load();
    } catch { /* ignore */ } finally {
      setDeletingId(null);
    }
  };

  const handleLinkTypeChange = (type: LinkType) => {
    setForm(f => ({ ...f, link_type: type, link_id: '', link_label: '', link_url: '' }));
  };

  const handleResourceSelect = (id: string, label: string) => {
    setForm(f => ({ ...f, link_id: id, link_label: label }));
  };

  const active = templates.filter(t => t.is_active);
  const inactive = templates.filter(t => !t.is_active);

  return (
    <div className="space-y-6">
      {/* Info Banner */}
      <div className={`${t.card} p-4 text-xs ${t.textDim} leading-relaxed`}>
        Priority tasks are automatically assigned to every new hire when they're created.
        Each priority can optionally link to a policy, handbook, or external URL so employees
        know exactly what to read or sign. You'll be notified by email and in-app when each item is completed.
      </div>

      {/* Header row */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className={`text-sm font-bold uppercase tracking-widest ${t.textMain}`}>Priority To-Dos</h2>
          <p className={`text-[10px] font-mono uppercase tracking-wide ${t.textMuted} mt-1`}>
            {active.length} active · {inactive.length} inactive
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* From Template dropdown */}
          <div className="relative" ref={templateDropdownRef}>
            <button
              onClick={openTemplateDropdown}
              className={`flex items-center gap-2 ${t.btnSecondary} px-3 py-2 text-[10px] font-bold uppercase tracking-widest rounded-xl transition-colors`}
            >
              <Layers className="w-3 h-3" />
              From Template
              <ChevronDown className={`w-3 h-3 transition-transform ${showTemplateDropdown ? 'rotate-180' : ''}`} />
            </button>
            {showTemplateDropdown && (
              <div className={`absolute right-0 top-full mt-1 w-72 ${t.dropdownBg} shadow-2xl z-20 max-h-72 overflow-y-auto rounded-xl`}>
                {loadingAllTemplates ? (
                  <div className={`px-4 py-3 text-xs ${t.textMuted} font-mono`}>Loading templates...</div>
                ) : allTemplates.length === 0 ? (
                  <div className={`px-4 py-3 text-xs ${t.textMuted}`}>No active templates found</div>
                ) : (
                  <>
                    <div className={`px-3 py-2 border-b ${t.dropdownBorder}`}>
                      <p className={`text-[10px] font-bold uppercase tracking-widest ${t.textMuted}`}>Pick a template to copy</p>
                    </div>
                    {allTemplates.map(tmpl => (
                      <button
                        key={tmpl.id}
                        onClick={() => openCreateFromTemplate(tmpl)}
                        className={`w-full text-left px-4 py-3 ${t.dropdownHover} transition-colors border-b ${t.dropdownBorder} last:border-0`}
                      >
                        <p className={`text-sm ${t.textMain} truncate`}>{tmpl.title}</p>
                        <p className={`text-[10px] font-mono ${t.textMuted} uppercase tracking-wider mt-0.5`}>
                          {tmpl.category} · due {tmpl.due_days}d
                        </p>
                      </button>
                    ))}
                  </>
                )}
              </div>
            )}
          </div>

          <button
            onClick={openCreate}
            className={`flex items-center gap-2 ${t.btnSecondary} px-3 py-2 text-[10px] font-bold uppercase tracking-widest rounded-xl transition-colors`}
          >
            <Plus className="w-3 h-3" />
            Add Priority
          </button>
        </div>
      </div>

      {loading && (
        <div className={`flex items-center gap-2 py-6 text-xs ${t.textMuted} font-mono`}>
          <div className="w-1.5 h-1.5 rounded-full bg-zinc-500 animate-pulse" />
          Loading...
        </div>
      )}
      {error && (
        <div className={`flex items-center gap-2 ${t.alertError} px-4 py-3 text-xs rounded-xl`}>
          <AlertTriangle className="w-4 h-4 flex-shrink-0" /> {error}
        </div>
      )}

      {!loading && active.length === 0 && inactive.length === 0 && (
        <div className={`${t.emptyBorder} py-12 text-center rounded-2xl`}>
          <Star className={`w-8 h-8 ${t.textFaint} mx-auto mb-3`} />
          <p className={`text-sm ${t.textDim} font-bold uppercase tracking-widest`}>No priorities yet</p>
          <p className={`text-xs ${t.textFaint} mt-1`}>Add items new hires should complete in their first days.</p>
        </div>
      )}

      {active.length > 0 && (
        <div className="space-y-2">
          {active.map(tmpl => (
            <TemplateRow
              key={tmpl.id}
              tmpl={tmpl}
              deleting={deletingId === tmpl.id}
              onEdit={() => openEdit(tmpl)}
              onDelete={() => handleDelete(tmpl.id)}
              onToggleActive={() => handleToggleActive(tmpl)}
              t={t}
            />
          ))}
        </div>
      )}

      {inactive.length > 0 && (
        <div className="space-y-2">
          <p className={`text-[10px] font-mono uppercase tracking-widest ${t.textMuted} pt-2`}>Inactive</p>
          {inactive.map(tmpl => (
            <TemplateRow
              key={tmpl.id}
              tmpl={tmpl}
              deleting={deletingId === tmpl.id}
              onEdit={() => openEdit(tmpl)}
              onDelete={() => handleDelete(tmpl.id)}
              onToggleActive={() => handleToggleActive(tmpl)}
              t={t}
            />
          ))}
        </div>
      )}

      {/* Create / Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-16 bg-black/40 overflow-y-auto">
          <div className={`${t.modalBg} w-full max-w-lg shadow-2xl mb-8`}>
            <div className={`flex items-center justify-between px-6 py-4 ${t.modalHeader}`}>
              <h3 className={`text-xs font-bold uppercase tracking-widest ${t.textMain}`}>
                {editing ? 'Edit Priority' : 'New Priority'}
              </h3>
              <button onClick={closeModal} className={`${t.btnGhost} transition-colors`}>
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="px-6 py-5 space-y-5">
              {/* Title */}
              <div>
                <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textDim} mb-1.5`}>
                  Title <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  value={form.title}
                  onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
                  placeholder="e.g. Introduce yourself in Slack"
                  className={`w-full px-3 py-2 ${t.input} text-sm`}
                />
              </div>

              {/* Description */}
              <div>
                <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textDim} mb-1.5`}>
                  Description
                </label>
                <textarea
                  value={form.description}
                  onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                  placeholder="Optional context for the employee..."
                  rows={2}
                  className={`w-full px-3 py-2 ${t.textarea} text-sm`}
                />
              </div>

              {/* Due days */}
              <div>
                <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textDim} mb-1.5`}>
                  Due Days After Start
                </label>
                <div className="flex items-center gap-3">
                  <input
                    type="number"
                    min={0}
                    max={90}
                    value={form.due_days}
                    onChange={e => setForm(f => ({ ...f, due_days: parseInt(e.target.value) || 0 }))}
                    className={`w-24 px-3 py-2 ${t.input} text-sm`}
                  />
                  <span className={`text-xs ${t.textMuted}`}>days after start date</span>
                </div>
              </div>

              {/* Link section */}
              <div className={`border-t ${t.border} pt-5`}>
                <div className="flex items-center gap-2 mb-3">
                  <Link className={`w-3.5 h-3.5 ${t.textMuted}`} />
                  <label className={`text-[10px] font-bold uppercase tracking-widest ${t.textDim}`}>
                    Attach Resource <span className={`${t.textFaint} normal-case font-normal`}>(optional)</span>
                  </label>
                </div>

                {/* Link type selector */}
                <div className="grid grid-cols-5 gap-2 mb-4">
                  <button
                    type="button"
                    onClick={() => handleLinkTypeChange(null)}
                    className={`py-2 px-2 text-[10px] font-bold uppercase tracking-widest border rounded-lg transition-colors ${
                      form.link_type === null ? t.selectorActive : t.selectorInactive
                    }`}
                  >
                    None
                  </button>
                  {(Object.entries(LINK_TYPE_META) as [Exclude<LinkType, null>, typeof LINK_TYPE_META[keyof typeof LINK_TYPE_META]][]).map(([type, meta]) => {
                    const Icon = meta.icon;
                    return (
                      <button
                        key={type}
                        type="button"
                        onClick={() => handleLinkTypeChange(type)}
                        className={`py-2 px-2 text-[10px] font-bold uppercase tracking-widest border rounded-lg transition-colors flex flex-col items-center gap-1 ${
                          form.link_type === type ? t.selectorActive : t.selectorInactive
                        }`}
                      >
                        <Icon className={`w-3.5 h-3.5 ${form.link_type === type ? '' : meta.color}`} />
                        {type === 'policy' ? 'Policy' : type === 'handbook' ? 'Handbook' : 'URL'}
                      </button>
                    );
                  })}
                </div>

                {/* Policy picker */}
                {form.link_type === 'policy' && (
                  <div>
                    <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-1.5`}>
                      Select Policy
                    </label>
                    {loadingResources ? (
                      <p className={`text-xs ${t.textFaint} py-2`}>Loading policies...</p>
                    ) : policyList.length === 0 ? (
                      <p className={`text-xs ${t.textFaint} py-2`}>No active policies found</p>
                    ) : (
                      <select
                        value={form.link_id}
                        onChange={e => {
                          const p = policyList.find(p => p.id === e.target.value);
                          handleResourceSelect(e.target.value, p?.title || '');
                        }}
                        className={`w-full px-3 py-2 ${t.select} text-sm`}
                      >
                        <option value="">— Select a policy —</option>
                        {policyList.map(p => (
                          <option key={p.id} value={p.id}>{p.title}</option>
                        ))}
                      </select>
                    )}
                  </div>
                )}

                {/* Handbook picker */}
                {form.link_type === 'handbook' && (
                  <div>
                    <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-1.5`}>
                      Select Handbook
                    </label>
                    {loadingResources ? (
                      <p className={`text-xs ${t.textFaint} py-2`}>Loading handbooks...</p>
                    ) : handbookList.length === 0 ? (
                      <p className={`text-xs ${t.textFaint} py-2`}>No handbooks found</p>
                    ) : (
                      <select
                        value={form.link_id}
                        onChange={e => {
                          const h = handbookList.find(h => h.id === e.target.value);
                          handleResourceSelect(e.target.value, h?.title || '');
                        }}
                        className={`w-full px-3 py-2 ${t.select} text-sm`}
                      >
                        <option value="">— Select a handbook —</option>
                        {handbookList.map(h => (
                          <option key={h.id} value={h.id}>{h.title}</option>
                        ))}
                      </select>
                    )}
                  </div>
                )}

                {/* URL input */}
                {form.link_type === 'url' && (
                  <div className="space-y-3">
                    <div>
                      <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-1.5`}>
                        URL <span className="text-red-400">*</span>
                      </label>
                      <input
                        type="url"
                        value={form.link_url}
                        onChange={e => setForm(f => ({ ...f, link_url: e.target.value }))}
                        placeholder="https://..."
                        className={`w-full px-3 py-2 ${t.input} text-sm`}
                      />
                    </div>
                    <div>
                      <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-1.5`}>
                        Display Label
                      </label>
                      <input
                        type="text"
                        value={form.link_label}
                        onChange={e => setForm(f => ({ ...f, link_label: e.target.value }))}
                        placeholder="e.g. Fill out this form"
                        className={`w-full px-3 py-2 ${t.input} text-sm`}
                      />
                    </div>
                  </div>
                )}

                {/* Template picker */}
                {form.link_type === 'template' && (
                  <div>
                    <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-1.5`}>
                      Select Template
                    </label>
                    {loadingAllTemplates ? (
                      <p className={`text-xs ${t.textFaint} py-2`}>Loading templates...</p>
                    ) : allTemplates.length === 0 ? (
                      <p className={`text-xs ${t.textFaint} py-2`}>No active templates found</p>
                    ) : (
                      <select
                        value={form.link_id}
                        onChange={e => {
                          const tmpl = allTemplates.find(tmpl => tmpl.id === e.target.value);
                          handleResourceSelect(e.target.value, tmpl?.title || '');
                        }}
                        className={`w-full px-3 py-2 ${t.select} text-sm`}
                      >
                        <option value="">— Select a template —</option>
                        {allTemplates.map(tmpl => (
                          <option key={tmpl.id} value={tmpl.id}>{tmpl.title}</option>
                        ))}
                      </select>
                    )}
                  </div>
                )}

                {/* Preview of selected link */}
                {form.link_type && form.link_id && (
                  <div className={`mt-3 px-3 py-2 ${t.linkPreview} text-xs ${t.textDim} rounded-lg`}>
                    <span className={`${t.textFaint} uppercase tracking-wider text-[10px] font-bold mr-2`}>Linked:</span>
                    {form.link_label || form.link_id}
                  </div>
                )}
              </div>

              {saveError && (
                <p className="text-xs text-red-400 flex items-center gap-1">
                  <AlertTriangle className="w-3.5 h-3.5" /> {saveError}
                </p>
              )}
            </div>

            <div className={`flex items-center justify-end gap-3 px-6 py-4 border-t ${t.border}`}>
              <button
                onClick={closeModal}
                className={`px-4 py-2 text-[10px] font-bold uppercase tracking-widest ${t.btnGhost} transition-colors`}
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className={`px-4 py-2 ${t.btnPrimary} text-[10px] font-bold uppercase tracking-widest rounded-xl transition-colors disabled:opacity-50`}
              >
                {saving ? 'Saving...' : editing ? 'Save Changes' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function TemplateRow({
  tmpl,
  deleting,
  onEdit,
  onDelete,
  onToggleActive,
  t,
}: {
  tmpl: OnboardingTemplate;
  deleting: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onToggleActive: () => void;
  t: Theme;
}) {
  const linkIcon = tmpl.link_type === 'policy' ? FileText
    : tmpl.link_type === 'handbook' ? BookOpen
    : tmpl.link_type === 'url' ? Globe
    : tmpl.link_type === 'template' ? Layers
    : null;
  const linkColor = tmpl.link_type === 'policy' ? 'text-blue-400'
    : tmpl.link_type === 'handbook' ? 'text-purple-400'
    : tmpl.link_type === 'template' ? 'text-amber-400'
    : 'text-emerald-400';

  return (
    <div className={`flex items-start gap-4 border px-4 py-3 rounded-xl transition-colors ${
      tmpl.is_active ? t.rowActive : t.rowInactive
    }`}>
      <CheckSquare className={`w-4 h-4 ${t.textMuted} mt-0.5 flex-shrink-0`} />

      <div className="flex-1 min-w-0">
        <p className={`text-sm font-medium ${t.textMain} truncate`}>{tmpl.title}</p>
        {tmpl.description && (
          <p className={`text-xs ${t.textMuted} mt-0.5 line-clamp-1`}>{tmpl.description}</p>
        )}
        <div className="flex items-center gap-3 mt-1">
          <p className={`text-[10px] font-mono ${t.textFaint} uppercase tracking-wider`}>
            Due {tmpl.due_days} day{tmpl.due_days !== 1 ? 's' : ''} after start
          </p>
          {tmpl.link_type && linkIcon && (
            <div className={`flex items-center gap-1 text-[10px] font-mono ${linkColor}`}>
              {(() => { const Icon = linkIcon; return <Icon className="w-3 h-3" />; })()}
              <span className="truncate max-w-[160px]">{tmpl.link_label || tmpl.link_url || tmpl.link_type}</span>
            </div>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2 flex-shrink-0">
        <button
          onClick={onToggleActive}
          title={tmpl.is_active ? 'Deactivate' : 'Activate'}
          className={`text-[10px] font-bold uppercase tracking-widest px-2 py-1 border rounded-lg transition-colors ${
            tmpl.is_active ? t.toggleActive : t.toggleInactive
          }`}
        >
          {tmpl.is_active ? 'Active' : 'Inactive'}
        </button>
        <button onClick={onEdit} className={`${t.actionBtn} transition-colors p-1`} title="Edit">
          <Edit2 className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={onDelete}
          disabled={deleting}
          className={`${t.actionBtnDanger} transition-colors p-1 disabled:opacity-50`}
          title="Delete"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
