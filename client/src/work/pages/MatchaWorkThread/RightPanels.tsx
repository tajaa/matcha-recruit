import { X } from 'lucide-react'
import PresentationPanel from '../../components/panels/PresentationPanel'
import ResumeBatchPanel from '../../components/panels/ResumeBatchPanel'
import InventoryPanel from '../../components/panels/InventoryPanel'
import ProjectPanel from '../../components/panels/ProjectPanel'
import LanguageTutorPanel from '../../components/panels/LanguageTutorPanel'
import AgentPanel from '../../components/panels/AgentPanel'
import HuumePanel from '../../components/panels/HuumePanel'
import { getThread, sendCandidateInterviews, syncInterviewStatuses } from '../../api/matchaWork'
import type { ThreadController } from './useThreadController'

interface RightPanelsProps {
  c: ThreadController
  showPresentationPanel: boolean
  showResumeBatchPanel: boolean
  showInventoryPanel: boolean
  showProjectPanel: boolean
  showLanguageTutorPanel: boolean
  showHuumePanel: boolean
  /** Hides the Huume panel without touching `huume_mode` — see the
   * dismissal-token comment in `MatchaWorkThread.tsx`. */
  onDismissHuumePanel: () => void
}

// Right panels — visible on desktop always, on mobile via toggle
export default function RightPanels({
  c, showPresentationPanel, showResumeBatchPanel, showInventoryPanel, showProjectPanel, showLanguageTutorPanel, showHuumePanel,
  onDismissHuumePanel,
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

      {showHuumePanel && (
        <HuumePanel
          state={thread!.current_state}
          threadId={threadId!}
          lightMode={lightMode}
          streaming={streaming}
          onDismiss={onDismissHuumePanel}
          onStateUpdate={(offerId, plan) => {
            setThread((prev) => prev ? {
              ...prev,
              current_state: {
                ...prev.current_state,
                huume_plans: { ...(prev.current_state.huume_plans as Record<string, unknown> | undefined), [offerId]: plan },
              },
            } : prev)
          }}
          onExecuted={() => {
            // The REST execute posts an assistant summary message
            // (metadata.huume_event = plan_executed) but does NOT broadcast
            // it — a full refetch is how it appears without a reload. Safe
            // to replace `messages` because execute is disabled while
            // streaming (see HuumePanel's streaming prop).
            if (threadId) getThread(threadId).then(t => { setThread(t); setMessages(t.messages ?? []) }).catch(() => {})
          }}
          onRecordClosed={(records) => {
            // The DELETE route already returns the updated working set —
            // merge it straight into current_state instead of refetching
            // the whole thread (messages included) for one JSONB key.
            setThread((prev) => prev ? {
              ...prev,
              current_state: { ...prev.current_state, huume_records: records },
            } : prev)
          }}
        />
      )}

      {agentMode && !showPresentationPanel && !showResumeBatchPanel && !showInventoryPanel && !showProjectPanel && !showLanguageTutorPanel && !showHuumePanel && (
        <AgentPanel />
      )}

      {pdfUrl && !showPresentationPanel && !showResumeBatchPanel && !showInventoryPanel && !showProjectPanel && !showLanguageTutorPanel && !showHuumePanel && !agentMode && (
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
