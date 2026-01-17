import { useEffect, useState, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Users, UserPlus, LogOut, RefreshCw, AlertCircle } from 'lucide-react';
import { chatRooms, chatMessages } from '../../api/chatClient';
import { useChatWebSocket } from '../../hooks/useChatWebSocket';
import { MessageList } from '../../components/chat/MessageList';
import { MessageInput } from '../../components/chat/MessageInput';
import { RoomIcon } from '../../components/chat/RoomIcon';
import type { ChatRoom as ChatRoomType, ChatMessage, ChatUser } from '../../types/chat';

export default function ChatRoom() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();

  const [room, setRoom] = useState<ChatRoomType | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [onlineUsers, setOnlineUsers] = useState<ChatUser[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [isMember, setIsMember] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Track if messages have been loaded to prevent race condition
  const messagesLoadedRef = useRef(false);

  // WebSocket connection
  const { isConnected, isReconnecting, joinRoom, leaveRoom, sendMessage, sendTyping } = useChatWebSocket({
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
        setError(null);
        const roomData = await chatRooms.get(slug);
        setRoom(roomData);

        // Check if we're a member
        const roomsList = await chatRooms.list();
        const roomInfo = roomsList.find((r) => r.slug === slug);
        setIsMember(roomInfo?.is_member || false);
      } catch (err) {
        console.error('Failed to load room:', err);
        setError('Failed to load room. Please try again.');
      }
    };

    loadRoom();
  }, [slug]);

  // Load messages - separate effect that only runs once isMember is true
  useEffect(() => {
    if (!slug || !isMember) return;

    const loadMessages = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const data = await chatMessages.getMessages(slug, undefined, 50);
        setMessages(data.messages);
        setNextCursor(data.next_cursor);
        setHasMore(data.has_more);
        messagesLoadedRef.current = true;

        // Mark room as read
        await chatRooms.markRead(slug);
      } catch (err) {
        console.error('Failed to load messages:', err);
        setError('Failed to load messages. Please try again.');
      } finally {
        setIsLoading(false);
      }
    };

    loadMessages();

    return () => {
      messagesLoadedRef.current = false;
    };
  }, [slug, isMember]);

  // Join WebSocket room only after messages are loaded
  useEffect(() => {
    if (!slug || !isMember || !isConnected || !messagesLoadedRef.current) return;

    joinRoom(slug);

    return () => {
      leaveRoom(slug);
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
    } catch (err) {
      console.error('Failed to load more messages:', err);
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
      setError(null);
      await chatRooms.join(slug);
      setIsMember(true);
    } catch (err) {
      console.error('Failed to join room:', err);
      setError('Failed to join room. Please try again.');
    }
  };

  const handleLeaveRoom = async () => {
    if (!slug) return;

    try {
      await chatRooms.leave(slug);
      navigate('/chat');
    } catch (err) {
      console.error('Failed to leave room:', err);
      setError('Failed to leave room. Please try again.');
    }
  };

  const handleRetry = () => {
    setError(null);
    setIsLoading(true);
    // Trigger reload by resetting isMember state
    if (isMember) {
      messagesLoadedRef.current = false;
      // Force re-fetch
      const loadMessages = async () => {
        try {
          if (!slug) return;
          const data = await chatMessages.getMessages(slug, undefined, 50);
          setMessages(data.messages);
          setNextCursor(data.next_cursor);
          setHasMore(data.has_more);
          messagesLoadedRef.current = true;
          await chatRooms.markRead(slug);
        } catch (err) {
          console.error('Failed to load messages:', err);
          setError('Failed to load messages. Please try again.');
        } finally {
          setIsLoading(false);
        }
      };
      loadMessages();
    } else {
      window.location.reload();
    }
  };

  // Error state
  if (error && !room) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="text-center">
          <AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-4" />
          <p className="text-zinc-400 mb-4">{error}</p>
          <button
            onClick={handleRetry}
            className="px-4 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-mono uppercase tracking-widest transition-all inline-flex items-center gap-2"
          >
            <RefreshCw className="w-4 h-4" />
            Retry
          </button>
        </div>
      </div>
    );
  }

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
            <RoomIcon slug={room.slug} name={room.name} size="xl" className="text-zinc-500" />
          </div>

          <h2 className="text-2xl font-bold text-white mb-2">{room.name}</h2>
          <p className="text-zinc-400 mb-6">{room.description}</p>

          <div className="flex items-center justify-center gap-2 text-xs text-zinc-500 mb-6">
            <Users className="w-4 h-4" />
            <span>{room.member_count} members</span>
          </div>

          {error && (
            <p className="text-red-400 text-sm mb-4">{error}</p>
          )}

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

  // Determine disabled reason for MessageInput
  const getInputDisabledReason = (): string | undefined => {
    if (!isConnected) {
      if (isReconnecting) {
        return 'Reconnecting to server...';
      }
      return 'Disconnected from server';
    }
    return undefined;
  };

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Header */}
      <div className="p-4 border-b border-white/10 bg-zinc-900">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-zinc-800 border border-white/10 flex items-center justify-center">
              <RoomIcon slug={room.slug} name={room.name} size="sm" className="text-zinc-500" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-white">{room.name}</h2>
              <p className="text-xs text-zinc-500">{room.description}</p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-xs text-zinc-500">
              <div className={`w-2 h-2 rounded-full ${
                isConnected
                  ? 'bg-emerald-500'
                  : isReconnecting
                    ? 'bg-amber-500 animate-pulse'
                    : 'bg-zinc-600'
              }`} />
              <span>
                {isReconnecting ? 'Reconnecting...' : `${onlineUsers.length} online`}
              </span>
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

        {/* Error banner */}
        {error && (
          <div className="mt-3 p-2 bg-red-500/10 border border-red-500/20 text-red-400 text-xs flex items-center justify-between">
            <span>{error}</span>
            <button
              onClick={handleRetry}
              className="text-red-300 hover:text-red-200 underline"
            >
              Retry
            </button>
          </div>
        )}
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
        disabledReason={getInputDisabledReason()}
      />
    </div>
  );
}
