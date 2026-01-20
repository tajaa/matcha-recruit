import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { policies } from '../api/client';
import type { Policy, PolicyStatus } from '../types';
import { ChevronRight, FileText, Plus, Pencil, CheckCircle, MoreHorizontal } from 'lucide-react';
import { Link } from 'react-router-dom';

export function Policies() {
  const navigate = useNavigate();
  const [policiesList, setPolicies] = useState<Policy[]>([]);
  const [loading, setLoading] = useState(false);
  const [filterStatus, setFilterStatus] = useState<PolicyStatus | ''>('');

  const loadPolicies = useCallback(async (status: PolicyStatus | '' = '') => {
    try {
      setLoading(true);
      const data = await policies.list(status || undefined);
      if (data) {
        setPolicies(data);
      }
    } catch (error) {
      console.error('Failed to load policies:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPolicies(filterStatus);
  }, [filterStatus, loadPolicies]);

  const handleFilterChange = (status: string) => {
    setFilterStatus(status as PolicyStatus | '');
  };

  const handleActivate = async (e: React.MouseEvent, policyId: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm('Activate this policy?')) return;
    try {
      await policies.update(policyId, { status: 'active' });
      loadPolicies(filterStatus);
    } catch (error) {
      console.error('Failed to activate policy:', error);
    }
  };

  const statusColors: Record<PolicyStatus, string> = {
    draft: 'text-zinc-500',
    active: 'text-white',
    archived: 'text-zinc-600',
  };

  const statusDotColors: Record<PolicyStatus, string> = {
    draft: 'bg-zinc-600',
    active: 'bg-white',
    archived: 'bg-zinc-800',
  };

  return (
    <div className="max-w-5xl mx-auto space-y-12">
      {/* Header */}
      <div className="flex justify-between items-start border-b border-white/10 pb-8">
        <div>
          <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">Policies</h1>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">Company Guidelines & Compliance</p>
        </div>
        <button
          onClick={() => navigate('/app/policies/new')}
          className="flex items-center gap-2 px-6 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors"
        >
          <Plus size={14} />
          Create Policy
        </button>
      </div>

      {/* Filter Tabs */}
      <div className="flex gap-8 border-b border-white/10 pb-px">
        {[
          { label: 'All', value: '' },
          { label: 'Active', value: 'active' },
          { label: 'Drafts', value: 'draft' },
          { label: 'Archived', value: 'archived' },
        ].map((tab) => (
          <button
            key={tab.value}
            onClick={() => handleFilterChange(tab.value)}
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
          <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Loading policies...</div>
        </div>
      ) : policiesList.length === 0 ? (
        <div className="text-center py-24 border border-dashed border-white/10 bg-white/5">
          <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center">
             <FileText size={20} className="text-zinc-600" />
          </div>
          <div className="text-xs text-zinc-500 mb-4 font-mono uppercase tracking-wider">NO POLICIES FOUND</div>
          <button
            onClick={() => navigate('/app/policies/new')}
            className="text-xs text-white hover:text-zinc-300 font-bold uppercase tracking-wider underline underline-offset-4"
          >
            Create first policy
          </button>
        </div>
      ) : (
        <div className="space-y-px bg-white/10 border border-white/10">
          {/* List Header */}
          <div className="flex items-center gap-4 py-3 px-4 text-[10px] text-zinc-500 uppercase tracking-widest bg-zinc-950 border-b border-white/10">
            <div className="w-4"></div>
            <div className="flex-1">Policy Title</div>
            <div className="w-24 text-center">Version</div>
            <div className="w-24 text-center">Signed</div>
            <div className="w-32 text-center">Status</div>
            <div className="w-28 text-center">Actions</div>
            <div className="w-8"></div>
          </div>

          {policiesList.map((policy) => (
            <Link 
              key={policy.id} 
              to={`/app/policies/${policy.id}`}
              className="group flex items-center gap-4 py-4 px-4 cursor-pointer bg-zinc-950 hover:bg-zinc-900 transition-colors"
            >
              <div className="w-4 flex justify-center">
                <div className={`w-1.5 h-1.5 rounded-full ${statusDotColors[policy.status] || 'bg-zinc-700'}`} />
              </div>
              
              <div className="flex-1 min-w-0">
                <h3 className="text-sm font-bold text-white truncate group-hover:text-zinc-300 transition-colors">
                  {policy.title}
                </h3>
                {policy.description && (
                  <p className="text-[10px] text-zinc-500 mt-1 truncate max-w-xl font-mono">{policy.description}</p>
                )}
              </div>

              <div className="w-24 text-center text-[10px] font-mono text-zinc-500">
                v{policy.version}
              </div>

              <div className="w-24 text-center">
                <span className="text-[10px] font-mono text-white font-bold">{policy.signed_count || 0}</span>
                <span className="text-[10px] text-zinc-600 uppercase tracking-tighter ml-1">Total</span>
              </div>

              <div className={`w-32 text-center text-[10px] font-bold uppercase tracking-wider ${statusColors[policy.status]}`}>
                {policy.status}
              </div>

              <div className="w-28 flex justify-center gap-2">
                <button
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    navigate(`/app/policies/${policy.id}/edit`);
                  }}
                  className="p-1.5 text-zinc-600 hover:text-white hover:bg-white/10 transition-colors rounded"
                  title="Edit policy"
                >
                  <Pencil size={14} />
                </button>
                {policy.status === 'draft' && (
                  <button
                    onClick={(e) => handleActivate(e, policy.id)}
                    className="p-1.5 text-emerald-600 hover:text-emerald-400 hover:bg-emerald-500/10 transition-colors rounded"
                    title="Activate policy"
                  >
                    <CheckCircle size={14} />
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

export default Policies;
