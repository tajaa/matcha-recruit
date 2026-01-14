import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { policies } from '../api/client';
import type { Policy, PolicyStatus } from '../types';
import { ChevronRight } from 'lucide-react';
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

  const statusColors: Record<PolicyStatus, string> = {
    draft: 'text-zinc-500',
    active: 'text-zinc-900 font-medium',
    archived: 'text-zinc-400',
  };

  const statusDotColors: Record<PolicyStatus, string> = {
    draft: 'bg-zinc-400',
    active: 'bg-zinc-900',
    archived: 'bg-zinc-200',
  };

  return (
    <div className="max-w-5xl mx-auto space-y-12">
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-3xl font-light tracking-tight text-zinc-900">Policies</h1>
          <p className="text-sm text-zinc-500 mt-2 font-mono tracking-wide uppercase">Company Guidelines & Compliance</p>
        </div>
        <button
          onClick={() => navigate('/app/policies/new')}
          className="px-4 py-2 bg-zinc-900 text-white text-xs font-medium hover:bg-zinc-800 uppercase tracking-wider transition-colors"
        >
          Create Policy
        </button>
      </div>

      {/* Filter Tabs */}
      <div className="flex gap-6 border-b border-zinc-200 pb-px">
        {[
          { label: 'All', value: '' },
          { label: 'Active', value: 'active' },
          { label: 'Drafts', value: 'draft' },
          { label: 'Archived', value: 'archived' },
        ].map((tab) => (
          <button
            key={tab.value}
            onClick={() => handleFilterChange(tab.value)}
            className={`pb-3 text-[10px] font-medium uppercase tracking-wider transition-colors border-b-2 ${
              filterStatus === tab.value
                ? 'border-zinc-900 text-zinc-900'
                : 'border-transparent text-zinc-400 hover:text-zinc-600'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="text-xs text-zinc-500 uppercase tracking-wider">Loading policies...</div>
        </div>
      ) : policiesList.length === 0 ? (
        <div className="text-center py-16 border-t border-zinc-200">
          <div className="text-xs text-zinc-500 mb-4 font-mono">NO POLICIES FOUND</div>
          <button
            onClick={() => navigate('/app/policies/new')}
            className="text-xs text-zinc-900 hover:text-zinc-700 font-medium uppercase tracking-wider"
          >
            Create first policy
          </button>
        </div>
      ) : (
        <div className="space-y-1">
          {/* List Header */}
          <div className="flex items-center gap-4 py-2 text-[10px] text-zinc-500 uppercase tracking-wider border-b border-zinc-200">
            <div className="w-4"></div>
            <div className="flex-1">Policy Title</div>
            <div className="w-24">Version</div>
            <div className="w-24 text-center">Signed</div>
            <div className="w-32">Status</div>
            <div className="w-8"></div>
          </div>

          {policiesList.map((policy) => (
            <Link 
              key={policy.id} 
              to={`/app/policies/${policy.id}`}
              className="group flex items-center gap-4 py-4 cursor-pointer border-b border-zinc-100 hover:bg-zinc-50 transition-colors"
            >
              <div className="w-4 flex justify-center">
                <div className={`w-1.5 h-1.5 rounded-full ${statusDotColors[policy.status] || 'bg-zinc-300'}`} />
              </div>
              
              <div className="flex-1 min-w-0">
                <h3 className="text-sm font-medium text-zinc-900 truncate group-hover:text-zinc-700 transition-colors">
                  {policy.title}
                </h3>
                {policy.description && (
                  <p className="text-[10px] text-zinc-500 mt-0.5 truncate max-w-xl">{policy.description}</p>
                )}
              </div>

              <div className="w-24 text-[10px] font-mono text-zinc-400">
                v{policy.version}
              </div>

              <div className="w-24 text-center">
                <span className="text-[10px] font-mono text-zinc-900">{policy.signed_count || 0}</span>
                <span className="text-[10px] text-zinc-400 uppercase tracking-tighter ml-1">Total</span>
              </div>

              <div className={`w-32 text-[10px] font-medium uppercase tracking-wide ${statusColors[policy.status]}`}>
                {policy.status}
              </div>
              
              <div className="w-8 flex justify-center text-zinc-300 group-hover:text-zinc-900 transition-colors">
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