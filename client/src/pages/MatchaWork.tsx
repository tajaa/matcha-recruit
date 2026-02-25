import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { matchaWork } from '../api/client';

export default function MatchaWork() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const openChat = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const activeThreads = await matchaWork.listThreads({ status: 'active', limit: 1, offset: 0 });
      if (activeThreads.length > 0) {
        navigate(`/app/matcha/work/${activeThreads[0].id}`, { replace: true });
        return;
      }

      const thread = await matchaWork.createThread({ title: 'Untitled Chat' });
      navigate(`/app/matcha/work/${thread.id}`, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to open Matcha Work chat');
      setLoading(false);
    }
  }, [navigate]);

  useEffect(() => {
    openChat();
  }, [openChat]);

  if (error) {
    return (
      <div className="flex items-center justify-center h-full min-h-[320px] px-4">
        <div className="max-w-md w-full rounded-xl border border-red-500/30 bg-red-500/10 p-4">
          <p className="text-sm text-red-300">Could not open Matcha Work chat.</p>
          <p className="text-xs text-red-200/80 mt-1">{error}</p>
          <button
            onClick={openChat}
            className="mt-3 px-3 py-1.5 text-xs rounded-lg bg-red-600 hover:bg-red-700 text-white transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full min-h-[320px]">
        <div className="flex items-center gap-2 text-zinc-400 text-sm">
          <div className="w-4 h-4 border-2 border-zinc-600 border-t-matcha-400 rounded-full animate-spin" />
          Opening chat...
        </div>
      </div>
    );
  }

  return null;
}
