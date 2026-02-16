import { useCallback, useEffect, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { handbooks } from '../api/client';
import type { HandbookListItem, HandbookStatus } from '../types';
import { BookOpen, ChevronRight, Plus, Pencil, CheckCircle, Send } from 'lucide-react';
import { FeatureGuideTrigger } from '../features/feature-guides';

export function Handbooks() {
  const navigate = useNavigate();
  const [items, setItems] = useState<HandbookListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [filterStatus, setFilterStatus] = useState<HandbookStatus | ''>('');

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

  const handleDistribute = async (e: React.MouseEvent, id: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm('Send this handbook to all active employees for e-signature?')) return;
    try {
      await handbooks.distribute(id);
      alert('Handbook distribution started.');
      await loadHandbooks();
    } catch (error) {
      console.error('Failed to distribute handbook:', error);
      alert(error instanceof Error ? error.message : 'Failed to distribute handbook');
    }
  };

  const filtered = filterStatus ? items.filter((item) => item.status === filterStatus) : items;

  const statusColors: Record<HandbookStatus, string> = {
    draft: 'text-zinc-500',
    active: 'text-emerald-400',
    archived: 'text-zinc-600',
  };

  return (
    <div className="max-w-6xl mx-auto space-y-12">
      <div className="flex justify-between items-start border-b border-white/10 pb-8">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">Handbooks</h1>
            <FeatureGuideTrigger guideId="handbooks" />
          </div>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">Employee Handbook Builder</p>
        </div>
        <button
          data-tour="handbooks-create-btn"
          onClick={() => navigate('/app/matcha/handbook/new')}
          className="flex items-center gap-2 px-6 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors"
        >
          <Plus size={14} />
          Create Handbook
        </button>
      </div>

      <div data-tour="handbooks-tabs" className="flex gap-8 border-b border-white/10 pb-px">
        {[
          { label: 'All', value: '' },
          { label: 'Active', value: 'active' },
          { label: 'Drafts', value: 'draft' },
          { label: 'Archived', value: 'archived' },
        ].map((tab) => (
          <button
            key={tab.value}
            onClick={() => setFilterStatus(tab.value as HandbookStatus | '')}
            className={`pb-3 text-[10px] font-bold uppercase tracking-widest transition-colors border-b-2 ${
              filterStatus === tab.value
                ? 'border-white text-white'
                : 'border-transparent text-zinc-500 hover:text-zinc-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-24">
          <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Loading handbooks...</div>
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-24 border border-dashed border-white/10 bg-white/5">
          <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center">
            <BookOpen size={20} className="text-zinc-600" />
          </div>
          <div className="text-xs text-zinc-500 mb-4 font-mono uppercase tracking-wider">NO HANDBOOKS FOUND</div>
          <button
            onClick={() => navigate('/app/matcha/handbook/new')}
            className="text-xs text-white hover:text-zinc-300 font-bold uppercase tracking-wider underline underline-offset-4"
          >
            Create first handbook
          </button>
        </div>
      ) : (
        <div data-tour="handbooks-list" className="space-y-px bg-white/10 border border-white/10">
          <div className="flex items-center gap-4 py-3 px-4 text-[10px] text-zinc-500 uppercase tracking-widest bg-zinc-950 border-b border-white/10">
            <div className="flex-1">Handbook</div>
            <div className="w-28 text-center">Scope</div>
            <div className="w-24 text-center">Version</div>
            <div className="w-28 text-center">Pending Changes</div>
            <div className="w-24 text-center">Status</div>
            <div className="w-32 text-center">Actions</div>
            <div className="w-8"></div>
          </div>

          {filtered.map((item) => (
            <Link
              key={item.id}
              to={`/app/matcha/handbook/${item.id}`}
              className="group flex items-center gap-4 py-4 px-4 cursor-pointer bg-zinc-950 hover:bg-zinc-900 transition-colors"
            >
              <div className="flex-1 min-w-0">
                <h3 className="text-sm font-bold text-white truncate group-hover:text-zinc-300 transition-colors">
                  {item.title}
                </h3>
                <p className="text-[10px] text-zinc-500 mt-1 truncate max-w-xl font-mono uppercase">
                  {item.mode === 'multi_state' ? 'Multi-State' : 'Single-State'} • {item.source_type}
                </p>
              </div>

              <div className="w-28 text-center text-[10px] font-mono text-zinc-400">
                {(item.scope_states || []).join(', ') || 'N/A'}
              </div>

              <div className="w-24 text-center text-[10px] font-mono text-zinc-500">
                v{item.active_version}
              </div>

              <div className="w-28 text-center text-[10px] font-mono text-amber-400">
                {item.pending_changes_count || 0}
              </div>

              <div className={`w-24 text-center text-[10px] font-bold uppercase tracking-wider ${statusColors[item.status]}`}>
                {item.status}
              </div>

              <div className="w-32 flex justify-center gap-2">
                <button
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    navigate(`/app/matcha/handbook/${item.id}/edit`);
                  }}
                  className="p-1.5 text-zinc-600 hover:text-white hover:bg-white/10 transition-colors rounded"
                  title="Edit handbook"
                >
                  <Pencil size={14} />
                </button>
                {item.status !== 'active' && (
                  <button
                    data-tour="handbooks-publish-btn"
                    onClick={(e) => handlePublish(e, item.id)}
                    className="p-1.5 text-emerald-500 hover:text-emerald-400 hover:bg-emerald-500/10 transition-colors rounded"
                    title="Publish handbook"
                  >
                    <CheckCircle size={14} />
                  </button>
                )}
                {item.status === 'active' && (
                  <button
                    data-tour="handbooks-distribute-btn"
                    onClick={(e) => handleDistribute(e, item.id)}
                    className="p-1.5 text-sky-500 hover:text-sky-400 hover:bg-sky-500/10 transition-colors rounded"
                    title="Send for e-signature"
                  >
                    <Send size={14} />
                  </button>
                )}
              </div>

              <div className="w-8 flex justify-center text-zinc-600 group-hover:text-white transition-colors">
                <ChevronRight size={14} />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export default Handbooks;
