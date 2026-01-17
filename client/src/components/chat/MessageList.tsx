import { useEffect, useRef, useMemo } from 'react';
import type { ChatMessage } from '../../types/chat';
import { formatMessageTime, getInitials, isOnline } from '../../types/chat';
import { useChatAuth } from '../../context/ChatAuthContext';

interface MessageListProps {
  messages: ChatMessage[];
  onLoadMore?: () => void;
  hasMore?: boolean;
  isLoading?: boolean;
}

export function MessageList({ messages, onLoadMore, hasMore, isLoading }: MessageListProps) {
  const { user: currentUser } = useChatAuth();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const prevScrollHeightRef = useRef<number>(0);
  const shouldAutoScrollRef = useRef(true);

  // Group messages by date
  const groupedMessages = useMemo(() => {
    const groups: { date: string; messages: ChatMessage[] }[] = [];
    let currentDate = '';

    messages.forEach((msg) => {
      const msgDate = new Date(msg.created_at).toLocaleDateString();
      if (msgDate !== currentDate) {
        currentDate = msgDate;
        groups.push({ date: msgDate, messages: [] });
      }
      groups[groups.length - 1].messages.push(msg);
    });

    return groups;
  }, [messages]);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (shouldAutoScrollRef.current && messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  // Handle scroll for load more
  const handleScroll = () => {
    const container = messagesContainerRef.current;
    if (!container) return;

    // Check if user is near bottom
    const { scrollTop, scrollHeight, clientHeight } = container;
    const isNearBottom = scrollHeight - scrollTop - clientHeight < 100;
    shouldAutoScrollRef.current = isNearBottom;

    // Load more when scrolled to top
    if (scrollTop < 100 && hasMore && !isLoading && onLoadMore) {
      prevScrollHeightRef.current = scrollHeight;
      onLoadMore();
    }
  };

  // Maintain scroll position after loading more
  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container || prevScrollHeightRef.current === 0) return;

    const newScrollHeight = container.scrollHeight;
    const scrollDiff = newScrollHeight - prevScrollHeightRef.current;
    container.scrollTop = scrollDiff;
    prevScrollHeightRef.current = 0;
  }, [messages.length]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-zinc-500">
        <div className="text-center">
          <p className="text-sm">No messages yet</p>
          <p className="text-xs mt-1">Be the first to say something!</p>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={messagesContainerRef}
      onScroll={handleScroll}
      className="flex-1 overflow-y-auto p-4 space-y-6"
    >
      {isLoading && hasMore && (
        <div className="text-center py-2">
          <div className="inline-block w-2 h-2 bg-emerald-400 rounded-full animate-pulse" />
        </div>
      )}

      {groupedMessages.map((group) => (
        <div key={group.date} className="space-y-3">
          {/* Date divider */}
          <div className="flex items-center gap-3">
            <div className="flex-1 h-px bg-white/10" />
            <div className="text-[10px] text-zinc-600 font-mono uppercase tracking-wider">
              {group.date === new Date().toLocaleDateString() ? 'Today' : group.date}
            </div>
            <div className="flex-1 h-px bg-white/10" />
          </div>

          {/* Messages */}
          {group.messages.map((msg, idx) => {
            const isOwn = msg.user_id === currentUser?.id;
            const showAvatar = idx === 0 || group.messages[idx - 1].user_id !== msg.user_id;
            const user = msg.user;

            return (
              <div
                key={msg.id}
                className={`flex gap-3 ${isOwn ? 'flex-row-reverse' : 'flex-row'} ${
                  !showAvatar ? 'ml-11' : ''
                }`}
              >
                {/* Avatar */}
                {showAvatar && user && (
                  <div className="flex-shrink-0 relative">
                    <div className="w-8 h-8 bg-zinc-800 border border-white/10 flex items-center justify-center text-xs font-bold text-white">
                      {getInitials(user)}
                    </div>
                    {isOnline(user) && (
                      <div className="absolute bottom-0 right-0 w-2.5 h-2.5 bg-emerald-500 border-2 border-zinc-900 rounded-full" />
                    )}
                  </div>
                )}

                {/* Message */}
                <div className={`flex-1 max-w-xl ${isOwn ? 'items-end' : 'items-start'} flex flex-col`}>
                  {showAvatar && user && (
                    <div className={`flex items-baseline gap-2 mb-1 ${isOwn ? 'flex-row-reverse' : 'flex-row'}`}>
                      <span className="text-xs font-medium text-white">
                        {user.first_name} {user.last_name}
                      </span>
                      <span className="text-[10px] text-zinc-600 font-mono">
                        {formatMessageTime(msg.created_at)}
                      </span>
                    </div>
                  )}

                  <div
                    className={`px-4 py-2 ${
                      isOwn
                        ? 'bg-white text-black'
                        : 'bg-zinc-800 text-white border border-white/10'
                    }`}
                  >
                    <p className="text-sm whitespace-pre-wrap break-words">{msg.content}</p>
                    {msg.edited_at && (
                      <span className="text-[10px] text-zinc-500 mt-1 block">
                        (edited)
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ))}

      <div ref={messagesEndRef} />
    </div>
  );
}
