import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { buildThreadTheme } from './MatchaWorkThread/theme'
import { useThreadController } from './MatchaWorkThread/useThreadController'
import ThreadHeader from './MatchaWorkThread/ThreadHeader'
import JurisdictionBar from './MatchaWorkThread/JurisdictionBar'
import ChatMessages from './MatchaWorkThread/ChatMessages'
import ChatComposer from './MatchaWorkThread/ChatComposer'
import RightPanels from './MatchaWorkThread/RightPanels'
import HuumeActionCard from '../components/panels/HuumeActionCard'
import { getHuumeState, shouldShowHuumePanel, deriveHuumeArtifacts } from '../utils/huumeState'

export default function MatchaWorkThread() {
  const c = useThreadController()
  const {
    base, thread, threadId, streaming, loading, lightMode, error, pdfUrl, agentMode,
    showTutorSetup, tutorDismissed, mobileView, complianceMode, locations, locationsUnavailable,
  } = c

  const isPresentation = thread?.task_type === 'presentation'
  const showPresentationPanel = !!(isPresentation && thread?.current_state)
  const isResumeBatch = thread?.task_type === 'resume_batch'
  const showResumeBatchPanel = !!(isResumeBatch && thread?.current_state)
  const isInventory = thread?.task_type === 'inventory'
  const showInventoryPanel = !!(isInventory && thread?.current_state)
  const isProject = thread?.task_type === 'project'
  const showProjectPanel = !!(isProject && thread?.current_state)
  const isLanguageTutor = thread?.task_type === 'language_tutor'
  const showLanguageTutorPanel = !tutorDismissed && (isLanguageTutor || showTutorSetup)
  const huume = getHuumeState(thread?.current_state)   // banner below needs huume.action

  // The panel's × closes it without disabling Huume mode (turning the mode
  // off stays on the ThreadHeader pill) — so dismissal has to be "hide THIS
  // content" rather than a persisted flag, or new Huume output could never
  // reopen the panel. `dismissedToken` snapshots what was showing when the
  // user closed it; the panel reappears the moment that identity changes
  // (a new/re-shown record, a newly staged action, a different thread).
  const [dismissedToken, setDismissedToken] = useState<string | null>(null)
  // Toggling the header pill off→on doesn't change any artifact identity
  // (huume_mode is a plain boolean column, untouched by apply_update/version
  // bumps) — without this, re-enabling Huume mode with a `proposed` plan
  // still staged would leave the panel dismissed and its approve/execute
  // buttons unreachable.
  const prevHuumeModeRef = useRef(thread?.huume_mode)
  useEffect(() => {
    if (thread?.huume_mode && !prevHuumeModeRef.current) setDismissedToken(null)
    prevHuumeModeRef.current = thread?.huume_mode
  }, [thread?.huume_mode])
  const huumeToken = [
    threadId,
    thread?.version ?? '',
    ...deriveHuumeArtifacts(huume).map((a) => a.key),
    huume.records?.[huume.records.length - 1]?.opened_at ?? '',
  ].join('|')
  const showHuumePanel = shouldShowHuumePanel({
    huumeMode: !!thread?.huume_mode, state: thread?.current_state, pdfUrl, agentMode,
  }) && dismissedToken !== huumeToken
  const hasRightPanel = !!(pdfUrl || showPresentationPanel || showResumeBatchPanel || showInventoryPanel || showProjectPanel || showLanguageTutorPanel || showHuumePanel || agentMode)
  const isFinalized = thread?.status === 'finalized'
  const isArchived = thread?.status === 'archived'
  const inputDisabled = !!(streaming || isFinalized || isArchived)

  // Project threads always use the dark editor theme; others respect lightMode
  const lm = isProject ? false : lightMode
  const th = buildThreadTheme()

  if (loading) {
    return (
      <div className="flex justify-center items-center h-[calc(100vh-49px)]">
        <Loader2 className="animate-spin text-w-dim" size={24} />
      </div>
    )
  }

  if (error && !thread) {
    return (
      <div className="flex flex-col items-center justify-center h-[calc(100vh-49px)] gap-4">
        <p className="text-red-400">{error}</p>
        <Link to={base} className="text-sm text-w-dim hover:text-w-text">
          Back to threads
        </Link>
      </div>
    )
  }

  return (
    <div className="flex flex-col md:flex-row h-[calc(100vh-49px)]">
      {/* Chat panel */}
      <div className={`${mobileView === 'panel' && hasRightPanel ? 'hidden md:flex' : 'flex'} flex-col ${hasRightPanel ? 'w-full md:w-1/2' : 'w-full'} border-r ${th.border} ${th.panelBg} ${lm ? 'mw-light' : ''}`}>
        <ThreadHeader c={c} th={th} lm={lm} hasRightPanel={hasRightPanel} />

        <JurisdictionBar
          complianceMode={complianceMode}
          locationsUnavailable={locationsUnavailable}
          locations={locations}
          th={th}
        />

        <ChatMessages c={c} th={th} isProject={isProject} />

        {thread?.huume_mode && huume.action?.status === 'proposed' && (
          <HuumeActionCard
            action={huume.action}
            lightMode={lm}
            streaming={streaming}
            onSendChat={(t) => c.handleSend(t)}
          />
        )}

        <ChatComposer c={c} th={th} isFinalized={isFinalized} isArchived={isArchived} inputDisabled={inputDisabled} />
      </div>

      {/* Right panels */}
      {hasRightPanel && (
        <RightPanels
          c={c}
          showPresentationPanel={showPresentationPanel}
          showResumeBatchPanel={showResumeBatchPanel}
          showInventoryPanel={showInventoryPanel}
          showProjectPanel={showProjectPanel}
          showLanguageTutorPanel={showLanguageTutorPanel}
          showHuumePanel={showHuumePanel}
          onDismissHuumePanel={() => setDismissedToken(huumeToken)}
        />
      )}
    </div>
  )
}
