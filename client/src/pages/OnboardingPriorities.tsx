import { useState, useEffect } from 'react';
import { Plus, Trash2, Edit2, CheckSquare, X, AlertTriangle, Star, Link, FileText, BookOpen, Globe } from 'lucide-react';
import { onboarding, policies, handbooks, type OnboardingTemplate } from '../api/client';
import type { Policy, HandbookListItem } from '../types';

type LinkType = 'policy' | 'handbook' | 'url' | null;

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
};

export default function OnboardingPriorities() {
  const [templates, setTemplates] = useState<OnboardingTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState<OnboardingTemplate | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

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

  const loadResources = async () => {
    if (policyList.length > 0 || handbookList.length > 0) return; // already loaded
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
    if ((form.link_type === 'policy' || form.link_type === 'handbook') && !form.link_id) {
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
      <div className="border border-white/10 bg-zinc-900/40 p-4 text-xs text-zinc-300 leading-relaxed">
        Priority tasks are automatically assigned to every new hire when they're created.
        Each priority can optionally link to a policy, handbook, or external URL so employees
        know exactly what to read or sign. You'll be notified by email and in-app when each item is completed.
      </div>

      {/* Header row */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-widest text-white">Priority To-Dos</h2>
          <p className="text-[10px] font-mono uppercase tracking-wide text-zinc-500 mt-1">
            {active.length} active · {inactive.length} inactive
          </p>
        </div>
        <button
          onClick={openCreate}
          className="flex items-center gap-2 border border-white/20 bg-white/5 hover:bg-white/10 px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-white transition-colors"
        >
          <Plus className="w-3 h-3" />
          Add Priority
        </button>
      </div>

      {loading && (
        <div className="flex items-center gap-2 py-6 text-xs text-zinc-500 font-mono">
          <div className="w-1.5 h-1.5 rounded-full bg-zinc-500 animate-pulse" />
          Loading...
        </div>
      )}
      {error && (
        <div className="flex items-center gap-2 border border-red-500/30 bg-red-500/10 px-4 py-3 text-xs text-red-300">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" /> {error}
        </div>
      )}

      {!loading && active.length === 0 && inactive.length === 0 && (
        <div className="border border-dashed border-white/10 py-12 text-center">
          <Star className="w-8 h-8 text-zinc-600 mx-auto mb-3" />
          <p className="text-sm text-zinc-400 font-bold uppercase tracking-widest">No priorities yet</p>
          <p className="text-xs text-zinc-600 mt-1">Add items new hires should complete in their first days.</p>
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
            />
          ))}
        </div>
      )}

      {inactive.length > 0 && (
        <div className="space-y-2">
          <p className="text-[10px] font-mono uppercase tracking-widest text-zinc-500 pt-2">Inactive</p>
          {inactive.map(tmpl => (
            <TemplateRow
              key={tmpl.id}
              tmpl={tmpl}
              deleting={deletingId === tmpl.id}
              onEdit={() => openEdit(tmpl)}
              onDelete={() => handleDelete(tmpl.id)}
              onToggleActive={() => handleToggleActive(tmpl)}
            />
          ))}
        </div>
      )}

      {/* Create / Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-16 bg-black/70 overflow-y-auto">
          <div className="bg-zinc-950 border border-white/10 w-full max-w-lg shadow-2xl mb-8">
            <div className="flex items-center justify-between px-6 py-4 border-b border-white/10">
              <h3 className="text-xs font-bold uppercase tracking-widest text-white">
                {editing ? 'Edit Priority' : 'New Priority'}
              </h3>
              <button onClick={closeModal} className="text-zinc-500 hover:text-white transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="px-6 py-5 space-y-5">
              {/* Title */}
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-widest text-zinc-400 mb-1.5">
                  Title <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  value={form.title}
                  onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
                  placeholder="e.g. Introduce yourself in Slack"
                  className="w-full bg-zinc-900 border border-white/10 px-3 py-2 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-white/30"
                />
              </div>

              {/* Description */}
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-widest text-zinc-400 mb-1.5">
                  Description
                </label>
                <textarea
                  value={form.description}
                  onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                  placeholder="Optional context for the employee..."
                  rows={2}
                  className="w-full bg-zinc-900 border border-white/10 px-3 py-2 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-white/30 resize-none"
                />
              </div>

              {/* Due days */}
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-widest text-zinc-400 mb-1.5">
                  Due Days After Start
                </label>
                <div className="flex items-center gap-3">
                  <input
                    type="number"
                    min={0}
                    max={90}
                    value={form.due_days}
                    onChange={e => setForm(f => ({ ...f, due_days: parseInt(e.target.value) || 0 }))}
                    className="w-24 bg-zinc-900 border border-white/10 px-3 py-2 text-sm text-white focus:outline-none focus:border-white/30"
                  />
                  <span className="text-xs text-zinc-500">days after start date</span>
                </div>
              </div>

              {/* Link section */}
              <div className="border-t border-white/10 pt-5">
                <div className="flex items-center gap-2 mb-3">
                  <Link className="w-3.5 h-3.5 text-zinc-500" />
                  <label className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">
                    Attach Resource <span className="text-zinc-600 normal-case font-normal">(optional)</span>
                  </label>
                </div>

                {/* Link type selector */}
                <div className="grid grid-cols-4 gap-2 mb-4">
                  <button
                    type="button"
                    onClick={() => handleLinkTypeChange(null)}
                    className={`py-2 px-2 text-[10px] font-bold uppercase tracking-widest border transition-colors ${
                      form.link_type === null
                        ? 'border-white/30 bg-white/10 text-white'
                        : 'border-white/10 text-zinc-600 hover:text-zinc-300 hover:border-white/20'
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
                        className={`py-2 px-2 text-[10px] font-bold uppercase tracking-widest border transition-colors flex flex-col items-center gap-1 ${
                          form.link_type === type
                            ? 'border-white/30 bg-white/10 text-white'
                            : 'border-white/10 text-zinc-600 hover:text-zinc-300 hover:border-white/20'
                        }`}
                      >
                        <Icon className={`w-3.5 h-3.5 ${form.link_type === type ? 'text-white' : meta.color}`} />
                        {type === 'policy' ? 'Policy' : type === 'handbook' ? 'Handbook' : 'URL'}
                      </button>
                    );
                  })}
                </div>

                {/* Policy picker */}
                {form.link_type === 'policy' && (
                  <div>
                    <label className="block text-[10px] font-bold uppercase tracking-widest text-zinc-500 mb-1.5">
                      Select Policy
                    </label>
                    {loadingResources ? (
                      <p className="text-xs text-zinc-600 py-2">Loading policies...</p>
                    ) : policyList.length === 0 ? (
                      <p className="text-xs text-zinc-600 py-2">No active policies found</p>
                    ) : (
                      <select
                        value={form.link_id}
                        onChange={e => {
                          const p = policyList.find(p => p.id === e.target.value);
                          handleResourceSelect(e.target.value, p?.title || '');
                        }}
                        className="w-full bg-zinc-900 border border-white/10 px-3 py-2 text-sm text-white focus:outline-none focus:border-white/30"
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
                    <label className="block text-[10px] font-bold uppercase tracking-widest text-zinc-500 mb-1.5">
                      Select Handbook
                    </label>
                    {loadingResources ? (
                      <p className="text-xs text-zinc-600 py-2">Loading handbooks...</p>
                    ) : handbookList.length === 0 ? (
                      <p className="text-xs text-zinc-600 py-2">No handbooks found</p>
                    ) : (
                      <select
                        value={form.link_id}
                        onChange={e => {
                          const h = handbookList.find(h => h.id === e.target.value);
                          handleResourceSelect(e.target.value, h?.title || '');
                        }}
                        className="w-full bg-zinc-900 border border-white/10 px-3 py-2 text-sm text-white focus:outline-none focus:border-white/30"
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
                      <label className="block text-[10px] font-bold uppercase tracking-widest text-zinc-500 mb-1.5">
                        URL <span className="text-red-400">*</span>
                      </label>
                      <input
                        type="url"
                        value={form.link_url}
                        onChange={e => setForm(f => ({ ...f, link_url: e.target.value }))}
                        placeholder="https://..."
                        className="w-full bg-zinc-900 border border-white/10 px-3 py-2 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-white/30"
                      />
                    </div>
                    <div>
                      <label className="block text-[10px] font-bold uppercase tracking-widest text-zinc-500 mb-1.5">
                        Display Label
                      </label>
                      <input
                        type="text"
                        value={form.link_label}
                        onChange={e => setForm(f => ({ ...f, link_label: e.target.value }))}
                        placeholder="e.g. Fill out this form"
                        className="w-full bg-zinc-900 border border-white/10 px-3 py-2 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-white/30"
                      />
                    </div>
                  </div>
                )}

                {/* Preview of selected link */}
                {form.link_type && form.link_id && (
                  <div className="mt-3 px-3 py-2 bg-zinc-900/60 border border-white/5 text-xs text-zinc-400">
                    <span className="text-zinc-600 uppercase tracking-wider text-[10px] font-bold mr-2">Linked:</span>
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

            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-white/10">
              <button
                onClick={closeModal}
                className="px-4 py-2 text-[10px] font-bold uppercase tracking-widest text-zinc-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="px-4 py-2 bg-white text-black text-[10px] font-bold uppercase tracking-widest hover:bg-zinc-100 transition-colors disabled:opacity-50"
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
}: {
  tmpl: OnboardingTemplate;
  deleting: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onToggleActive: () => void;
}) {
  const linkIcon = tmpl.link_type === 'policy' ? FileText
    : tmpl.link_type === 'handbook' ? BookOpen
    : tmpl.link_type === 'url' ? Globe
    : null;
  const linkColor = tmpl.link_type === 'policy' ? 'text-blue-400'
    : tmpl.link_type === 'handbook' ? 'text-purple-400'
    : 'text-emerald-400';

  return (
    <div className={`flex items-start gap-4 border px-4 py-3 transition-colors ${
      tmpl.is_active
        ? 'border-white/10 bg-zinc-900/40 hover:bg-zinc-900/70'
        : 'border-white/5 bg-zinc-900/20 opacity-50'
    }`}>
      <CheckSquare className="w-4 h-4 text-zinc-500 mt-0.5 flex-shrink-0" />

      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-white truncate">{tmpl.title}</p>
        {tmpl.description && (
          <p className="text-xs text-zinc-500 mt-0.5 line-clamp-1">{tmpl.description}</p>
        )}
        <div className="flex items-center gap-3 mt-1">
          <p className="text-[10px] font-mono text-zinc-600 uppercase tracking-wider">
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
          className={`text-[10px] font-bold uppercase tracking-widest px-2 py-1 border transition-colors ${
            tmpl.is_active
              ? 'border-emerald-500/30 text-emerald-400 hover:bg-emerald-950/40'
              : 'border-zinc-700 text-zinc-600 hover:text-zinc-300'
          }`}
        >
          {tmpl.is_active ? 'Active' : 'Inactive'}
        </button>
        <button onClick={onEdit} className="text-zinc-500 hover:text-white transition-colors p-1" title="Edit">
          <Edit2 className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={onDelete}
          disabled={deleting}
          className="text-zinc-600 hover:text-red-400 transition-colors p-1 disabled:opacity-50"
          title="Delete"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
