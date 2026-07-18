import { Send, Loader2, Paperclip } from 'lucide-react'
import type { ThreadTheme } from './theme'
import type { ThreadController } from './useThreadController'

interface ChatComposerProps {
  c: ThreadController
  th: ThreadTheme
  isFinalized: boolean
  isArchived: boolean
  inputDisabled: boolean
}

export default function ChatComposer({ c, th, isFinalized, isArchived, inputDisabled }: ChatComposerProps) {
  const {
    error, setError, fileInputRef, handleFileUpload, lightMode, input, setInput,
    threadId, threadSocketRef, lastTypingSentRef, handleKeyDown, textareaRef, streaming, handleSend,
  } = c

  return (
    <>
      {/* Error */}
      {error && (
        <div className="mx-4 mb-2 p-2 bg-red-900/30 border border-red-800 rounded text-red-300 text-xs flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError('')} className="text-red-200 hover:text-white text-xs underline ml-2 shrink-0">
            Dismiss
          </button>
        </div>
      )}

      {/* Input */}
      <div className={`px-4 py-3 border-t ${th.border} pb-[env(safe-area-inset-bottom)]`}>
        {isFinalized ? (
          <div className="text-center text-sm text-zinc-500 py-2">
            This thread has been finalized.
          </div>
        ) : isArchived ? (
          <div className="text-center text-sm text-zinc-500 py-2">
            This thread has been archived.
          </div>
        ) : (
          <div className="flex items-end gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.doc,.docx,.txt,.csv,.xlsx,.xls"
              className="hidden"
              multiple
              onChange={(e) => {
                const files = e.target.files ? Array.from(e.target.files) : []
                if (files.length > 0) handleFileUpload(files)
                e.target.value = ''
              }}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={inputDisabled}
              title="Upload files (resumes, invoices, spreadsheets)"
              className={`p-3 rounded-lg transition-colors disabled:opacity-40 ${
                lightMode ? 'text-zinc-400 hover:text-zinc-700 hover:bg-zinc-100' : 'text-zinc-400 hover:text-white hover:bg-zinc-800'
              }`}
            >
              <Paperclip size={16} />
            </button>
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => {
                setInput(e.target.value)
                // Throttle typing indicator to once per 2 seconds
                if (threadId && threadSocketRef.current && Date.now() - lastTypingSentRef.current > 2000) {
                  threadSocketRef.current.sendTyping(threadId)
                  lastTypingSentRef.current = Date.now()
                }
              }}
              onKeyDown={handleKeyDown}
              placeholder="Type a message..."
              rows={1}
              disabled={inputDisabled}
              className={`flex-1 text-sm rounded-lg px-3 py-2.5 border focus:outline-none resize-none disabled:opacity-50 min-h-[44px] ${th.textarea}`}
            />
            <button
              onClick={() => handleSend()}
              disabled={inputDisabled || !input.trim()}
              className="p-3 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg transition-colors disabled:opacity-40 disabled:hover:bg-emerald-600"
            >
              {streaming ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Send size={16} />
              )}
            </button>
          </div>
        )}
      </div>
    </>
  )
}
