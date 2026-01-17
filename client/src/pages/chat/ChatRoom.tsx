import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Hash, Users, UserPlus, LogOut } from 'lucide-react';
import { chatRooms, chatMessages } from '../../api/chatClient';
import { useChatWebSocket } from '../../hooks/useChatWebSocket';
import { useChatAuth } from '../../context/ChatAuthContext';
import { MessageList } from '../../components/chat/MessageList';
import { MessageInput } from '../../components/chat/MessageInput';
import type { ChatRoom, ChatMessage, ChatUser } from '../../types/chat';

export function ChatRoom() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const { user } = useChatAuth();

  const [room, setRoom] = useState<ChatRoom | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [onlineUsers, setOnlineUsers] = useState<ChatUser[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [isMember, setIsMember] = useState(false);

  // WebSocket connection
  const { isConnected, joinRoom, leaveRoom, sendMessage, sendTyping } = useChatWebSocket({
    onMessage: (message, roomSlug) => {
      if (roomSlug === slug) {
        setMessages((prev) => [...prev, message]);
      }
    },
    onUserJoined: (user, roomSlug) => {
      if (roomSlug === slug) {
        setOnlineUsers((prev) => {
          if (prev.find((u) => u.id === user.id)) return prev;
          return [...prev, user];
        });
      }
    },
    onUserLeft: (user, roomSlug) => {
      if (roomSlug === slug) {
        setOnlineUsers((prev) => prev.filter((u) => u.id !== user.id));
      }
    },
    onOnlineUsers: (users, roomSlug) => {
      if (roomSlug === slug) {
        setOnlineUsers(users);
      }
    },
  });

  // Load room info
  useEffect(() => {
    if (!slug) return;

    const loadRoom = async () => {
      try {
        const roomData = await chatRooms.get(slug);
        setRoom(roomData);

        // Check if we're a member
        const roomsList = await chatRooms.list();
        const roomInfo = roomsList.find((r) => r.slug === slug);
        setIsMember(roomInfo?.is_member || false);
      } catch (error) {
        console.error('Failed to load room:', error);
        navigate('/chat');
      }
    };

    loadRoom();
  }, [slug, navigate]);

  // Load messages and join room
  useEffect(() => {
    if (!slug || !isMember) return;

    const loadMessages = async () => {
      try {
        setIsLoading(true);
        const data = await chatMessages.getMessages(slug, undefined, 50);
        setMessages(data.messages);
        setNextCursor(data.next_cursor);
        setHasMore(data.has_more);

        // Join room via WebSocket
        if (isConnected) {
          joinRoom(slug);
        }

        // Mark room as read
        await chatRooms.markRead(slug);
      } catch (error) {
        console.error('Failed to load messages:', error);
      } finally {
        setIsLoading(false);
      }
    };

    loadMessages();

    return () => {
      if (slug && isConnected) {
        leaveRoom(slug);
      }
    };
  }, [slug, isMember, isConnected, joinRoom, leaveRoom]);

  const handleLoadMore = useCallback(async () => {
    if (!slug || !nextCursor || isLoadingMore || !hasMore) return;

    try {
      setIsLoadingMore(true);
      const data = await chatMessages.getMessages(slug, nextCursor, 50);
      setMessages((prev) => [...data.messages, ...prev]);
      setNextCursor(data.next_cursor);
      setHasMore(data.has_more);
    } catch (error) {
      console.error('Failed to load more messages:', error);
    } finally {
      setIsLoadingMore(false);
    }
  }, [slug, nextCursor, isLoadingMore, hasMore]);

  const handleSendMessage = useCallback(
    (content: string) => {
      if (!slug) return;
      sendMessage(slug, content);
    },
    [slug, sendMessage]
  );

  const handleTyping = useCallback(() => {
    if (!slug) return;
    sendTyping(slug);
  }, [slug, sendTyping]);

  const handleJoinRoom = async () => {
    if (!slug) return;

    try {
      await chatRooms.join(slug);
      setIsMember(true);
    } catch (error) {
      console.error('Failed to join room:', error);
    }
  };

  const handleLeaveRoom = async () => {
    if (!slug) return;

    try {
      await chatRooms.leave(slug);
      navigate('/chat');
    } catch (error) {
      console.error('Failed to leave room:', error);
    }
  };

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
      </div>
    );
  }

  if (!room) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-zinc-500">Room not found</p>
      </div>
    );
  }

  if (!isMember) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="max-w-md text-center">
          <div className="w-16 h-16 bg-zinc-800 border border-white/10 flex items-center justify-center mx-auto mb-6">
            {room.icon ? (
              <span className="text-3xl">{room.icon}</span>
            ) : (
              <Hash className="w-8 h-8 text-zinc-500" />
            )}
          </div>

          <h2 className="text-2xl font-bold text-white mb-2">{room.name}</h2>
          <p className="text-zinc-400 mb-6">{room.description}</p>

          <div className="flex items-center justify-center gap-2 text-xs text-zinc-500 mb-6">
            <Users className="w-4 h-4" />
            <span>{room.member_count} members</span>
          </div>

          <button
            onClick={handleJoinRoom}
            className="px-6 py-3 bg-white text-black hover:bg-zinc-200 text-xs font-mono uppercase tracking-widest font-bold transition-all inline-flex items-center gap-2"
          >
            <UserPlus className="w-4 h-4" />
            Join Room
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Header */}
      <div className="p-4 border-b border-white/10 bg-zinc-900">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-zinc-800 border border-white/10 flex items-center justify-center">
              {room.icon ? (
                <span className="text-lg">{room.icon}</span>
              ) : (
                <Hash className="w-4 h-4 text-zinc-500" />
              )}
            </div>
            <div>
              <h2 className="text-sm font-bold text-white">{room.name}</h2>
              <p className="text-xs text-zinc-500">{room.description}</p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-xs text-zinc-500">
              <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-500' : 'bg-zinc-600'}`} />
              <span>{onlineUsers.length} online</span>
            </div>

            <button
              onClick={handleLeaveRoom}
              className="p-2 hover:bg-white/5 rounded transition-colors text-zinc-500 hover:text-zinc-300"
              title="Leave room"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Messages */}
      <MessageList
        messages={messages}
        onLoadMore={handleLoadMore}
        hasMore={hasMore}
        isLoading={isLoadingMore}
      />

      {/* Input */}
      <MessageInput
        onSendMessage={handleSendMessage}
        onTyping={handleTyping}
        disabled={!isConnected}
      />
    </div>
  );
}

export default ChatRoom;
