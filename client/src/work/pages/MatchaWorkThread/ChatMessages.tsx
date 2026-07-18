import { Loader2 } from 'lucide-react'
import MessageBubble from '../../components/panels/MessageBubble'
import { addProjectSection } from '../../api/matchaWork'
import SkillGrid from './SkillGrid'
import type { ThreadTheme } from './theme'
import type { ThreadController } from './useThreadController'

interface ChatMessagesProps {
  c: ThreadController
  th: ThreadTheme
  isProject: boolean
}

// Messages — drop zone for resumes
export default function ChatMessages({ c, th, isProject }: ChatMessagesProps) {
  const {
    streaming, setIsDragOver, isDragOver, handleFileUpload, lightMode, messages,
    statusMessage, typingUsers, messagesEndRef, threadId, setThread,
    isIndividual, setInput, textareaRef, setShowTutorSetup, setTutorDismissed,
  } = c

  return (
    <div
      className="flex-1 overflow-y-auto px-4 py-4 space-y-4 relative"
      onDragOver={(e) => { e.preventDefault(); if (!streaming) setIsDragOver(true) }}
      onDragLeave={(e) => {
        // Only hide overlay when leaving the container (not entering a child)
        if (e.currentTarget.contains(e.relatedTarget as Node)) return
        setIsDragOver(false)
      }}
      onDrop={(e) => {
        e.preventDefault()
        setIsDragOver(false)
        const files = Array.from(e.dataTransfer.files)
        if (files.length > 0) handleFileUpload(files)
      }}
    >
      {isDragOver && (
        <div className="absolute inset-0 z-10 bg-emerald-600/10 border-2 border-dashed border-emerald-500 rounded-lg flex items-center justify-center pointer-events-none">
          <p className={`text-sm font-medium ${lightMode ? 'text-emerald-700' : 'text-emerald-400'}`}>
            Drop files here (resumes, invoices, spreadsheets)
          </p>
        </div>
      )}

      {messages.length === 0 && (
        <SkillGrid
          isIndividual={isIndividual}
          isProject={isProject}
          lightMode={lightMode}
          th={th}
          setInput={setInput}
          textareaRef={textareaRef}
          setShowTutorSetup={setShowTutorSetup}
          setTutorDismissed={setTutorDismissed}
        />
      )}
      {messages.map((m) => (
        <MessageBubble
          key={m.id}
          message={m}
          lightMode={lightMode}
          isProjectThread={isProject}
          onAddToProject={isProject ? async (msgId, content) => {
            const result = await addProjectSection(threadId!, { content, source_message_id: msgId })
            setThread((prev) => prev ? { ...prev, current_state: result.current_state, version: result.version } : prev)
          } : undefined}
        />
      ))}

      {streaming && (
        <div className="flex justify-start">
          <div className={`${th.streamBg} rounded-lg px-4 py-2.5 flex items-center gap-2`}>
            <Loader2 size={14} className={`animate-spin ${th.streamText}`} />
            <span className={`text-sm ${th.streamText}`}>{statusMessage || 'Thinking...'}</span>
          </div>
        </div>
      )}

      {typingUsers.size > 0 && (
        <div className={`text-xs ${th.streamText} px-1`}>
          {Array.from(typingUsers.values()).join(', ')}{' '}
          {typingUsers.size === 1 ? 'is' : 'are'} typing...
        </div>
      )}

      <div ref={messagesEndRef} />
    </div>
  )
}
