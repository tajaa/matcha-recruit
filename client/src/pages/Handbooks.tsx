import { useCallback, useEffect, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { handbooks } from '../api/client';
import { useAuth } from '../context/AuthContext';
import type { HandbookListItem, HandbookStatus } from '../types';
import { BookOpen, ChevronRight, Plus, Pencil, CheckCircle, Send, ExternalLink, ShieldCheck } from 'lucide-react';
import { FeatureGuideTrigger } from '../features/feature-guides';
import HandbookDistributeModal from '../components/HandbookDistributeModal';
import { useIsLightMode } from '../hooks/useIsLightMode';

// ─── theme ────────────────────────────────────────────────────────────────────

const LT = {
  pageBg: 'bg-stone-300',
  card: 'bg-stone-100 rounded-2xl',
  cardBg: 'bg-stone-100',
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  border: 'border-stone-200',
  divide: 'divide-stone-200',
  rowHover: 'hover:bg-stone-50',
  label: 'text-[10px] text-stone-500 uppercase tracking-widest font-bold',
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800 rounded-xl',
  btnSecondary: 'border border-stone-300 hover:border-stone-400 text-stone-600 hover:text-zinc-900 rounded-xl',
  btnGhost: 'text-stone-500 hover:text-zinc-900',
  tabActive: 'border-zinc-900 text-zinc-900',
  tabInactive: 'border-transparent text-stone-400 hover:text-stone-600',
  emptyBg: 'border border-dashed border-stone-200 bg-stone-100 rounded-2xl',
  emptyIcon: 'bg-stone-200 border border-stone-300',
  emptyIconColor: 'text-stone-400',
  adminBg: 'bg-stone-200/60 border border-stone-200 rounded-2xl',
  adminLabel: 'text-stone-500',
  adminTitle: 'text-zinc-900',
  adminDesc: 'text-stone-500',
  adminBtn: 'border border-stone-300 text-zinc-900 hover:bg-stone-100',
  statusColors: {
    draft: 'text-stone-500',
    active: 'text-emerald-600',
    archived: 'text-stone-400',
  } as Record<HandbookStatus, string>,
  actionBtn: 'text-stone-400 hover:text-zinc-900 hover:bg-stone-200 rounded-lg',
  publishBtn: 'text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50 rounded-lg',
  distributeBtn: 'text-sky-600 hover:text-sky-700 hover:bg-sky-50 rounded-lg',
} as const;

const DK = {
  pageBg: 'bg-zinc-950',
  card: 'bg-zinc-900/50 border border-white/10 rounded-2xl',
  cardBg: 'bg-zinc-900/50',
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  border: 'border-white/10',
  divide: 'divide-white/10',
  rowHover: 'hover:bg-white/5',
  label: 'text-[10px] text-zinc-500 uppercase tracking-widest font-bold',
  btnPrimary: 'bg-zinc-700 text-zinc-100 hover:bg-zinc-600 rounded-xl',
  btnSecondary: 'border border-white/10 hover:border-white/20 text-zinc-500 hover:text-zinc-100 rounded-xl',
  btnGhost: 'text-zinc-600 hover:text-zinc-100',
  tabActive: 'border-zinc-100 text-zinc-100',
  tabInactive: 'border-transparent text-zinc-600 hover:text-zinc-400',
  emptyBg: 'border border-dashed border-white/10 bg-white/5 rounded-2xl',
  emptyIcon: 'bg-zinc-900 border border-zinc-800',
  emptyIconColor: 'text-zinc-600',
  adminBg: 'bg-zinc-900/50 border border-white/5 rounded-2xl',
  adminLabel: 'text-zinc-400',
  adminTitle: 'text-zinc-100',
  adminDesc: 'text-zinc-500',
  adminBtn: 'border border-white/10 text-zinc-100 hover:bg-white/5',
  statusColors: {
    draft: 'text-zinc-500',
    active: 'text-emerald-400',
    archived: 'text-zinc-600',
  } as Record<HandbookStatus, string>,
  actionBtn: 'text-zinc-600 hover:text-white hover:bg-white/10 rounded-lg',
  publishBtn: 'text-emerald-500 hover:text-emerald-400 hover:bg-emerald-500/10 rounded-lg',
  distributeBtn: 'text-sky-500 hover:text-sky-400 hover:bg-sky-500/10 rounded-lg',
} as const;

export function Handbooks() {
  const navigate = useNavigate();
  const { hasRole } = useAuth();
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;
  const [items, setItems] = useState<HandbookListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [filterStatus, setFilterStatus] = useState<HandbookStatus | ''>('');
  const [distributionLoading, setDistributionLoading] = useState(false);
  const [distributionTarget, setDistributionTarget] = useState<{ id: string; title: string } | null>(null);

  const loadHandbooks = useCallback(async () => {
    try {
      setLoading(true);
      const data = await handbooks.list();
      setItems(data);
    } catch (error) {
      console.error('Failed to load handbooks:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadHandbooks();
  }, [loadHandbooks]);

  useEffect(() => {
    const onFocus = () => {
      void loadHandbooks();
    };
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [loadHandbooks]);

  const handlePublish = async (e: React.MouseEvent, id: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm('Publish this handbook? This will archive any other active handbook.')) return;
    try {
      await handbooks.publish(id);
      await loadHandbooks();
    } catch (error) {
      console.error('Failed to publish handbook:', error);
    }
  };

  const handleDistribute = (e: React.MouseEvent, id: string, title: string) => {
    e.preventDefault();
    e.stopPropagation();
    setDistributionTarget({ id, title });
  };

  const handleConfirmDistribution = async (employeeIds?: string[]) => {
    if (!distributionTarget) return;
    try {
      setDistributionLoading(true);
      const result = await handbooks.distribute(distributionTarget.id, employeeIds);
      alert(`Distributed to ${result.assigned_count} employees (${result.skipped_existing_count} already assigned).`);
      setDistributionTarget(null);
      await loadHandbooks();
    } catch (error) {
      console.error('Failed to distribute handbook:', error);
      alert(error instanceof Error ? error.message : 'Failed to distribute handbook');
    } finally {
      setDistributionLoading(false);
    }
  };

  const filtered = filterStatus ? items.filter((item) => item.status === filterStatus) : items;

  return (
    <div className={`-mx-4 sm:-mx-6 lg:-mx-8 -mt-20 md:-mt-6 -mb-12 px-4 sm:px-6 lg:px-8 py-8 md:pt-10 min-h-screen ${t.pageBg}`}>
    <div className="max-w-5xl mx-auto space-y-8">
      <div className="flex justify-between items-start mb-12 pb-8">
        <div>
          <div className="flex items-center gap-3">
            <h1 className={`text-4xl font-bold tracking-tighter ${t.textMain} uppercase`}>Handbooks</h1>
            <FeatureGuideTrigger guideId="handbooks" />
          </div>
          <p className={`text-xs ${t.textMuted} mt-2 font-mono tracking-wide uppercase`}>Employee Handbook Builder</p>
        </div>
        <button
          data-tour="handbooks-create-btn"
          onClick={() => navigate('/app/matcha/handbook/new')}
          className={`flex items-center gap-2 px-5 py-2 text-xs font-bold uppercase tracking-wider transition-colors ${t.btnPrimary}`}
        >
          <Plus size={14} />
          Create Handbook
        </button>
      </div>

      {hasRole('admin') && (
        <div className={`p-6 ${t.adminBg} space-y-4`}>
          <div className={`flex items-center gap-2 ${t.adminLabel} mb-2`}>
            <ShieldCheck size={14} className="text-matcha-500" />
            <span className="text-[10px] font-bold uppercase tracking-[0.2em]">Master Admin Console</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-2">
              <h3 className={`text-sm font-bold ${t.adminTitle} uppercase tracking-tight`}>Industry Reference Benchmarks</h3>
              <p className={`text-xs ${t.adminDesc} leading-relaxed`}>
                Access our internal library of gold-standard handbooks from industry leaders like Valve, Netflix, and GitLab to assist with client templating.
              </p>
            </div>
            <div className="flex items-center justify-end">
              <Link
                to="/app/admin/handbooks"
                className={`flex items-center gap-2 px-4 py-2 ${t.adminBtn} text-[10px] font-bold uppercase tracking-widest transition-all rounded-xl`}
              >
                Open Reference Library
                <ExternalLink size={12} />
              </Link>
            </div>
          </div>
        </div>
      )}

      <div data-tour="handbooks-tabs" className={`flex gap-8 mb-px border-b ${t.border}`}>
        {[
          { label: 'All', value: '' },
          { label: 'Active', value: 'active' },
          { label: 'Drafts', value: 'draft' },
          { label: 'Archived', value: 'archived' },
        ].map((tab) => (
          <button
            key={tab.value}
            onClick={() => {
              setFilterStatus(tab.value as HandbookStatus | '');
              void loadHandbooks();
            }}
            className={`pb-3 text-[10px] font-bold uppercase tracking-widest transition-colors border-b-2 ${
              filterStatus === tab.value ? t.tabActive : t.tabInactive
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-24">
          <div className={`text-xs ${t.textFaint} uppercase tracking-wider animate-pulse`}>Loading handbooks...</div>
        </div>
      ) : filtered.length === 0 ? (
        <div className={`text-center py-24 ${t.emptyBg}`}>
          <div className={`w-12 h-12 mx-auto mb-4 rounded-full ${t.emptyIcon} flex items-center justify-center`}>
            <BookOpen size={20} className={t.emptyIconColor} />
          </div>
          <div className={`text-xs ${t.textMuted} mb-4 font-mono uppercase tracking-wider`}>No handbooks found</div>
          <button
            onClick={() => navigate('/app/matcha/handbook/new')}
            className={`text-xs ${t.textMain} font-bold uppercase tracking-wider underline underline-offset-4`}
          >
            Create first handbook
          </button>
        </div>
      ) : (
        <div data-tour="handbooks-list" className={`${t.card} overflow-hidden`}>
          <div className={`flex items-center gap-4 py-3 px-4 ${t.label} border-b ${t.border}`}>
            <div className="flex-1">Handbook</div>
            <div className="w-28 text-center">Scope</div>
            <div className="w-24 text-center">Version</div>
            <div className="w-28 text-center">Pending Changes</div>
            <div className="w-24 text-center">Status</div>
            <div className="w-32 text-center">Actions</div>
            <div className="w-8"></div>
          </div>

          <div className={`divide-y ${t.divide}`}>
            {filtered.map((item) => (
              <Link
                key={item.id}
                to={`/app/matcha/handbook/${item.id}`}
                className={`group flex items-center gap-4 py-4 px-4 cursor-pointer ${t.rowHover} transition-colors`}
              >
                <div className="flex-1 min-w-0">
                  <h3 className={`text-sm font-bold ${t.textMain} truncate transition-colors`}>
                    {item.title}
                  </h3>
                  <p className={`text-[10px] ${t.textFaint} mt-1 truncate max-w-xl font-mono uppercase`}>
                    {item.mode === 'multi_state' ? 'Multi-State' : 'Single-State'} • {item.source_type}
                  </p>
                </div>

                <div className={`w-28 text-center text-[10px] font-mono ${t.textMuted}`}>
                  {(item.scope_states || []).join(', ') || 'N/A'}
                </div>

                <div className={`w-24 text-center text-[10px] font-mono ${t.textFaint}`}>
                  v{item.active_version}
                </div>

                <div className="w-28 text-center text-[10px] font-mono text-amber-400">
                  {item.pending_changes_count || 0}
                </div>

                <div className={`w-24 text-center text-[10px] font-bold uppercase tracking-wider ${t.statusColors[item.status]}`}>
                  {item.status}
                </div>

                <div className="w-32 flex justify-center gap-2">
                  <button
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      navigate(`/app/matcha/handbook/${item.id}/edit`);
                    }}
                    className={`p-1.5 ${t.actionBtn} transition-colors`}
                    title="Edit handbook"
                  >
                    <Pencil size={14} />
                  </button>
                  {item.status !== 'active' && (
                    <button
                      data-tour="handbooks-publish-btn"
                      onClick={(e) => handlePublish(e, item.id)}
                      className={`p-1.5 ${t.publishBtn} transition-colors`}
                      title="Publish handbook"
                    >
                      <CheckCircle size={14} />
                    </button>
                  )}
                  {item.status === 'active' && (
                    <button
                      data-tour="handbooks-distribute-btn"
                      onClick={(e) => handleDistribute(e, item.id, item.title)}
                      className={`p-1.5 ${t.distributeBtn} transition-colors`}
                      title="Send for e-signature"
                    >
                      <Send size={14} />
                    </button>
                  )}
                </div>

                <div className={`w-8 flex justify-center ${t.textFaint} group-hover:${t.textMain} transition-colors`}>
                  <ChevronRight size={14} />
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      <HandbookDistributeModal
        open={Boolean(distributionTarget)}
        handbookId={distributionTarget?.id ?? null}
        handbookTitle={distributionTarget?.title}
        submitting={distributionLoading}
        onClose={() => {
          if (!distributionLoading) setDistributionTarget(null);
        }}
        onSubmit={handleConfirmDistribution}
      />
    </div>
    </div>
  );
}

export default Handbooks;
