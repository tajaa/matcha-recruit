import { X } from 'lucide-react'
import PresentationPanel from '../../components/panels/PresentationPanel'
import ResumeBatchPanel from '../../components/panels/ResumeBatchPanel'
import InventoryPanel from '../../components/panels/InventoryPanel'
import ProjectPanel from '../../components/panels/ProjectPanel'
import LanguageTutorPanel from '../../components/panels/LanguageTutorPanel'
import AgentPanel from '../../components/panels/AgentPanel'
import { getThread, sendCandidateInterviews, syncInterviewStatuses } from '../../api/matchaWork'
import type { ThreadController } from './useThreadController'

interface RightPanelsProps {
  c: ThreadController
  showPresentationPanel: boolean
  showResumeBatchPanel: boolean
  showInventoryPanel: boolean
  showProjectPanel: boolean
  showLanguageTutorPanel: boolean
}

// Right panels — visible on desktop always, on mobile via toggle
export default function RightPanels({
  c, showPresentationPanel, showResumeBatchPanel, showInventoryPanel, showProjectPanel, showLanguageTutorPanel,
}: RightPanelsProps) {
  const {
    mobileView, thread, threadId, handleEditSlide, lightMode, streaming,
    setThread, setError, setMessages, agentMode, pdfUrl, setShowTutorSetup, setTutorDismissed,
  } = c

  return (
    <div className={`${mobileView === 'panel' ? 'flex w-full' : 'hidden'} md:contents`}>
      {showPresentationPanel && (
        <PresentationPanel
          state={thread!.current_state}
          threadId={threadId!}
          onEditSlide={handleEditSlide}
          lightMode={lightMode}
          streaming={streaming}
        />
      )}

      {showResumeBatchPanel && (
        <ResumeBatchPanel
          state={thread!.current_state}
          threadId={threadId!}
          lightMode={lightMode}
          streaming={streaming}
          onSendInterviews={async (ids, positionTitle) => {
            const result = await sendCandidateInterviews(threadId!, ids, positionTitle)
            if (result.sent.length > 0) {
              const refreshed = await getThread(threadId!)
              setThread(refreshed)
            }
            if (result.failed.length > 0) {
              setError(`Failed to send ${result.failed.length} interview(s): ${result.failed.map(f => f.error).join(', ')}`)
            }
          }}
          onSyncInterviews={async () => {
            const { updated } = await syncInterviewStatuses(threadId!)
            if (updated > 0) {
              const refreshed = await getThread(threadId!)
              setThread(refreshed)
            }
          }}
        />
      )}

      {showInventoryPanel && (
        <InventoryPanel
          state={thread!.current_state}
          threadId={threadId!}
          lightMode={lightMode}
          streaming={streaming}
        />
      )}

      {showProjectPanel && (
        <ProjectPanel
          state={thread!.current_state}
          threadId={threadId!}
          lightMode={lightMode}
          streaming={streaming}
          onStateUpdate={(newState, newVersion) => {
            setThread((prev) => prev ? { ...prev, current_state: newState, version: newVersion } : prev)
          }}
        />
      )}

      {showLanguageTutorPanel && (
        <div className="relative flex-1 min-w-0">
          <button
            onClick={() => { setShowTutorSetup(false); setTutorDismissed(true) }}
            className="absolute top-2 right-2 z-10 p-1 rounded hover:bg-zinc-700/50 text-zinc-500 hover:text-zinc-300"
            title="Close tutor"
          >
            <X size={16} />
          </button>
          <LanguageTutorPanel
            threadId={threadId!}
            lightMode={lightMode}
            currentState={thread?.current_state ?? null}
            onStateUpdate={() => {
              if (threadId) getThread(threadId).then(t => { setThread(t); setMessages(t.messages ?? []) }).catch(() => {})
            }}
          />
        </div>
      )}

      {agentMode && !showPresentationPanel && !showResumeBatchPanel && !showInventoryPanel && !showProjectPanel && !showLanguageTutorPanel && (
        <AgentPanel />
      )}

      {pdfUrl && !showPresentationPanel && !showResumeBatchPanel && !showInventoryPanel && !showProjectPanel && !showLanguageTutorPanel && !agentMode && (
        <div className={`${mobileView === 'panel' ? 'block w-full' : 'hidden md:block'} flex-1 bg-zinc-900`}>
          <iframe
            src={pdfUrl}
            className="w-full h-full border-0"
            title="Document preview"
          />
        </div>
      )}
    </div>
  )
}
