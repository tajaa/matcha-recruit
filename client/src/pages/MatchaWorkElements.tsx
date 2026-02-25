import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { matchaWork } from '../api/client';
import type { MWElement, MWThreadStatus } from '../types/matcha-work';

type StatusFilter = 'all' | MWThreadStatus;

const STATUS_COLORS: Record<MWThreadStatus, string> = {
  active: 'bg-matcha-500/20 text-matcha-300',
  finalized: 'bg-blue-500/20 text-blue-300',
  archived: 'bg-zinc-500/20 text-zinc-400',
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export default function MatchaWorkElements() {
  const navigate = useNavigate();
  const [elements, setElements] = useState<MWElement[]>([]);
  const [loading, setLoading] = useState(true);
  const [creatingChat, setCreatingChat] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');

  const loadElements = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await matchaWork.listElements({
        status: statusFilter === 'all' ? undefined : statusFilter,
        limit: 100,
        offset: 0,
      });
      setElements(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load Matcha Elements');
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    loadElements();
  }, [loadElements]);

  const handleCreateElement = async () => {
    try {
      setCreatingChat(true);
      setError(null);
      const thread = await matchaWork.createThread({ title: 'Untitled Chat' });
      navigate(`/app/matcha/work/${thread.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create element');
    } finally {
      setCreatingChat(false);
    }
  };

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between gap-3 mb-5">
        <div>
          <div className="inline-flex items-center bg-zinc-800 rounded-lg p-0.5 mb-2">
            <button
              onClick={() => navigate('/app/matcha/work')}
              className="px-3 py-1 text-xs rounded text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              Chat
            </button>
            <button
              onClick={() => navigate('/app/matcha/work/chats')}
              className="px-3 py-1 text-xs rounded text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              Chats
            </button>
            <button className="px-3 py-1 text-xs rounded bg-zinc-700 text-zinc-100">
              Matcha Elements
            </button>
          </div>
          <h1 className="text-xl font-semibold text-zinc-100">Matcha Elements</h1>
          <p className="text-sm text-zinc-400 mt-0.5">
            Finalized or saved artifacts live here. Use Chats for full conversation history.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleCreateElement}
            disabled={creatingChat}
            className="px-3 py-2 text-sm rounded-lg bg-matcha-600 hover:bg-matcha-700 disabled:opacity-50 text-white transition-colors"
          >
            {creatingChat ? 'Creating...' : 'New Chat'}
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 mb-4">
        {(['all', 'active', 'finalized', 'archived'] as StatusFilter[]).map((value) => (
          <button
            key={value}
            onClick={() => setStatusFilter(value)}
            className={`px-2.5 py-1 rounded-md text-xs capitalize transition-colors ${
              statusFilter === value
                ? 'bg-zinc-700 text-zinc-100'
                : 'bg-zinc-900 text-zinc-400 hover:text-zinc-200'
            }`}
          >
            {value}
          </button>
        ))}
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-300 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="space-y-2">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-16 bg-zinc-800/50 rounded-lg animate-pulse" />
          ))}
        </div>
      ) : elements.length === 0 ? (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-8 text-center">
          <p className="text-sm text-zinc-400">No saved or finalized elements found for this filter.</p>
          <button
            onClick={handleCreateElement}
            disabled={creatingChat}
            className="mt-3 px-3 py-1.5 text-xs rounded-lg bg-matcha-600 hover:bg-matcha-700 disabled:opacity-50 text-white transition-colors"
          >
            Start New Chat
          </button>
        </div>
      ) : (
        <div className="space-y-2">
          {elements.map((element) => (
            <button
              key={element.id}
              onClick={() => navigate(`/app/matcha/work/${element.thread_id}`)}
              className="w-full flex items-center justify-between p-4 bg-zinc-800/50 hover:bg-zinc-800 border border-zinc-700/50 hover:border-zinc-600 rounded-lg text-left transition-colors group"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium text-zinc-200 truncate group-hover:text-white transition-colors">
                  {element.title}
                </p>
                <p className="text-xs text-zinc-500 mt-0.5">
                  {element.element_type === 'review' ? 'anonymized review' : element.element_type === 'workbook' ? 'HR workbook' : 'offer letter'} · v{element.version} · Updated{' '}
                  {formatDate(element.updated_at)}
                </p>
              </div>
              <div className="ml-3 flex items-center gap-2 flex-shrink-0">
                <span
                  className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize ${
                    STATUS_COLORS[element.status]
                  }`}
                >
                  {element.status}
                </span>
                <svg
                  className="w-4 h-4 text-zinc-600 group-hover:text-zinc-300 transition-colors"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5l7 7-7 7" />
                </svg>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
