import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import type { Position, Company, ExperienceLevel, RemotePolicy, PositionStatus } from '../types';
import { positions as positionsApi, companies as companiesApi } from '../api/client';
import { Button, Modal, PositionCard, PositionForm } from '../components';

export function Positions() {
  const navigate = useNavigate();
  const [positions, setPositions] = useState<Position[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [isCreating, setIsCreating] = useState(false);

  // Filters
  const [statusFilter, setStatusFilter] = useState<PositionStatus | ''>('');
  const [experienceFilter, setExperienceFilter] = useState<ExperienceLevel | ''>('');
  const [remoteFilter, setRemoteFilter] = useState<RemotePolicy | ''>('');
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    loadData();
  }, [statusFilter, experienceFilter, remoteFilter, searchQuery]);

  const loadData = async () => {
    try {
      setLoading(true);
      const [positionsData, companiesData] = await Promise.all([
        positionsApi.list({
          status: statusFilter || undefined,
          experience_level: experienceFilter || undefined,
          remote_policy: remoteFilter || undefined,
          search: searchQuery || undefined,
        }),
        companiesApi.list(),
      ]);
      setPositions(positionsData);
      setCompanies(companiesData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load positions');
    } finally {
      setLoading(false);
    }
  };

  const handleCreatePosition = async (data: Parameters<typeof positionsApi.create>[0]) => {
    try {
      setIsCreating(true);
      await positionsApi.create(data);
      setShowCreateModal(false);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create position');
    } finally {
      setIsCreating(false);
    }
  };

  const selectClass = 'px-3 py-2 bg-zinc-900 border border-zinc-800 rounded-lg text-zinc-300 text-sm focus:outline-none focus:ring-2 focus:ring-matcha-500 focus:border-transparent';

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight">Positions</h1>
          <p className="text-zinc-400 mt-1">Manage open positions across all companies</p>
        </div>
        <Button onClick={() => setShowCreateModal(true)}>
          Add Position
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-4 p-4 bg-zinc-900/50 rounded-xl border border-zinc-800">
        <div className="flex-1 min-w-[200px]">
          <input
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="Search positions..."
            className="w-full px-4 py-2 bg-zinc-900 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-matcha-500 focus:border-transparent"
          />
        </div>

        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value as PositionStatus | '')}
          className={selectClass}
        >
          <option value="">All Statuses</option>
          <option value="active">Active</option>
          <option value="closed">Closed</option>
          <option value="draft">Draft</option>
        </select>

        <select
          value={experienceFilter}
          onChange={e => setExperienceFilter(e.target.value as ExperienceLevel | '')}
          className={selectClass}
        >
          <option value="">All Experience</option>
          <option value="entry">Entry</option>
          <option value="mid">Mid</option>
          <option value="senior">Senior</option>
          <option value="lead">Lead</option>
          <option value="executive">Executive</option>
        </select>

        <select
          value={remoteFilter}
          onChange={e => setRemoteFilter(e.target.value as RemotePolicy | '')}
          className={selectClass}
        >
          <option value="">All Remote</option>
          <option value="remote">Remote</option>
          <option value="hybrid">Hybrid</option>
          <option value="onsite">On-site</option>
        </select>
      </div>

      {/* Error */}
      {error && (
        <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400">
          {error}
        </div>
      )}

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center h-64">
          <div className="w-8 h-8 border-2 border-matcha-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : positions.length === 0 ? (
        <div className="text-center py-16">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-zinc-800 flex items-center justify-center">
            <svg className="w-8 h-8 text-zinc-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
          </div>
          <h3 className="text-lg font-medium text-zinc-300 mb-2">No positions found</h3>
          <p className="text-zinc-500 mb-6">
            {searchQuery || statusFilter || experienceFilter || remoteFilter
              ? 'Try adjusting your filters'
              : 'Create your first position to get started'}
          </p>
          {!searchQuery && !statusFilter && !experienceFilter && !remoteFilter && (
            <Button onClick={() => setShowCreateModal(true)}>Add Position</Button>
          )}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {positions.map(position => (
            <PositionCard
              key={position.id}
              position={position}
              onClick={() => navigate(`/app/positions/${position.id}`)}
            />
          ))}
        </div>
      )}

      {/* Create Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="Create New Position"
      >
        <PositionForm
          companies={companies}
          onSubmit={handleCreatePosition}
          onCancel={() => setShowCreateModal(false)}
          isLoading={isCreating}
        />
      </Modal>
    </div>
  );
}

export default Positions;
