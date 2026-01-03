import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Card } from '../components/Card';
import { Button } from '../components/Button';
import { policies } from '../api/client';
import type { Policy, PolicyStatus } from '../types';

export function Policies() {
  const [policiesList, setPolicies] = useState<Policy[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState<PolicyStatus | ''>('');

  const loadPolicies = async (status: PolicyStatus | '' = '') => {
    try {
      setLoading(true);
      const data = await policies.list(status || undefined);
      setPolicies(data);
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

  const handleDelete = async (id: string) => {
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
    draft: 'bg-zinc-700 text-zinc-300',
    active: 'bg-green-900/30 text-green-400',
    archived: 'bg-zinc-700 text-zinc-400',
  };

  const statusLabels: Record<PolicyStatus, string> = {
    draft: 'Draft',
    active: 'Active',
    archived: 'Archived',
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-zinc-500">Loading...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Policies</h1>
          <p className="text-sm text-zinc-500 mt-1">Manage company policies and collect signatures</p>
        </div>
        <Button onClick={() => window.location.href = '/app/policies/new'}>
          Create Policy
        </Button>
      </div>

      <Card>
        <div className="p-4 border-b border-zinc-800">
          <div className="flex items-center gap-4">
            <span className="text-xs text-zinc-500 uppercase tracking-wider">Filter:</span>
            <select
              value={filterStatus}
              onChange={(e) => handleFilterChange(e.target.value)}
              className="px-3 py-1.5 bg-zinc-900 border border-zinc-800 text-zinc-200 text-sm rounded-md focus:outline-none focus:border-zinc-700"
            >
              <option value="">All Status</option>
              <option value="draft">Draft</option>
              <option value="active">Active</option>
              <option value="archived">Archived</option>
            </select>
          </div>
        </div>

        {policiesList.length === 0 ? (
          <div className="p-12 text-center">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-zinc-900 flex items-center justify-center">
              <svg className="w-8 h-8 text-zinc-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <h3 className="text-lg font-medium text-white mb-2">No policies found</h3>
            <p className="text-sm text-zinc-500 mb-6">
              {filterStatus ? `No ${filterStatus} policies yet` : 'Create your first policy to get started'}
            </p>
            <Button onClick={() => window.location.href = '/app/policies/new'}>
              Create Policy
            </Button>
          </div>
        ) : (
          <div className="divide-y divide-zinc-800">
            {policiesList.map((policy) => (
              <div key={policy.id} className="p-4 hover:bg-zinc-800/30 transition-colors">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <h3 className="text-base font-medium text-white">{policy.title}</h3>
                      <span className={`px-2 py-0.5 rounded text-[10px] tracking-wider uppercase ${statusColors[policy.status]}`}>
                        {statusLabels[policy.status]}
                      </span>
                      <span className="text-xs text-zinc-500">v{policy.version}</span>
                    </div>
                    {policy.description && (
                      <p className="text-sm text-zinc-400 line-clamp-2 mb-2">{policy.description}</p>
                    )}
                    <div className="flex items-center gap-4 text-xs text-zinc-500">
                      <span>{policy.signature_count || 0} total signatures</span>
                      {policy.signed_count !== null && policy.signed_count > 0 && (
                        <span className="text-green-400">{policy.signed_count} signed</span>
                      )}
                      {policy.pending_signatures !== null && policy.pending_signatures > 0 && (
                        <span className="text-yellow-400">{policy.pending_signatures} pending</span>
                      )}
                      <span>Updated {new Date(policy.updated_at).toLocaleDateString()}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Link
                      to={`/app/policies/${policy.id}`}
                      className="text-xs text-zinc-400 hover:text-white transition-colors px-2 py-1"
                    >
                      View
                    </Link>
                    <Link
                      to={`/app/policies/${policy.id}/signatures`}
                      className="text-xs text-zinc-400 hover:text-white transition-colors px-2 py-1"
                    >
                      Signatures
                    </Link>
                    <button
                      onClick={() => handleDelete(policy.id)}
                      className="text-xs text-zinc-600 hover:text-red-400 transition-colors px-2 py-1"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

export default Policies;
