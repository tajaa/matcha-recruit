import { Link } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { buildThreadTheme } from './MatchaWorkThread/theme'
import { useThreadController } from './MatchaWorkThread/useThreadController'
import ThreadHeader from './MatchaWorkThread/ThreadHeader'
import JurisdictionBar from './MatchaWorkThread/JurisdictionBar'
import ChatMessages from './MatchaWorkThread/ChatMessages'
import ChatComposer from './MatchaWorkThread/ChatComposer'
import RightPanels from './MatchaWorkThread/RightPanels'

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
  const hasRightPanel = !!(pdfUrl || showPresentationPanel || showResumeBatchPanel || showInventoryPanel || showProjectPanel || showLanguageTutorPanel || agentMode)
  const isFinalized = thread?.status === 'finalized'
  const isArchived = thread?.status === 'archived'
  const inputDisabled = !!(streaming || isFinalized || isArchived)

  // Project threads always use the dark editor theme; others respect lightMode
  const lm = isProject ? false : lightMode
  const th = buildThreadTheme(isProject, lm)

  if (loading) {
    return (
      <div className="flex justify-center items-center h-[calc(100vh-49px)]">
        <Loader2 className="animate-spin text-zinc-500" size={24} />
      </div>
    )
  }

  if (error && !thread) {
    return (
      <div className="flex flex-col items-center justify-center h-[calc(100vh-49px)] gap-4">
        <p className="text-red-400">{error}</p>
        <Link to={base} className="text-sm text-zinc-400 hover:text-white">
          Back to threads
        </Link>
      </div>
    )
  }

  return (
    <div className="flex flex-col md:flex-row h-[calc(100vh-49px)]">
      {/* Chat panel */}
      <div className={`${mobileView === 'panel' && hasRightPanel ? 'hidden md:flex' : 'flex'} flex-col ${hasRightPanel ? 'w-full md:w-1/2' : 'w-full'} border-r ${th.border} ${th.panelBg}`}>
        <ThreadHeader c={c} th={th} lm={lm} hasRightPanel={hasRightPanel} />

        <JurisdictionBar
          complianceMode={complianceMode}
          locationsUnavailable={locationsUnavailable}
          locations={locations}
          th={th}
        />

        <ChatMessages c={c} th={th} isProject={isProject} />

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
        />
      )}
    </div>
  )
}
