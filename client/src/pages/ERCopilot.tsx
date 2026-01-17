import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { erCopilot } from '../api/client';
import type { ERCase, ERCaseStatus, ERCaseCreate } from '../types';
import { X, ChevronRight } from 'lucide-react';

const STATUS_TABS: { label: string; value: ERCaseStatus | 'all' }[] = [
  { label: 'All', value: 'all' },
  { label: 'Open', value: 'open' },
  { label: 'In Review', value: 'in_review' },
  { label: 'Pending', value: 'pending_determination' },
  { label: 'Closed', value: 'closed' },
];

const STATUS_COLORS: Record<ERCaseStatus, string> = {
  open: 'text-white',
  in_review: 'text-amber-400',
  pending_determination: 'text-orange-400',
  closed: 'text-zinc-500',
};

const STATUS_DOTS: Record<ERCaseStatus, string> = {
  open: 'bg-white',
  in_review: 'bg-amber-500',
  pending_determination: 'bg-orange-500',
  closed: 'bg-zinc-700',
};

const STATUS_LABELS: Record<ERCaseStatus, string> = {
  open: 'Open',
  in_review: 'In Review',
  pending_determination: 'Pending',
  closed: 'Closed',
};

export function ERCopilot() {
  const navigate = useNavigate();
  const [cases, setCases] = useState<ERCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<ERCaseStatus | 'all'>('all');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [creating, setCreating] = useState(false);

  // Form state
  const [formData, setFormData] = useState<ERCaseCreate>({
    title: '',
    description: '',
  });

  const fetchCases = useCallback(async () => {
    try {
      setLoading(true);
      const status = activeTab !== 'all' ? activeTab : undefined;
      const response = await erCopilot.listCases(status);
      setCases(response.cases);
    } catch (err) {
      console.error('Failed to fetch cases:', err);
    } finally {
      setLoading(false);
    }
  }, [activeTab]);

  useEffect(() => {
    fetchCases();
  }, [fetchCases]);

  const handleCreate = async () => {
    if (!formData.title.trim()) return;

    setCreating(true);
    try {
      const created = await erCopilot.createCase(formData);
      setShowCreateModal(false);
      setFormData({ title: '', description: '' });
      navigate(`/app/er-copilot/${created.id}`);
    } catch (err) {
      console.error('Failed to create case:', err);
    } finally {
      setCreating(false);
    }
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  return (
    <div className="max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex justify-between items-start mb-12 border-b border-white/10 pb-8">
        <div>
          <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">ER Copilot</h1>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">Investigation Assistant</p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="px-6 py-2 bg-white text-black text-xs font-bold hover:bg-zinc-200 uppercase tracking-wider transition-colors"
        >
          New Case
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-8 mb-px border-b border-white/10">
        {STATUS_TABS.map((tab) => (
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

      {loading ? (
        <div className="flex items-center justify-center min-h-[20vh]">
           <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Loading...</div>
        </div>
      ) : cases.length === 0 ? (
        <div className="text-center py-24 border border-dashed border-white/10 bg-white/5 mt-8">
          <div className="text-xs text-zinc-500 mb-4 font-mono uppercase tracking-wider">No cases found</div>
          <button
            onClick={() => setShowCreateModal(true)}
            className="text-xs text-white hover:text-zinc-300 font-bold uppercase tracking-wider underline underline-offset-4"
          >
            Create first case
          </button>
        </div>
      ) : (
        <div className="space-y-px bg-white/10 border border-white/10 mt-8">
           {/* List Header */}
           <div className="flex items-center gap-4 py-3 px-4 text-[10px] text-zinc-500 uppercase tracking-widest bg-zinc-950 border-b border-white/10">
             <div className="w-8"></div>
             <div className="w-24">ID</div>
             <div className="flex-1">Title</div>
             <div className="w-32">Status</div>
             <div className="w-24 text-right">Created</div>
             <div className="w-8"></div>
           </div>

          {cases.map((erCase) => (
            <div 
              key={erCase.id} 
              className="group flex items-center gap-4 py-4 px-4 cursor-pointer bg-zinc-950 hover:bg-zinc-900 transition-colors"
              onClick={() => navigate(`/app/er-copilot/${erCase.id}`)}
            >
              <div className="w-8 flex justify-center">
                 <div className={`w-1.5 h-1.5 rounded-full ${STATUS_DOTS[erCase.status] || 'bg-zinc-700'}`} />
              </div>
              
              <div className="w-24 text-[10px] text-zinc-500 font-mono group-hover:text-zinc-400">
                 {erCase.case_number}
              </div>

              <div className="flex-1 min-w-0">
                 <h3 className="text-sm font-bold text-white truncate group-hover:text-zinc-300">
                   {erCase.title}
                 </h3>
                 {erCase.description && (
                   <p className="text-[10px] text-zinc-500 mt-1 truncate max-w-lg font-mono">{erCase.description}</p>
                 )}
              </div>

              <div className={`w-32 text-[10px] font-bold uppercase tracking-wider ${STATUS_COLORS[erCase.status]}`}>
                 {STATUS_LABELS[erCase.status]}
              </div>

              <div className="w-24 text-right text-[10px] text-zinc-500 font-mono">
                 {formatDate(erCase.created_at)}
              </div>
              
              <div className="w-8 flex justify-center text-zinc-600 group-hover:text-white">
                 <ChevronRight className="w-4 h-4" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create Modal - Inline implementation */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg bg-zinc-950 border border-zinc-800 shadow-2xl flex flex-col">
            <div className="flex items-center justify-between p-6 border-b border-white/10">
              <h3 className="text-sm font-bold text-white uppercase tracking-wider">New Investigation Case</h3>
              <button 
                onClick={() => setShowCreateModal(false)}
                className="text-zinc-500 hover:text-white transition-colors"
              >
                <X size={20} />
              </button>
            </div>
            
            <div className="p-8 space-y-6">
              <div>
                <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-2">Case Title</label>
                <input
                  type="text"
                  value={formData.title}
                  onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                  placeholder="e.g., Harassment Allegation - Sales Team"
                  className="w-full px-0 py-2 bg-transparent border-b border-zinc-800 text-white placeholder-zinc-600 text-sm focus:outline-none focus:border-white transition-colors"
                  autoFocus
                />
              </div>

              <div>
                <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-2">Description</label>
                <textarea
                  value={formData.description || ''}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="Brief summary of the allegation or incident..."
                  rows={4}
                  className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white placeholder-zinc-600 text-sm focus:outline-none focus:border-white/20 resize-none transition-colors"
                />
              </div>
            </div>

            <div className="flex justify-between items-center p-6 border-t border-white/10 bg-zinc-900/50">
              <button
                 onClick={() => setShowCreateModal(false)}
                 className="px-4 py-2 text-zinc-500 hover:text-white text-xs font-bold uppercase tracking-wider transition-colors"
              >
                Cancel
              </button>
              <button
                 onClick={handleCreate} 
                 disabled={creating || !formData.title.trim()}
                 className="px-6 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {creating ? 'Creating...' : 'Create Case'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ERCopilot;
