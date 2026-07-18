import { Link } from 'react-router-dom'
import { ArrowLeft, Send, Loader2, HelpCircle, UserPlus, Menu, Paperclip } from 'lucide-react'
import type { MWProject } from '../../types'
import MessageBubble from '../../components/panels/MessageBubble'
import RecruitingWizard from '../../components/panels/RecruitingWizard'
import CollaboratorPanel from '../../components/panels/CollaboratorPanel'
import { MODEL_OPTIONS, formatTokens } from '../../components/panels/constants'
import type { ProjectViewModel } from './useProjectView'

interface Props {
  vm: ProjectViewModel
  project: MWProject
  isRecruiting: boolean
  hasPanelTab: boolean
}

/** Center pane when the sidebar is in chats mode: header, message list, drop zone, input. */
export function ChatPane({ vm, project, isRecruiting, hasPanelTab }: Props) {
  const {
    base,
    setMobileMenuOpen,
    activeThread,
    projectId,
    showCollaborators,
    setShowCollaborators,
    selectedModel,
    setSelectedModel,
    usage24h,
    usageTotal,
    messages,
    setShowWizard,
    setShowTour,
    streaming,
    statusMessage,
    isDragOver,
    setIsDragOver,
    handleResumeDropForProject,
    isPostingFinalized,
    showWizard,
    dismissWizard,
    textareaRef,
    handleAddToProject,
    messagesEndRef,
    error,
    setError,
    resumeFileRef,
    input,
    setInput,
    handleSend,
  } = vm

  return (
    <div className={`flex-1 flex-col min-w-0 min-h-0 ${vm.activeTab === 'chat' ? 'flex' : 'hidden'}`}>
      {/* Header */}
      <div className="px-4 py-2 flex items-center gap-2" style={{ borderBottom: '1px solid var(--color-w-line)' }}>
        {isRecruiting ? (
          <Link to={base} className="text-[var(--color-w-dim)] hover:text-[var(--color-w-text)]" title="Back to workspace">
            <ArrowLeft size={14} />
          </Link>
        ) : (
          <button onClick={() => setMobileMenuOpen(true)} className="sm:hidden text-[var(--color-w-dim)] hover:text-[var(--color-w-text)]">
            <Menu size={14} />
          </button>
        )}
        <h2 className="text-xs font-medium truncate" style={{ color: 'var(--color-w-text)' }}>
          {project.title}
        </h2>
        {activeThread && (
          <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ color: 'var(--color-w-dim)', background: 'var(--color-w-surface2)' }}>
            {activeThread.title}
          </span>
        )}
        <div className="flex items-center gap-1.5 ml-auto">
          {/* Share / collaborators (admin only) */}
          {project.collaborator_role && (
            <div className="relative">
              <button
                onClick={() => { if (!showCollaborators) setShowCollaborators(true) }}
                className="p-1 rounded transition-colors"
                style={{ color: showCollaborators ? 'var(--color-w-accent)' : 'var(--color-w-dim)' }}
                title="Share project"
              >
                <UserPlus size={14} />
              </button>
              {showCollaborators && (
                <CollaboratorPanel
                  projectId={projectId!}
                  currentUserRole={project.collaborator_role}
                  onClose={() => setShowCollaborators(false)}
                />
              )}
            </div>
          )}
          {/* Model selector */}
          <select
            value={selectedModel}
            onChange={(e) => {
              setSelectedModel(e.target.value)
              localStorage.setItem('mw-model', e.target.value)
            }}
            className="shrink-0 text-[11px] font-medium rounded-full px-2.5 py-1 appearance-none cursor-pointer border-0"
            style={{ background: 'var(--color-w-surface2)', color: 'var(--color-w-dim)' }}
          >
            {MODEL_OPTIONS.map((m) => (
              <option key={m.id} value={m.id}>{m.label}</option>
            ))}
          </select>

          {/* Token counter */}
          {(usage24h?.totals.total_tokens || usageTotal?.totals.total_tokens) ? (
            <div className="hidden sm:flex items-center gap-1.5 text-[10px] font-mono" style={{ color: 'var(--color-w-dim)' }}>
              {usage24h && usage24h.totals.total_tokens > 0 && <span>24h: {formatTokens(usage24h.totals.total_tokens)}</span>}
              {usage24h?.totals.total_tokens && usageTotal?.totals.total_tokens ? <span>|</span> : null}
              {usageTotal && usageTotal.totals.total_tokens > 0 && <span>30d: {formatTokens(usageTotal.totals.total_tokens)}</span>}
            </div>
          ) : null}

          {project.project_type === 'recruiting' && messages.length === 0 && (
            <button
              onClick={() => setShowWizard(true)}
              title="How it works"
              className="p-1 rounded transition-colors text-[var(--color-w-dim)] hover:text-[var(--color-w-accent)]"
            >
              <HelpCircle size={14} />
            </button>
          )}
          {project.project_type !== 'recruiting' && (
            <button
              onClick={() => setShowTour(true)}
              title="Project tour"
              className="p-1 rounded transition-colors text-[var(--color-w-dim)] hover:text-[var(--color-w-accent)]"
            >
              <HelpCircle size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Messages + drop zone */}
      <div
        className="flex-1 overflow-y-auto px-4 py-4 space-y-4 relative"
        onDragOver={(e) => { e.preventDefault(); if (!streaming) setIsDragOver(true) }}
        onDragLeave={(e) => { if (e.currentTarget.contains(e.relatedTarget as Node)) return; setIsDragOver(false) }}
        onDrop={(e) => {
          e.preventDefault()
          setIsDragOver(false)
          const files = Array.from(e.dataTransfer.files)
          if (files.length > 0 && project?.project_type === 'recruiting') {
            handleResumeDropForProject(files)
          }
        }}
      >
        {isDragOver && project?.project_type === 'recruiting' && (
          <div
            className="absolute inset-0 z-10 border-2 border-dashed rounded-lg flex items-center justify-center pointer-events-none"
            style={{
              background: isPostingFinalized ? 'rgba(242,106,33,0.08)' : 'rgba(245,158,11,0.08)',
              borderColor: isPostingFinalized ? 'var(--color-w-accent)' : '#f59e0b',
            }}
          >
            <p className="text-sm font-medium" style={{ color: isPostingFinalized ? 'var(--color-w-accent)' : '#f59e0b' }}>
              {isPostingFinalized ? 'Drop resumes here to add candidates' : 'Finalize the posting first before adding resumes'}
            </p>
          </div>
        )}
        {messages.length === 0 && showWizard && project?.project_type === 'recruiting' ? (
          <div className="flex items-center justify-center h-full">
            <RecruitingWizard
              onDismiss={dismissWizard}
              onStartHiring={() => {
                dismissWizard()
                setTimeout(() => textareaRef.current?.focus(), 50)
              }}
            />
          </div>
        ) : messages.length === 0 ? (
          <div className="flex items-center justify-center h-full text-sm" style={{ color: 'var(--color-w-dim)' }}>
            {project?.project_type === 'recruiting'
              ? (isPostingFinalized
                  ? 'Posting finalized. Drop resumes to add candidates.'
                  : 'Describe the role you\'re hiring for, then click "Add to Project" to build the posting.')
              : hasPanelTab
              ? 'Start chatting — use "Add to Project" to build your document.'
              : 'Start chatting.'}
          </div>
        ) : null}
        {messages.map((m) => (
          <MessageBubble
            key={m.id}
            message={m}
            isProjectThread
            // Only offer "Add to Project" when a panel tab exists to view the
            // result — otherwise the section is written somewhere unreachable.
            onAddToProject={hasPanelTab ? (msgId, content) => handleAddToProject(msgId, content) : undefined}
          />
        ))}
        {streaming && (
          <div className="flex justify-start">
            <div className="rounded-lg px-4 py-2.5 flex items-center gap-2" style={{ background: 'var(--color-w-surface)', border: '1px solid var(--color-w-line)' }}>
              <Loader2 size={14} className="animate-spin" style={{ color: 'var(--color-w-dim)' }} />
              <span className="text-sm" style={{ color: 'var(--color-w-dim)' }}>{statusMessage || 'Thinking...'}</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Error */}
      {error && (
        <div className="mx-4 mb-2 p-2 bg-red-900/30 border border-red-800 rounded text-red-300 text-xs">
          {error}
          <button onClick={() => setError('')} className="ml-2 underline">Dismiss</button>
        </div>
      )}

      {/* Input */}
      <div className="px-4 py-3" style={{ borderTop: '1px solid var(--color-w-line)' }}>
        <div className="flex items-end gap-2">
          {project?.project_type === 'recruiting' && isPostingFinalized && (
            <>
              <input
                type="file"
                ref={resumeFileRef}
                multiple
                accept=".pdf,.doc,.docx,.txt"
                className="hidden"
                onChange={(e) => {
                  const files = Array.from(e.target.files || [])
                  if (files.length > 0) handleResumeDropForProject(files)
                  e.target.value = ''
                }}
              />
              <button
                onClick={() => resumeFileRef.current?.click()}
                disabled={streaming}
                className="p-2.5 rounded-lg transition-colors disabled:opacity-40 hover:bg-w-surface2/50"
                style={{ color: 'var(--color-w-dim)' }}
                title="Upload resumes"
              >
                <Paperclip size={18} />
              </button>
            </>
          )}
          <textarea
            ref={textareaRef}
            data-tour="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
            placeholder={project?.project_type === 'recruiting' && isPostingFinalized ? 'Type a message or upload resumes...' : 'Type a message...'}
            rows={1}
            disabled={streaming || (!vm.activeChatId && vm.pendingPlaceholders.current.length === 0)}
            className="flex-1 text-sm rounded-lg px-3 py-2.5 border focus:outline-none resize-none disabled:opacity-50 min-h-[44px]"
            style={{ background: 'var(--color-w-surface)', color: 'var(--color-w-text)', borderColor: 'var(--color-w-line)' }}
          />
          <button
            onClick={handleSend}
            disabled={streaming || !input.trim() || (!vm.activeChatId && vm.pendingPlaceholders.current.length === 0)}
            className="p-3 rounded-lg transition-colors disabled:opacity-40"
            style={{ background: 'var(--color-w-accent)', color: '#fff' }}
          >
            {streaming ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
          </button>
        </div>
      </div>
    </div>
  )
}
