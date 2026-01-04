import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Card } from '../components/Card';
import { Button } from '../components/Button';
import { policies } from '../api/client';
import type { Policy, PolicyStatus } from '../types';
import { FileText, Send, BarChart3, RotateCcw, ListChecks } from 'lucide-react';

export function Policies() {
  const [policiesList, setPolicies] = useState<Policy[]>([
    {
      id: 'p1',
      company_id: 'c1',
      company_name: 'Matcha Recruit',
      title: 'Remote Work Policy',
      description: 'Guidelines and requirements for employees working remotely or in a hybrid capacity.',
      content: 'Sample content for remote work policy...',
      file_url: null,
      version: '1.2',
      status: 'active',
      signature_count: 45,
      signed_count: 42,
      pending_signatures: 3,
      created_at: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString(),
      updated_at: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
      created_by: 'admin1'
    },
    {
      id: 'p2',
      company_id: 'c1',
      company_name: 'Matcha Recruit',
      title: 'Code of Conduct',
      description: 'Expected behavior and professional standards for all members of the organization.',
      content: 'Sample content for code of conduct...',
      file_url: null,
      version: '2.0',
      status: 'active',
      signature_count: 120,
      signed_count: 118,
      pending_signatures: 2,
      created_at: new Date(Date.now() - 365 * 24 * 60 * 60 * 1000).toISOString(),
      updated_at: new Date(Date.now() - 120 * 24 * 60 * 60 * 1000).toISOString(),
      created_by: 'admin1'
    },
    {
      id: 'p3',
      company_id: 'c1',
      company_name: 'Matcha Recruit',
      title: '2026 Bonus Structure',
      description: 'Proposed annual performance bonus criteria and payout schedules for the upcoming year.',
      content: 'Sample content for bonus structure...',
      file_url: null,
      version: '0.1',
      status: 'draft',
      signature_count: 0,
      signed_count: 0,
      pending_signatures: 0,
      created_at: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
      updated_at: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
      created_by: 'admin1'
    }
  ]);
  const [loading, setLoading] = useState(false);
  const [filterStatus, setFilterStatus] = useState<PolicyStatus | ''>('');
  const [showHelp, setShowHelp] = useState(false);

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
        <div className="flex gap-2">
          <Button
            variant="secondary"
            onClick={() => setShowHelp(!showHelp)}
          >
            {showHelp ? 'Hide Help' : 'Show Help'}
          </Button>
          <Button onClick={() => window.location.href = '/app/policies/new'}>
            Create Policy
          </Button>
        </div>
      </div>

      {showHelp && (
        <Card>
          <div className="p-6 space-y-4">
            <h2 className="text-lg font-semibold text-white mb-4">How to Use Policy Management</h2>

            <div className="space-y-4">
              <div>
                <h3 className="text-base font-medium text-white mb-2 flex items-center gap-2">
                  <FileText className="w-4 h-4 text-blue-400" />
                  Creating Policies
                </h3>
                <p className="text-sm text-zinc-300">
                  Click "Create Policy" to add a new company policy. Include the title, description,
                  and full policy content. You can also upload a document file (PDF, DOC, etc.) that
                  will be stored securely and accessible to signers.
                </p>
              </div>

              <div>
                <h3 className="text-base font-medium text-white mb-2 flex items-center gap-2">
                  <Send className="w-4 h-4 text-green-400" />
                  Sending Signature Requests
                </h3>
                <p className="text-sm text-zinc-300">
                  Click on any policy to view details, then click "Send Signatures". You can:
                </p>
                <ul className="text-sm text-zinc-400 mt-2 space-y-1 ml-4">
                  <li>• Select from existing candidates using the "Select from Candidates" button</li>
                  <li>• Manually add external signers (employees, contractors, etc.)</li>
                  <li>• Add multiple signers at once</li>
                </ul>
              </div>

              <div>
                <h3 className="text-base font-medium text-white mb-2 flex items-center gap-2">
                  <BarChart3 className="w-4 h-4 text-purple-400" />
                  Tracking Signatures
                </h3>
                <p className="text-sm text-zinc-300">
                  Monitor signature status in the policy details view. Each signer receives an
                  email with a secure link to review and sign the policy. Signatures are
                  timestamped and IP-addressed for compliance.
                </p>
              </div>

              <div>
                <h3 className="text-base font-medium text-white mb-2 flex items-center gap-2">
                  <RotateCcw className="w-4 h-4 text-orange-400" />
                  Managing Policies
                </h3>
                <p className="text-sm text-zinc-300">
                  Use the status filter to view draft, active, or archived policies. Click on
                  any policy to edit, send signatures, or delete it. Version numbers help track
                  policy updates.
                </p>
              </div>

              <div>
                <h3 className="text-base font-medium text-white mb-2 flex items-center gap-2">
                  <ListChecks className="w-4 h-4 text-emerald-400" />
                  Signature Workflow
                </h3>
                <div className="bg-zinc-900 p-4 rounded-lg text-sm">
                  <ol className="text-zinc-300 space-y-2">
                    <li><strong>1. Create Policy:</strong> Write or upload your policy document</li>
                    <li><strong>2. Send Requests:</strong> Select signers and send email invitations</li>
                    <li><strong>3. Signers Review:</strong> Recipients click email link to view policy</li>
                    <li><strong>4. Collect Signatures:</strong> Signers draw signature or accept/decline</li>
                    <li><strong>5. Track Progress:</strong> Monitor completion in policy dashboard</li>
                  </ol>
                </div>
              </div>
            </div>
          </div>
        </Card>
      )}

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
                      to={`/app/policies/${policy.id}`}
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
