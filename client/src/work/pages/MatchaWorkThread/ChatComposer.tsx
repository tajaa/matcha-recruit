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
    pendingAttachments, removePendingAttachment, uploadingFiles,
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
      <div className={`px-3 py-2 border-t ${th.border} pb-[env(safe-area-inset-bottom)]`}>
        {isFinalized ? (
          <div className="text-center text-sm text-w-faint py-2">
            This thread has been finalized.
          </div>
        ) : isArchived ? (
          <div className="text-center text-sm text-w-faint py-2">
            This thread has been archived.
          </div>
        ) : (
          <>
            {huumeOn && thread && (
              <div className="flex items-center gap-1.5 mb-1.5">
                <div className="flex items-center gap-1.5 pl-1.5 pr-1 py-0.5 rounded-full border bg-w-accent/10 border-w-accent/30">
                  <HuumeAvatar size="sm" lightMode={lightMode} />
                  <span className="text-xs font-medium text-w-accent">Huume</span>
                  <button
                    type="button"
                    onClick={() => handleModeToggle('huume')}
                    disabled={togglingHuume}
                    title="Turn Huume off for this thread"
                    className="p-0.5 rounded-full transition-colors disabled:opacity-50 text-w-accent/70 hover:text-w-accent hover:bg-w-accent/10"
                  >
                    {togglingHuume ? <Loader2 size={11} className="animate-spin" /> : <X size={11} />}
                  </button>
                </div>
              </div>
            )}
            {pendingAttachments.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-2">
                {pendingAttachments.map((a) => (
                  <span key={a.url} className="inline-flex items-center gap-1.5 pl-2 pr-1 py-1 rounded-full border text-xs bg-w-surface2 border-w-line text-w-text">
                    <Paperclip size={11} className="shrink-0 text-w-dim" />
                    <span className="max-w-[180px] truncate">{a.filename}</span>
                    <button
                      type="button"
                      onClick={() => removePendingAttachment(a.url)}
                      title="Remove attachment"
                      className="p-0.5 rounded-full text-w-dim hover:text-w-text hover:bg-w-surface"
                    >
                      <X size={11} />
                    </button>
                  </span>
                ))}
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
                disabled={inputDisabled || uploadingFiles}
                title="Upload files (resumes, invoices, spreadsheets)"
                className="p-2 rounded-lg transition-colors disabled:opacity-40 text-w-dim hover:text-w-text hover:bg-w-surface2"
              >
                {uploadingFiles ? <Loader2 size={16} className="animate-spin" /> : <Paperclip size={16} />}
              </button>
              <div className="flex-1 relative">
                {mentionQuery !== null && mentionMatches.length > 0 && (
                  <div className="absolute bottom-full left-0 mb-1 w-full max-w-xs rounded-lg shadow-xl z-20 overflow-hidden border bg-w-surface border-w-line">
                    <div className="px-2 py-1 text-[10px] uppercase tracking-wide border-b text-w-faint border-w-line">
                      Mention an agent
                    </div>
                    {mentionMatches.map((m) => (
                      <button
                        key={m.key}
                        type="button"
                        onMouseDown={(e) => { e.preventDefault(); applyHuumeMention() }}
                        className="w-full text-left px-3 py-2 text-sm flex items-center gap-2 hover:bg-w-surface2"
                      >
                        <HuumeAvatar size="sm" lightMode={lightMode} />
                        <span className="min-w-0 flex-1">
                          <span className="block font-medium text-w-text">{m.label}</span>
                          <span className="block text-[11px] truncate text-w-faint">{m.description}</span>
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
                  className={`w-full text-[13px] rounded-lg px-3 py-2 border focus:outline-none resize-none disabled:opacity-50 min-h-[36px] ${th.textarea} ${
                    huumeOn ? 'ring-2 ring-w-accent/50' : ''
                  }`}
                />
              </div>
              <button
                onClick={() => handleSend()}
                disabled={inputDisabled || (!input.trim() && pendingAttachments.length === 0) || togglingHuume}
                className="p-2 bg-w-accent hover:bg-w-accent-hi text-white rounded-lg transition-colors disabled:opacity-40 disabled:hover:bg-w-accent"
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
