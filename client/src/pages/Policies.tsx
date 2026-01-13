import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { GlassCard } from '../components/GlassCard';
import { Button } from '../components/Button';
import { policies } from '../api/client';
import type { Policy, PolicyStatus } from '../types';
import { FileText, RotateCcw, ListChecks, ChevronRight, Filter } from 'lucide-react';

export function Policies() {
  const [policiesList, setPolicies] = useState<Policy[]>([]);
  const [loading, setLoading] = useState(false);
  const [filterStatus, setFilterStatus] = useState<PolicyStatus | ''>('');
  const [showHelp, setShowHelp] = useState(false);

  const loadPolicies = async (status: PolicyStatus | '' = '') => {
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
  };

  useEffect(() => {
    loadPolicies(filterStatus);
  }, []);

  const handleFilterChange = (status: string) => {
    const newStatus = status as PolicyStatus | '';
    setFilterStatus(newStatus);
    loadPolicies(newStatus);
  };

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm('Are you sure you want to delete this policy?')) return;

    try {
      await policies.delete(id);
      loadPolicies(filterStatus);
    } catch (error) {
      console.error('Failed to delete policy:', error);
      alert('Failed to delete policy');
    }
  };

  const statusColors: Record<PolicyStatus, string> = {
    draft: 'bg-zinc-100 text-zinc-600 border-zinc-200',
    active: 'bg-zinc-200 text-zinc-900 border-zinc-300',
    archived: 'bg-zinc-50 text-zinc-400 border-zinc-200',
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="w-2 h-2 rounded-full bg-zinc-900 animate-ping" />
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-light tracking-tight text-zinc-900">Policies</h1>
          <p className="text-sm text-zinc-500 mt-2 font-mono tracking-wide uppercase">Company Guidelines & Compliance</p>
        </div>
        <div className="flex gap-3">
          <Button
            variant="secondary"
            onClick={() => setShowHelp(!showHelp)}
          >
            {showHelp ? 'Hide Help' : 'Help'}
          </Button>
          <Button onClick={() => window.location.href = '/app/policies/new'}>
            Create Policy
          </Button>
        </div>
      </div>

      {showHelp && (
        <GlassCard className="mb-6">
          <div className="p-8 space-y-8">
            <h2 className="text-lg font-light text-zinc-900 mb-6 flex items-center gap-2">
               <ListChecks className="w-5 h-5 text-zinc-600" />
               Policy Management Guide
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
              <div className="space-y-3">
                <h3 className="text-xs font-bold uppercase tracking-widest text-zinc-700">1. Draft & Review</h3>
                <p className="text-sm text-zinc-600 leading-relaxed italic">
                  Create policies in draft mode to refine content before making them active for signatures.
                </p>
              </div>
              <div className="space-y-3">
                <h3 className="text-xs font-bold uppercase tracking-widest text-zinc-700">2. Distribute</h3>
                <p className="text-sm text-zinc-600 leading-relaxed italic">
                  Send secure signing links to employees or candidates via bulk email or CSV upload.
                </p>
              </div>
              <div className="space-y-3">
                <h3 className="text-xs font-bold uppercase tracking-widest text-zinc-700">3. Audit Trail</h3>
                <p className="text-sm text-zinc-600 leading-relaxed italic">
                  Every signature is recorded with a timestamp and IP address for compliance reporting.
                </p>
              </div>
            </div>
          </div>
        </GlassCard>
      )}

      <div className="flex items-center gap-4 mb-2">
        <div className="flex items-center gap-2 px-3 py-1.5 bg-white border border-zinc-200 rounded-md">
          <Filter className="w-3.5 h-3.5 text-zinc-500" />
          <select
            value={filterStatus}
            onChange={(e) => handleFilterChange(e.target.value)}
            className="bg-transparent text-zinc-700 text-xs focus:outline-none uppercase tracking-widest font-medium cursor-pointer"
          >
            <option value="">All Policies</option>
            <option value="draft">Drafts</option>
            <option value="active">Active</option>
            <option value="archived">Archived</option>
          </select>
        </div>
      </div>

      {policiesList.length === 0 ? (
        <GlassCard className="p-16 text-center">
          <div className="w-20 h-20 mx-auto mb-6 rounded-full bg-zinc-50 border border-zinc-200 flex items-center justify-center">
            <FileText className="w-8 h-8 text-zinc-400" strokeWidth={1.5} />
          </div>
          <h3 className="text-xl font-light text-zinc-900 mb-2">No policies found</h3>
          <p className="text-sm text-zinc-500 mb-8 max-w-sm mx-auto">Create your first company policy to begin collecting signatures.</p>
          <Button onClick={() => window.location.href = '/app/policies/new'}>
            Create Policy
          </Button>
        </GlassCard>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {policiesList.map((policy) => (
            <Link key={policy.id} to={`/app/policies/${policy.id}`}>
              <GlassCard
                className="group cursor-pointer"
                hoverEffect
              >
                <div className="p-6 flex items-center justify-between">
                  <div className="flex items-center gap-6">
                    <div className="w-12 h-12 rounded-lg bg-zinc-50 border border-zinc-200 flex items-center justify-center text-zinc-400 group-hover:text-zinc-900 transition-colors">
                      <FileText className="w-6 h-6" strokeWidth={1.5} />
                    </div>
                    <div>
                      <div className="flex items-center gap-3">
                        <h3 className="text-lg font-medium text-zinc-900 group-hover:text-zinc-900 transition-colors">
                          {policy.title}
                        </h3>
                        <span className="text-[10px] font-mono text-zinc-500 uppercase tracking-tighter bg-zinc-100 px-1.5 py-0.5 rounded border border-zinc-200">
                          v{policy.version}
                        </span>
                      </div>
                      <p className="text-sm text-zinc-500 mt-1 line-clamp-1 max-w-xl">{policy.description}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-8">
                    <div className="hidden md:flex items-center gap-8">
                      <div className="text-center">
                        <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Signed</div>
                        <div className="text-sm font-mono text-zinc-900">{policy.signed_count || 0}</div>
                      </div>
                      <div className="text-center">
                        <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Pending</div>
                        <div className="text-sm font-mono text-zinc-700">{policy.pending_signatures || 0}</div>
                      </div>
                    </div>

                    <span className={`px-3 py-1 rounded-full text-[10px] uppercase tracking-wider font-medium border ${statusColors[policy.status]}`}>
                      {policy.status}
                    </span>

                    <div className="flex items-center gap-2">
                       <button
                        onClick={(e) => handleDelete(e, policy.id)}
                        className="p-2 text-zinc-400 hover:text-zinc-900 transition-colors"
                        title="Delete Policy"
                      >
                        <RotateCcw className="w-4 h-4 rotate-45" />
                      </button>
                      <ChevronRight className="w-5 h-5 text-zinc-400 group-hover:text-zinc-700 transition-colors" />
                    </div>
                  </div>
                </div>
              </GlassCard>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export default Policies;