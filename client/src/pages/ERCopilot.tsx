import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Card, CardContent, Modal } from '../components';
import { erCopilot } from '../api/client';
import type { ERCase, ERCaseStatus, ERCaseCreate } from '../types';

const STATUS_TABS: { label: string; value: ERCaseStatus | 'all' }[] = [
  { label: 'All', value: 'all' },
  { label: 'Open', value: 'open' },
  { label: 'In Review', value: 'in_review' },
  { label: 'Pending', value: 'pending_determination' },
  { label: 'Closed', value: 'closed' },
];

const STATUS_COLORS: Record<ERCaseStatus, string> = {
  open: 'bg-matcha-500/20 text-matcha-400',
  in_review: 'bg-yellow-500/20 text-yellow-400',
  pending_determination: 'bg-orange-500/20 text-orange-400',
  closed: 'bg-zinc-700 text-zinc-300',
};

const STATUS_LABELS: Record<ERCaseStatus, string> = {
  open: 'Open',
  in_review: 'In Review',
  pending_determination: 'Pending Determination',
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

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Delete this case? This will permanently delete all documents and analysis.')) return;
    try {
      await erCopilot.deleteCase(id);
      fetchCases();
    } catch (err) {
      console.error('Failed to delete case:', err);
    }
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight">ER Copilot</h1>
          <p className="text-zinc-400 mt-1">Employee Relations Investigation Assistant</p>
        </div>
        <Button onClick={() => setShowCreateModal(true)}>New Case</Button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 bg-zinc-900 p-1 rounded-lg w-fit">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setActiveTab(tab.value)}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
              activeTab === tab.value
                ? 'bg-zinc-800 text-white'
                : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-center py-12 text-zinc-500">Loading...</div>
      ) : cases.length === 0 ? (
        <Card>
          <CardContent className="text-center py-12">
            <svg
              className="mx-auto h-12 w-12 text-zinc-600"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
            <h3 className="mt-4 text-lg font-medium text-white">No cases found</h3>
            <p className="mt-2 text-zinc-500">Get started by creating a new investigation case.</p>
            <Button className="mt-4" onClick={() => setShowCreateModal(true)}>
              Create Case
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {cases.map((erCase) => (
            <Card
              key={erCase.id}
              className="cursor-pointer hover:border-zinc-600 transition-colors"
              onClick={() => navigate(`/app/er-copilot/${erCase.id}`)}
            >
              <CardContent>
                <div className="flex justify-between items-start mb-3">
                  <span className="text-sm text-zinc-500 font-mono">{erCase.case_number}</span>
                  <span className={`px-2 py-0.5 text-xs rounded ${STATUS_COLORS[erCase.status]}`}>
                    {STATUS_LABELS[erCase.status]}
                  </span>
                </div>

                <h3 className="font-medium text-white mb-2 line-clamp-2">{erCase.title}</h3>

                {erCase.description && (
                  <p className="text-sm text-zinc-500 mb-3 line-clamp-2">{erCase.description}</p>
                )}

                <div className="flex items-center justify-between text-sm text-zinc-500">
                  <span className="flex items-center gap-1">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                      />
                    </svg>
                    {erCase.document_count} docs
                  </span>
                  <span>{formatDate(erCase.created_at)}</span>
                </div>

                <div className="mt-3 pt-3 border-t border-zinc-800 flex justify-end">
                  <button
                    onClick={(e) => handleDelete(erCase.id, e)}
                    className="text-xs text-zinc-500 hover:text-red-400 transition-colors"
                  >
                    Delete
                  </button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create Modal */}
      <Modal isOpen={showCreateModal} onClose={() => setShowCreateModal(false)} title="New Investigation Case">
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-zinc-300 mb-1">Case Title *</label>
            <input
              type="text"
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
              placeholder="e.g., Harassment Allegation - Sales Team"
              className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-matcha-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-zinc-300 mb-1">Description</label>
            <textarea
              value={formData.description || ''}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder="Brief summary of the allegation or incident..."
              rows={3}
              className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-matcha-500"
            />
          </div>

          <div className="flex justify-end gap-2 pt-4">
            <Button variant="ghost" onClick={() => setShowCreateModal(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={creating || !formData.title.trim()}>
              {creating ? 'Creating...' : 'Create Case'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

export default ERCopilot;
