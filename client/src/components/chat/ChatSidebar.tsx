import { useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';
import { MessageCircle, Hash, LogOut } from 'lucide-react';
import type { ChatRoomWithUnread } from '../../types/chat';
import { useChatAuth } from '../../context/ChatAuthContext';

interface ChatSidebarProps {
  rooms: ChatRoomWithUnread[];
  onClose?: () => void;
}

export function ChatSidebar({ rooms, onClose }: ChatSidebarProps) {
  const { slug } = useParams<{ slug: string }>();
  const { user, logout } = useChatAuth();

  const sortedRooms = useMemo(() => {
    return [...rooms].sort((a, b) => {
      // Joined rooms first
      if (a.is_member && !b.is_member) return -1;
      if (!a.is_member && b.is_member) return 1;
      // Then by default rooms
      if (a.is_default && !b.is_default) return -1;
      if (!a.is_default && b.is_default) return 1;
      // Then by name
      return a.name.localeCompare(b.name);
    });
  }, [rooms]);

  const handleLogout = () => {
    logout();
    window.location.href = '/chat/login';
  };

  return (
    <div className="flex flex-col h-full bg-zinc-900 border-r border-white/10">
      {/* Header */}
      <div className="p-4 border-b border-white/10">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <MessageCircle className="w-5 h-5 text-emerald-400" />
            <h1 className="text-sm font-bold tracking-wider text-white uppercase">
              Community
            </h1>
          </div>
          <button
            onClick={handleLogout}
            className="p-1.5 hover:bg-white/5 rounded transition-colors"
            title="Logout"
          >
            <LogOut className="w-4 h-4 text-zinc-500 hover:text-zinc-300" />
          </button>
        </div>

        {user && (
          <div className="text-xs text-zinc-500">
            {user.first_name} {user.last_name}
          </div>
        )}
      </div>

      {/* Rooms List */}
      <div className="flex-1 overflow-y-auto">
        <div className="p-2 space-y-0.5">
          {sortedRooms.map((room) => (
            <Link
              key={room.id}
              to={`/chat/${room.slug}`}
              onClick={onClose}
              className={`
                flex items-center justify-between px-3 py-2 rounded-sm text-sm transition-colors group
                ${slug === room.slug
                  ? 'bg-white/10 text-white'
                  : 'text-zinc-400 hover:bg-white/5 hover:text-white'
                }
              `}
            >
              <div className="flex items-center gap-3 min-w-0 flex-1">
                <div className="flex-shrink-0">
                  {room.icon ? (
                    <span className="text-base">{room.icon}</span>
                  ) : (
                    <Hash className="w-4 h-4" />
                  )}
                </div>
                <span className="truncate font-medium">{room.name}</span>
              </div>

              <div className="flex items-center gap-2">
                {room.unread_count > 0 && (
                  <div className="px-1.5 min-w-[20px] h-5 flex items-center justify-center bg-emerald-500 text-white text-[10px] font-bold rounded-sm">
                    {room.unread_count > 99 ? '99+' : room.unread_count}
                  </div>
                )}
                {!room.is_member && (
                  <div className="text-[9px] text-zinc-600 font-mono uppercase">
                    Join
                  </div>
                )}
              </div>
            </Link>
          ))}
        </div>
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-white/10">
        <Link
          to="/"
          className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors"
        >
          Back to Matcha
        </Link>
      </div>
    </div>
  );
}
