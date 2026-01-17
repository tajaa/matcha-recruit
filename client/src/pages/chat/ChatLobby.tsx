import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Users, ArrowRight, RefreshCw, AlertCircle } from 'lucide-react';
import { chatRooms } from '../../api/chatClient';
import { RoomIcon } from '../../components/chat/RoomIcon';
import type { ChatRoomWithUnread } from '../../types/chat';

export function ChatLobby() {
  const navigate = useNavigate();
  const [rooms, setRooms] = useState<ChatRoomWithUnread[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadRooms();
  }, []);

  const loadRooms = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await chatRooms.list();
      setRooms(data);
    } catch (err) {
      console.error('Failed to load rooms:', err);
      setError('Failed to load chat rooms. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleJoinRoom = async (slug: string) => {
    try {
      await chatRooms.join(slug);
      navigate(`/chat/${slug}`);
    } catch (err) {
      console.error('Failed to join room:', err);
      setError('Failed to join room. Please try again.');
    }
  };

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
      </div>
    );
  }

  if (error && rooms.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="text-center">
          <AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-4" />
          <p className="text-zinc-400 mb-4">{error}</p>
          <button
            onClick={loadRooms}
            className="px-4 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-mono uppercase tracking-widest transition-all inline-flex items-center gap-2"
          >
            <RefreshCw className="w-4 h-4" />
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-8">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-12">
          <h1 className="text-4xl font-bold tracking-tighter text-white uppercase mb-4">
            Welcome to Chat
          </h1>
          <p className="text-zinc-400">
            Join rooms to connect with the community and start conversations
          </p>
        </div>

        {/* Error banner */}
        {error && (
          <div className="mb-6 p-4 bg-red-500/10 border border-red-500/20 text-red-400 text-sm flex items-center justify-between">
            <span>{error}</span>
            <button
              onClick={loadRooms}
              className="text-red-300 hover:text-red-200 underline text-xs"
            >
              Retry
            </button>
          </div>
        )}

        {/* Rooms Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {rooms.map((room) => (
            <div
              key={room.id}
              className="border border-white/10 bg-zinc-900/50 p-6 hover:bg-zinc-900 transition-colors group"
            >
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-zinc-800 border border-white/10 flex items-center justify-center">
                    <RoomIcon slug={room.slug} name={room.name} size="md" className="text-zinc-500" />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-white">{room.name}</h3>
                    <div className="flex items-center gap-2 text-xs text-zinc-500 mt-1">
                      <Users className="w-3 h-3" />
                      <span>{room.member_count} members</span>
                    </div>
                  </div>
                </div>

                {room.is_default && (
                  <div className="px-2 py-1 bg-emerald-900/20 border border-emerald-500/20 text-emerald-400 text-[9px] uppercase tracking-wider font-mono rounded">
                    Popular
                  </div>
                )}
              </div>

              <p className="text-sm text-zinc-400 mb-4 min-h-[40px]">
                {room.description || 'No description'}
              </p>

              {room.is_member ? (
                <button
                  onClick={() => navigate(`/chat/${room.slug}`)}
                  className="w-full flex items-center justify-center gap-2 py-2 px-4 bg-white/10 hover:bg-white/20 text-white text-xs font-mono uppercase tracking-widest transition-all group"
                >
                  <span>Open Room</span>
                  <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                </button>
              ) : (
                <button
                  onClick={() => handleJoinRoom(room.slug)}
                  className="w-full py-2 px-4 bg-white text-black hover:bg-zinc-200 text-xs font-mono uppercase tracking-widest font-bold transition-all"
                >
                  Join Room
                </button>
              )}
            </div>
          ))}
        </div>

        {rooms.length === 0 && (
          <div className="text-center py-12">
            <p className="text-zinc-500">No rooms available</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default ChatLobby;
