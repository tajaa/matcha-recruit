import { useState, useRef, type KeyboardEvent } from 'react';
import { Send } from 'lucide-react';

interface MessageInputProps {
  onSendMessage: (content: string) => void;
  onTyping?: () => void;
  disabled?: boolean;
  disabledReason?: string;
}

export function MessageInput({ onSendMessage, onTyping, disabled, disabledReason }: MessageInputProps) {
  const [message, setMessage] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const lastTypingSentRef = useRef(0);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setMessage(e.target.value);

    // Send typing indicator (throttled)
    if (onTyping) {
      const now = Date.now();
      if (now - lastTypingSentRef.current >= 1000) {
        onTyping();
        lastTypingSentRef.current = now;
      }
    }

    // Auto-resize textarea
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 120)}px`;
    }
  };

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();

    const trimmed = message.trim();
    if (!trimmed || disabled) return;

    if (trimmed.length > 2000) {
      alert('Message is too long (max 2000 characters)');
      return;
    }

    onSendMessage(trimmed);
    setMessage('');

    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter to send, Shift+Enter for newline
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <form onSubmit={handleSubmit} className="p-4 border-t border-white/10 bg-zinc-900">
      <div className="flex items-end gap-2">
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            value={message}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            placeholder="Type a message... (Enter to send, Shift+Enter for new line)"
            rows={1}
            className="w-full px-4 py-3 bg-zinc-950 border border-white/10 text-sm text-white placeholder-zinc-600 focus:border-white/30 focus:ring-0 focus:outline-none transition-colors resize-none disabled:opacity-50 disabled:cursor-not-allowed"
            style={{ minHeight: '48px', maxHeight: '120px' }}
          />
          <div className="absolute bottom-2 right-2 text-[10px] text-zinc-600 font-mono">
            {message.length}/2000
          </div>
        </div>

        <button
          type="submit"
          disabled={!message.trim() || disabled}
          className="p-3 bg-white text-black hover:bg-zinc-200 disabled:bg-white/10 disabled:text-zinc-600 disabled:cursor-not-allowed transition-all"
        >
          <Send className="w-5 h-5" />
        </button>
      </div>

      <div className="mt-2 text-[10px] text-zinc-600">
        {disabled && disabledReason ? (
          <span className="text-amber-500">{disabledReason}</span>
        ) : (
          <>
            Press <kbd className="px-1 py-0.5 bg-white/5 border border-white/10 rounded">Enter</kbd> to send,{' '}
            <kbd className="px-1 py-0.5 bg-white/5 border border-white/10 rounded">Shift</kbd> +{' '}
            <kbd className="px-1 py-0.5 bg-white/5 border border-white/10 rounded">Enter</kbd> for new line
          </>
        )}
      </div>
    </form>
  );
}
