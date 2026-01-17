import { useEffect, useState, useRef, useCallback } from 'react';
import { Outlet, Navigate } from 'react-router-dom';
import { Menu } from 'lucide-react';
import { useChatAuth } from '../../context/ChatAuthContext';
import { ChatSidebar } from '../../components/chat/ChatSidebar';
import { chatRooms } from '../../api/chatClient';
import type { ChatRoomWithUnread } from '../../types/chat';

export function ChatLayout() {
  const { isAuthenticated, isLoading } = useChatAuth();
  const [rooms, setRooms] = useState<ChatRoomWithUnread[]>([]);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const intervalRef = useRef<number | null>(null);

  const loadRooms = useCallback(async () => {
    try {
      const data = await chatRooms.list();
      setRooms(data);
    } catch (error) {
      console.error('Failed to load rooms:', error);
    }
  }, []);

  const startPolling = useCallback(() => {
    // Clear any existing interval
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
    }
    // Start new polling interval
    intervalRef.current = window.setInterval(loadRooms, 30000);
  }, [loadRooms]);

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (isAuthenticated) {
      loadRooms();
      startPolling();

      // Handle visibility changes to pause/resume polling
      const handleVisibilityChange = () => {
        if (document.visibilityState === 'visible') {
          // Refresh rooms immediately when tab becomes visible
          loadRooms();
          startPolling();
        } else {
          // Pause polling when tab is hidden
          stopPolling();
        }
      };

      document.addEventListener('visibilitychange', handleVisibilityChange);

      return () => {
        stopPolling();
        document.removeEventListener('visibilitychange', handleVisibilityChange);
      };
    }
  }, [isAuthenticated, loadRooms, startPolling, stopPolling]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-xs text-zinc-500 font-mono uppercase tracking-wider">Loading</span>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/chat/login" replace />;
  }

  return (
    <div className="h-screen flex bg-zinc-950 text-white">
      {/* Mobile sidebar overlay */}
      {isSidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <div
        className={`
          fixed lg:static inset-y-0 left-0 z-50 w-64 transform transition-transform duration-300 ease-in-out
          ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
        `}
      >
        <ChatSidebar rooms={rooms} onClose={() => setIsSidebarOpen(false)} />
      </div>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Mobile header */}
        <div className="lg:hidden p-4 border-b border-white/10 bg-zinc-900">
          <button
            onClick={() => setIsSidebarOpen(true)}
            className="p-2 hover:bg-white/5 rounded transition-colors"
          >
            <Menu className="w-5 h-5" />
          </button>
        </div>

        {/* Page content */}
        <Outlet />
      </div>
    </div>
  );
}

export default ChatLayout;
