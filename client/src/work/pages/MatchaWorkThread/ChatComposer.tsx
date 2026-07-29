import { Send, Loader2, Paperclip, X } from 'lucide-react'
import type { ThreadTheme } from './theme'
import type { ThreadController } from './useThreadController'
import HuumeAvatar from '../../components/panels/HuumeAvatar'

interface ChatComposerProps {
  c: ThreadController
  th: ThreadTheme
  isFinalized: boolean
  isArchived: boolean
  inputDisabled: boolean
}

export default function ChatComposer({ c, th, isFinalized, isArchived, inputDisabled }: ChatComposerProps) {
  const {
    error, setError, fileInputRef, handleFileUpload, lightMode, input,
    threadId, threadSocketRef, lastTypingSentRef, handleKeyDown, handleInputChange, textareaRef, streaming, handleSend,
    mentionQuery, mentionMatches, applyHuumeMention, thread, modeValue, handleModeToggle, togglingMode,
  } = c

  const huumeOn = modeValue('huume')
  const togglingHuume = togglingMode === 'huume'

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
          <>
            {huumeOn && thread && (
              <div className="flex items-center gap-1.5 mb-2">
                <div className={`flex items-center gap-1.5 pl-1.5 pr-1 py-1 rounded-full border ${
                  lightMode ? 'bg-orange-50 border-orange-300' : 'bg-orange-950/30 border-orange-800/60'
                }`}>
                  <HuumeAvatar size="sm" lightMode={lightMode} />
                  <span className={`text-xs font-medium ${lightMode ? 'text-orange-700' : 'text-orange-300'}`}>Huume</span>
                  <button
                    type="button"
                    onClick={() => handleModeToggle('huume')}
                    disabled={togglingHuume}
                    title="Turn Huume off for this thread"
                    className={`p-0.5 rounded-full transition-colors disabled:opacity-50 ${
                      lightMode ? 'text-orange-400 hover:text-orange-700 hover:bg-orange-100' : 'text-orange-500 hover:text-orange-200 hover:bg-orange-900/40'
                    }`}
                  >
                    {togglingHuume ? <Loader2 size={11} className="animate-spin" /> : <X size={11} />}
                  </button>
                </div>
              </div>
            )}
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
              <div className="flex-1 relative">
                {mentionQuery !== null && mentionMatches.length > 0 && (
                  <div className={`absolute bottom-full left-0 mb-1 w-full max-w-xs rounded-lg shadow-xl z-20 overflow-hidden border ${
                    lightMode ? 'bg-white border-zinc-200' : 'bg-zinc-900 border-zinc-700'
                  }`}>
                    <div className={`px-2 py-1 text-[10px] uppercase tracking-wide border-b ${
                      lightMode ? 'text-zinc-400 border-zinc-200' : 'text-zinc-500 border-zinc-700'
                    }`}>
                      Mention an agent
                    </div>
                    {mentionMatches.map((m) => (
                      <button
                        key={m.key}
                        type="button"
                        onMouseDown={(e) => { e.preventDefault(); applyHuumeMention() }}
                        className={`w-full text-left px-3 py-2 text-sm flex items-center gap-2 ${
                          lightMode ? 'hover:bg-zinc-100' : 'hover:bg-zinc-800'
                        }`}
                      >
                        <HuumeAvatar size="sm" lightMode={lightMode} />
                        <span className="min-w-0 flex-1">
                          <span className={`block font-medium ${lightMode ? 'text-zinc-800' : 'text-zinc-100'}`}>{m.label}</span>
                          <span className={`block text-[11px] truncate ${lightMode ? 'text-zinc-500' : 'text-zinc-400'}`}>{m.description}</span>
                        </span>
                      </button>
                    ))}
                  </div>
                )}
                <textarea
                  ref={textareaRef}
                  value={input}
                  onChange={(e) => {
                    handleInputChange(e)
                    // Throttle typing indicator to once per 2 seconds
                    if (threadId && threadSocketRef.current && Date.now() - lastTypingSentRef.current > 2000) {
                      threadSocketRef.current.sendTyping(threadId)
                      lastTypingSentRef.current = Date.now()
                    }
                  }}
                  onKeyDown={handleKeyDown}
                  placeholder={huumeOn ? 'Ask Huume...' : 'Type a message...'}
                  rows={1}
                  disabled={inputDisabled}
                  className={`w-full text-sm rounded-lg px-3 py-2.5 border focus:outline-none resize-none disabled:opacity-50 min-h-[44px] ${th.textarea} ${
                    huumeOn ? 'ring-2 ring-orange-500/50' : ''
                  }`}
                />
              </div>
              <button
                onClick={() => handleSend()}
                disabled={inputDisabled || !input.trim() || togglingHuume}
                className="p-3 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg transition-colors disabled:opacity-40 disabled:hover:bg-emerald-600"
              >
                {streaming ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <Send size={16} />
                )}
              </button>
            </div>
          </>
        )}
      </div>
    </>
  )
}
