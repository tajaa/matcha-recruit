import { useState, useEffect } from 'react';
import type { Position } from '../types';
import { positions as positionsApi } from '../api/client';

export function JobBoards() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toggling, setToggling] = useState<string | null>(null);

  useEffect(() => {
    loadPositions();
  }, []);

  const loadPositions = async () => {
    try {
      setLoading(true);
      const data = await positionsApi.list({ status: 'active' });
      setPositions(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load positions');
    } finally {
      setLoading(false);
    }
  };

  const handleToggle = async (position: Position) => {
    try {
      setToggling(position.id);
      const updated = await positionsApi.toggleJobBoard(position.id, !position.show_on_job_board);
      setPositions(prev => prev.map(p => p.id === updated.id ? updated : p));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update position');
    } finally {
      setToggling(null);
    }
  };

  const publishedCount = positions.filter(p => p.show_on_job_board).length;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight">Job Board</h1>
          <p className="text-zinc-400 mt-1">Control which positions appear on your public careers page</p>
        </div>
        <div className="flex items-center gap-4">
          <div className="px-4 py-2 bg-matcha-500/10 border border-matcha-500/20 rounded-lg">
            <span className="text-matcha-400 font-medium">{publishedCount}</span>
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
          <h3 className="text-lg font-medium text-zinc-300 mb-2">No active positions</h3>
          <p className="text-zinc-500">Create active positions first to publish them to your job board</p>
        </div>
      ) : (
        <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-zinc-800">
                <th className="text-left px-6 py-4 text-[10px] tracking-[0.2em] uppercase text-zinc-500 font-medium">Position</th>
                <th className="text-left px-6 py-4 text-[10px] tracking-[0.2em] uppercase text-zinc-500 font-medium">Company</th>
                <th className="text-left px-6 py-4 text-[10px] tracking-[0.2em] uppercase text-zinc-500 font-medium">Location</th>
                <th className="text-left px-6 py-4 text-[10px] tracking-[0.2em] uppercase text-zinc-500 font-medium">Remote</th>
                <th className="text-center px-6 py-4 text-[10px] tracking-[0.2em] uppercase text-zinc-500 font-medium">Published</th>
              </tr>
            </thead>
            <tbody>
              {positions.map(position => (
                <tr key={position.id} className="border-b border-zinc-800/50 last:border-0 hover:bg-zinc-800/30 transition-colors">
                  <td className="px-6 py-4">
                    <div className="font-medium text-white">{position.title}</div>
                    {position.department && (
                      <div className="text-xs text-zinc-500 mt-0.5">{position.department}</div>
                    )}
                  </td>
                  <td className="px-6 py-4 text-zinc-300">{position.company_name || '—'}</td>
                  <td className="px-6 py-4 text-zinc-400">{position.location || '—'}</td>
                  <td className="px-6 py-4">
                    {position.remote_policy && (
                      <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                        position.remote_policy === 'remote'
                          ? 'bg-green-500/10 text-green-400'
                          : position.remote_policy === 'hybrid'
                          ? 'bg-blue-500/10 text-blue-400'
                          : 'bg-zinc-700/50 text-zinc-400'
                      }`}>
                        {position.remote_policy}
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex justify-center">
                      <button
                        onClick={() => handleToggle(position)}
                        disabled={toggling === position.id}
                        className={`relative w-12 h-6 rounded-full transition-colors ${
                          position.show_on_job_board
                            ? 'bg-matcha-500'
                            : 'bg-zinc-700'
                        } ${toggling === position.id ? 'opacity-50' : ''}`}
                      >
                        <div
                          className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${
                            position.show_on_job_board ? 'left-7' : 'left-1'
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
          <div className="w-8 h-8 rounded-lg bg-matcha-500/10 flex items-center justify-center flex-shrink-0">
            <svg className="w-4 h-4 text-matcha-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div>
            <h3 className="text-sm font-medium text-zinc-200 mb-1">About the Job Board</h3>
            <p className="text-sm text-zinc-500">
              Published positions appear on your public careers page at <code className="text-matcha-400">/careers</code>.
              They are also included in the Indeed XML feed and have Google Jobs structured data for better search visibility.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
