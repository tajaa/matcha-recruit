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
    <div className="relative min-h-[calc(100vh-8rem)]">
      <div className="fixed inset-0 pointer-events-none -z-10 transition-colors duration-500 light:bg-black/[0.12]" />
      <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between gap-3 mb-5">
        <div>
          <div className="inline-flex items-center bg-zinc-800 light:bg-white/10 light:backdrop-blur-[40px] light:backdrop-saturate-[150%] light:border-white/30 light:shadow-[0_4px_24px_rgba(0,0,0,0.02),inset_0_1px_1px_rgba(255,255,255,0.4)] rounded-lg p-0.5 mb-2 transition-colors">
            <button
              onClick={() => navigate('/app/matcha/work')}
              className="px-3 py-1 text-xs rounded text-zinc-400 hover:text-zinc-200 light:text-black/60 light:hover:text-black transition-colors"
            >
              Chat
            </button>
            <button
              onClick={() => navigate('/app/matcha/work/chats')}
              className="px-3 py-1 text-xs rounded text-zinc-400 hover:text-zinc-200 light:text-black/60 light:hover:text-black transition-colors"
            >
              Chats
            </button>
            <button className="px-3 py-1 text-xs rounded bg-zinc-700 text-zinc-100 light:bg-black/[0.12] light:text-black light:font-medium light:shadow-none transition-colors">
              Matcha Elements
            </button>
            <button
              onClick={() => navigate('/app/matcha/work/billing')}
              className="px-3 py-1 text-xs rounded text-zinc-400 hover:text-zinc-200 light:text-black/60 light:hover:text-black transition-colors"
            >
              Billing
            </button>
          </div>
          <h1 className="text-xl font-semibold text-zinc-100 light:text-black transition-colors">Matcha Elements</h1>
          <p className="text-sm text-zinc-400 light:text-black/60 mt-0.5 transition-colors">
            Finalized or saved artifacts live here. Use Chats for full conversation history.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleCreateElement}
            disabled={creatingChat}
            className="px-3 py-2 text-sm rounded-lg bg-matcha-600 hover:bg-matcha-700 light:bg-black light:hover:bg-black/80 light:shadow-none disabled:opacity-50 text-white transition-colors"
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
                ? 'bg-zinc-700 text-zinc-100 light:bg-black/10 light:text-black'
                : 'bg-zinc-900 text-zinc-400 hover:text-zinc-200 light:bg-black/[0.12] light:text-black/60 light:hover:bg-black/5 light:hover:text-black'
            }`}
          >
            {value}
          </button>
        ))}
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-300 light:text-red-600 light:bg-red-500/10 light:border-red-500/20 text-sm transition-colors">
          {error}
        </div>
      )}

      {loading ? (
        <div className="space-y-2">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-16 bg-zinc-800/50 light:bg-black/5 rounded-lg animate-pulse" />
          ))}
        </div>
      ) : elements.length === 0 ? (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 light:border-black/10 light:bg-black/5 p-8 text-center transition-colors">
          <p className="text-sm text-zinc-400 light:text-black/60">No saved or finalized elements found for this filter.</p>
          <button
            onClick={handleCreateElement}
            disabled={creatingChat}
            className="mt-3 px-3 py-1.5 text-xs rounded-lg bg-matcha-600 hover:bg-matcha-700 light:bg-black light:hover:bg-black/80 light:shadow-none disabled:opacity-50 text-white transition-colors"
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
              className="w-full flex items-center justify-between p-4 bg-zinc-800/50 hover:bg-zinc-800 border border-zinc-700/50 hover:border-zinc-600 light:bg-white/20 light:backdrop-blur-[40px] light:backdrop-saturate-[150%] light:hover:bg-white/30 light:border-white/40 light:hover:border-white/60 light:shadow-[0_4px_16px_rgba(0,0,0,0.03),inset_0_1px_1px_rgba(255,255,255,0.5)] rounded-lg text-left transition-all duration-200 group"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium text-zinc-200 truncate group-hover:text-white light:text-black light:group-hover:text-black transition-colors">
                  {element.title}
                </p>
                <p className="text-xs text-zinc-500 light:text-black/50 mt-0.5">
                  {element.element_type === 'review' ? 'anonymized review' : element.element_type === 'workbook' ? 'HR workbook' : 'offer letter'} · v{element.version} · Updated{' '}
                  {formatDate(element.updated_at)}
                </p>
              </div>
              <div className="ml-3 flex items-center gap-2 flex-shrink-0">
                <span
                  className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize ${
                    STATUS_COLORS[element.status].replace('bg-matcha-500/20 text-matcha-300', 'bg-matcha-500/20 text-matcha-300 light:bg-black/10 light:text-black').replace('bg-blue-500/20 text-blue-300', 'bg-blue-500/20 text-blue-300 light:bg-black/10 light:text-black').replace('bg-zinc-500/20 text-zinc-400', 'bg-zinc-500/20 text-zinc-400 light:bg-black/10 light:text-black')
                  }`}
                >
                  {element.status}
                </span>
                <svg
                  className="w-4 h-4 text-zinc-600 group-hover:text-zinc-300 light:text-black/40 light:group-hover:text-black/70 transition-colors"
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
    </div>
  );
}
