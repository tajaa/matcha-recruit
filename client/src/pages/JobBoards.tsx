import { useState, useEffect } from 'react';
import type { Position, SavedJob } from '../types';
import type { SavedOpening } from '../api/client';
import { positions as positionsApi, jobSearch, openings } from '../api/client';

// Unified job item for display
interface JobBoardItem {
  id: string;
  title: string;
  company_name: string;
  location: string | null;
  remote_policy: string | null;
  show_on_job_board: boolean;
  source_type: 'position' | 'saved_job' | 'saved_opening';
  created_at: string;
}

export function JobBoards() {
  const [items, setItems] = useState<JobBoardItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toggling, setToggling] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'all' | 'positions' | 'saved_jobs' | 'saved_openings'>('all');

  useEffect(() => {
    loadAllItems();
  }, []);

  const loadAllItems = async () => {
    try {
      setLoading(true);
      const [positionsData, savedJobsData, savedOpeningsData] = await Promise.all([
        positionsApi.list({ status: 'active' }),
        jobSearch.listSaved(),
        openings.listSaved(),
      ]);

      const positionItems: JobBoardItem[] = positionsData.map((p: Position) => ({
        id: p.id,
        title: p.title,
        company_name: p.company_name || '',
        location: p.location,
        remote_policy: p.remote_policy,
        show_on_job_board: p.show_on_job_board,
        source_type: 'position' as const,
        created_at: p.created_at,
      }));

      const savedJobItems: JobBoardItem[] = savedJobsData.map((sj: SavedJob) => ({
        id: sj.id,
        title: sj.title,
        company_name: sj.company_name,
        location: sj.location ?? null,
        remote_policy: sj.work_from_home ? 'remote' : null,
        show_on_job_board: (sj as any).show_on_job_board || false,
        source_type: 'saved_job' as const,
        created_at: sj.created_at,
      }));

      const savedOpeningItems: JobBoardItem[] = savedOpeningsData.map((so: SavedOpening) => ({
        id: so.id,
        title: so.title,
        company_name: so.company_name,
        location: so.location,
        remote_policy: null,
        show_on_job_board: (so as any).show_on_job_board || false,
        source_type: 'saved_opening' as const,
        created_at: so.created_at,
      }));

      const allItems = [...positionItems, ...savedJobItems, ...savedOpeningItems];
      allItems.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

      setItems(allItems);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load items');
    } finally {
      setLoading(false);
    }
  };

  const handleToggle = async (item: JobBoardItem) => {
    try {
      setToggling(item.id);
      const newValue = !item.show_on_job_board;

      if (item.source_type === 'position') {
        await positionsApi.toggleJobBoard(item.id, newValue);
      } else if (item.source_type === 'saved_job') {
        await jobSearch.toggleJobBoard(item.id, newValue);
      } else {
        await openings.toggleJobBoard(item.id, newValue);
      }

      setItems(prev => prev.map(i =>
        i.id === item.id ? { ...i, show_on_job_board: newValue } : i
      ));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update item');
    } finally {
      setToggling(null);
    }
  };

  const filteredItems = items.filter(item => {
    if (activeTab === 'all') return true;
    if (activeTab === 'positions') return item.source_type === 'position';
    if (activeTab === 'saved_jobs') return item.source_type === 'saved_job';
    if (activeTab === 'saved_openings') return item.source_type === 'saved_opening';
    return true;
  });

  const publishedCount = items.filter(i => i.show_on_job_board).length;

  const sourceLabel = (type: string) => {
    switch (type) {
      case 'position': return 'Position';
      case 'saved_job': return 'Job Search';
      case 'saved_opening': return 'Opening';
      default: return type;
    }
  };

  const sourceBadgeColor = (type: string) => {
    switch (type) {
      case 'position': return 'bg-zinc-800 text-white border-zinc-700';
      case 'saved_job': return 'bg-violet-500/10 text-violet-400 border-violet-500/20';
      case 'saved_opening': return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
      default: return 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20';
    }
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight">Job Board</h1>
          <p className="text-zinc-400 mt-1">Control which jobs appear on your public careers page</p>
        </div>
        <div className="flex items-center gap-4">
          <div className="px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg">
            <span className="text-white font-medium">{publishedCount}</span>
            <span className="text-zinc-400 ml-2">published</span>
          </div>
          <a
            href="/careers"
            target="_blank"
            rel="noopener noreferrer"
            className="px-4 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 hover:text-white hover:border-zinc-600 transition-colors flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
            View Public Page
          </a>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2">
        {[
          { key: 'all', label: 'All', count: items.length },
          { key: 'positions', label: 'Positions', count: items.filter(i => i.source_type === 'position').length },
          { key: 'saved_jobs', label: 'Job Search', count: items.filter(i => i.source_type === 'saved_job').length },
          { key: 'saved_openings', label: 'Openings', count: items.filter(i => i.source_type === 'saved_opening').length },
        ].map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key as any)}
            className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
              activeTab === tab.key
                ? 'bg-matcha-500 text-zinc-950'
                : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-300'
            }`}
          >
            {tab.label}
            <span className={`ml-2 ${activeTab === tab.key ? 'opacity-70' : 'text-zinc-500'}`}>
              {tab.count}
            </span>
          </button>
        ))}
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
          <div className="w-8 h-8 border-2 border-white border-t-transparent rounded-full animate-spin" />
        </div>
      ) : filteredItems.length === 0 ? (
        <div className="text-center py-16">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-zinc-800 flex items-center justify-center">
            <svg className="w-8 h-8 text-zinc-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
          </div>
          <h3 className="text-lg font-medium text-zinc-300 mb-2">No jobs found</h3>
          <p className="text-zinc-500">Save jobs from Job Search or Openings to publish them here</p>
        </div>
      ) : (
        <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-zinc-800">
                <th className="text-left px-6 py-4 text-[10px] tracking-[0.2em] uppercase text-zinc-500 font-medium">Job</th>
                <th className="text-left px-6 py-4 text-[10px] tracking-[0.2em] uppercase text-zinc-500 font-medium">Company</th>
                <th className="text-left px-6 py-4 text-[10px] tracking-[0.2em] uppercase text-zinc-500 font-medium">Location</th>
                <th className="text-left px-6 py-4 text-[10px] tracking-[0.2em] uppercase text-zinc-500 font-medium">Source</th>
                <th className="text-center px-6 py-4 text-[10px] tracking-[0.2em] uppercase text-zinc-500 font-medium">Published</th>
              </tr>
            </thead>
            <tbody>
              {filteredItems.map(item => (
                <tr key={`${item.source_type}-${item.id}`} className="border-b border-zinc-800/50 last:border-0 hover:bg-zinc-800/30 transition-colors">
                  <td className="px-6 py-4">
                    <div className="font-medium text-white">{item.title}</div>
                  </td>
                  <td className="px-6 py-4 text-zinc-300">{item.company_name || '—'}</td>
                  <td className="px-6 py-4 text-zinc-400">{item.location || '—'}</td>
                  <td className="px-6 py-4">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${sourceBadgeColor(item.source_type)}`}>
                      {sourceLabel(item.source_type)}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex justify-center">
                      <button
                        onClick={() => handleToggle(item)}
                        disabled={toggling === item.id}
                        className={`relative w-12 h-6 rounded-full transition-colors ${
                          item.show_on_job_board
                            ? 'bg-matcha-500'
                            : 'bg-zinc-700'
                        } ${toggling === item.id ? 'opacity-50' : ''}`}
                      >
                        <div
                          className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${
                            item.show_on_job_board ? 'left-7' : 'left-1'
                          }`}
                        />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Info Box */}
      <div className="p-4 bg-zinc-900/50 border border-zinc-800 rounded-xl">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-lg bg-zinc-800 flex items-center justify-center flex-shrink-0">
            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div>
            <h3 className="text-sm font-medium text-zinc-200 mb-1">About the Job Board</h3>
            <p className="text-sm text-zinc-500">
              Published jobs from all sources appear on your public careers page at <code className="text-white">/careers</code>.
              They are also included in the Indeed XML feed and have Google Jobs structured data for better search visibility.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default JobBoards;
