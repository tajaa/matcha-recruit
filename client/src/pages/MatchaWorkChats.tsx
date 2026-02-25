import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { matchaWork } from '../api/client';
import type { MWThread, MWThreadStatus } from '../types/matcha-work';

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

function sortThreads(rows: MWThread[]): MWThread[] {
  return [...rows].sort((a, b) => {
    if (a.is_pinned !== b.is_pinned) return a.is_pinned ? -1 : 1;
    return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
  });
}

export default function MatchaWorkChats() {
  const navigate = useNavigate();
  const [threads, setThreads] = useState<MWThread[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [creatingChat, setCreatingChat] = useState(false);
  const [pinningThreadId, setPinningThreadId] = useState<string | null>(null);

  const loadThreads = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await matchaWork.listThreads({
        status: statusFilter === 'all' ? undefined : statusFilter,
        limit: 200,
        offset: 0,
      });
      setThreads(sortThreads(data));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load chat history');
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    loadThreads();
  }, [loadThreads]);

  const handleCreateThread = async () => {
    try {
      setCreatingChat(true);
      setError(null);
      const thread = await matchaWork.createThread({ title: 'Untitled Chat' });
      navigate(`/app/matcha/work/${thread.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create chat');
    } finally {
      setCreatingChat(false);
    }
  };

  const handleTogglePin = async (thread: MWThread) => {
    try {
      setPinningThreadId(thread.id);
      const updated = await matchaWork.pinThread(thread.id, !thread.is_pinned);
      setThreads((prev) => sortThreads(prev.map((t) => (t.id === updated.id ? updated : t))));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update pin');
    } finally {
      setPinningThreadId(null);
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
            <button className="px-3 py-1 text-xs rounded bg-zinc-700 text-zinc-100">
              Chats
            </button>
            <button
              onClick={() => navigate('/app/matcha/work/elements')}
              className="px-3 py-1 text-xs rounded text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              Matcha Elements
            </button>
          </div>
          <h1 className="text-xl font-semibold text-zinc-100">Chat History</h1>
          <p className="text-sm text-zinc-400 mt-0.5">
            Stored chats for your company. Pin important threads to keep them at the top.
          </p>
          <p className="text-xs text-zinc-500 mt-2">
            Skills: offer letters, anonymized reviews. Ask naturally. Unsupported requests return: "I can't do that."
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleCreateThread}
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
      ) : threads.length === 0 ? (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-8 text-center">
          <p className="text-sm text-zinc-400">No chats found.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {threads.map((thread) => (
            <div
              key={thread.id}
              role="button"
              tabIndex={0}
              onClick={() => navigate(`/app/matcha/work/${thread.id}`)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  navigate(`/app/matcha/work/${thread.id}`);
                }
              }}
              className="w-full flex items-center justify-between p-4 bg-zinc-800/50 hover:bg-zinc-800 border border-zinc-700/50 hover:border-zinc-600 rounded-lg text-left transition-colors group cursor-pointer"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium text-zinc-200 truncate group-hover:text-white transition-colors">
                  {thread.title}
                </p>
                <p className="text-xs text-zinc-500 mt-0.5">
                  {thread.task_type === 'review' ? 'anonymized review' : 'offer letter'} · v{thread.version} · Updated{' '}
                  {formatDate(thread.updated_at)}
                </p>
              </div>
              <div className="ml-3 flex items-center gap-2 flex-shrink-0">
                <button
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    if (pinningThreadId) return;
                    handleTogglePin(thread);
                  }}
                  className="w-7 h-7 rounded-md border border-zinc-700 hover:border-zinc-500 flex items-center justify-center text-zinc-400 hover:text-amber-300 transition-colors"
                  title={thread.is_pinned ? 'Unpin chat' : 'Pin chat'}
                  aria-label={thread.is_pinned ? 'Unpin chat' : 'Pin chat'}
                >
                  <svg
                    className={`w-4 h-4 ${thread.is_pinned ? 'text-amber-300 fill-current' : ''}`}
                    fill={thread.is_pinned ? 'currentColor' : 'none'}
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={1.5}
                      d="M12 3l2.9 5.88L21.4 10l-4.7 4.58 1.11 6.5L12 18l-5.81 3.08 1.11-6.5L2.6 10l6.5-1.12L12 3z"
                    />
                  </svg>
                </button>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize ${STATUS_COLORS[thread.status]}`}
                >
                  {thread.status}
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
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
