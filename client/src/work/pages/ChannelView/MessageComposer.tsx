import { Send, Loader2, Paperclip, X, FileText, Image as ImageIcon } from 'lucide-react'
import type { ChannelMember } from '../../api/channels'
import { handleFromEmail } from './mentions'

interface MessageComposerProps {
  pendingFiles: File[]
  setPendingFiles: React.Dispatch<React.SetStateAction<File[]>>
  fileInputRef: React.RefObject<HTMLInputElement>
  mentionQuery: string | null
  mentionMatches: ChannelMember[]
  applyMention: (member: ChannelMember) => void
  inputTextareaRef: React.RefObject<HTMLTextAreaElement>
  input: string
  onInputChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void
  onKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void
  channelName: string | undefined
  onSend: () => void
  uploading: boolean
}

export default function MessageComposer({
  pendingFiles,
  setPendingFiles,
  fileInputRef,
  mentionQuery,
  mentionMatches,
  applyMention,
  inputTextareaRef,
  input,
  onInputChange,
  onKeyDown,
  channelName,
  onSend,
  uploading,
}: MessageComposerProps) {
  return (
    <div className="px-4 py-3 border-t border-w-line shrink-0">
      {/* Pending file previews */}
      {pendingFiles.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {pendingFiles.map((f, i) => (
            <div key={i} className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-w-surface2 border border-w-line text-xs text-w-text">
              {f.type.startsWith('image/') ? <ImageIcon size={11} /> : <FileText size={11} />}
              <span className="truncate max-w-[150px]">{f.name}</span>
              <button onClick={() => setPendingFiles(prev => prev.filter((_, j) => j !== i))} className="text-w-dim hover:text-w-text">
                <X size={10} />
              </button>
            </div>
          ))}
        </div>
      )}
      <div className="flex items-end gap-2">
        <button
          onClick={() => fileInputRef.current?.click()}
          className="p-2 text-w-dim hover:text-w-text transition-colors shrink-0"
          title="Attach files"
        >
          <Paperclip size={16} />
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          hidden
          onChange={(e) => {
            const files = Array.from(e.target.files ?? [])
            if (files.length) setPendingFiles(prev => [...prev, ...files].slice(0, 5))
            e.target.value = ''
          }}
        />
        <div className="flex-1 relative">
          {mentionQuery !== null && mentionMatches.length > 0 && (
            <div className="absolute bottom-full left-0 mb-1 w-full max-w-xs bg-w-surface border border-w-line rounded-lg shadow-xl z-20 overflow-hidden">
              <div className="px-2 py-1 text-[10px] uppercase tracking-wide text-w-dim border-b border-w-line">
                Mention a member
              </div>
              {mentionMatches.map((m, i) => {
                const handle = handleFromEmail(m.email || '')
                return (
                  <button
                    key={m.user_id}
                    type="button"
                    onMouseDown={(e) => { e.preventDefault(); applyMention(m) }}
                    className={`w-full text-left px-3 py-1.5 text-sm flex items-center justify-between hover:bg-w-surface2 ${i === 0 ? 'bg-w-surface2/60' : ''}`}
                  >
                    <span className="text-w-text truncate">{m.name}</span>
                    <span className="text-w-accent text-xs ml-2 shrink-0">@{handle}</span>
                  </button>
                )
              })}
            </div>
          )}
          <textarea
            ref={inputTextareaRef}
            value={input}
            onChange={onInputChange}
            onKeyDown={onKeyDown}
            placeholder={`Message #${channelName ?? 'channel'}...`}
            rows={1}
            className="w-full px-3 py-2 bg-w-surface2 border border-w-line rounded-lg text-white text-sm placeholder:text-w-dim focus:outline-none focus:border-w-accent resize-none max-h-32"
            style={{ minHeight: '38px' }}
          />
        </div>
        <button
          onClick={onSend}
          disabled={(!input.trim() && pendingFiles.length === 0) || uploading}
          className="p-2 bg-w-accent hover:bg-w-accent-hi text-white rounded-lg transition-colors disabled:opacity-30 shrink-0"
        >
          {uploading ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
        </button>
      </div>
    </div>
  )
}
