import type { MWProject } from '../../types'
import { getProjectDetail, sendProjectInterviews, syncProjectInterviews, analyzeProjectCandidates, generatePlaceholderQuestions } from '../../api/matchaWork'
import ProjectPanel from '../../components/panels/ProjectPanel'
import RecruitingPipeline from '../../components/panels/RecruitingPipeline'
import CollaboratorsPill from '../../components/panels/CollaboratorsPill'
import PresenceLayer from '../../components/panels/PresenceLayer'
import type { ProjectViewModel } from './useProjectView'

interface Props {
  vm: ProjectViewModel
  project: MWProject
}

/** Right pane (`panel` tab): recruiting pipeline or project sections panel, wrapped in presence. */
export function WorkspacePanel({ vm, project }: Props) {
  const {
    activeTab,
    projectId,
    presence,
    currentUserId,
    activePageKey,
    cursorsActive,
    setProject,
    streaming,
    offerPdfUrl,
    setError,
    setMessages,
    makeLocalMsg,
    askNextPlaceholder,
    pendingPlaceholders,
    textareaRef,
  } = vm

  return (
    <div
      className={`${activeTab === 'panel' ? 'flex' : 'hidden'} flex-1 w-full min-w-0 min-h-0 flex-col`}
      data-tour="sections-panel"
    >
      {/* Collaborator presence pill (cross-tab awareness). Always rendered
          so the onboarding tour can target it; shows "Working solo" when
          no one else is in the project. */}
      <div
        data-tour="collaborators-pill"
        className="flex items-center justify-end px-3 py-1"
        style={{ borderBottom: '1px solid var(--color-w-line)', background: 'var(--color-w-bg)' }}
      >
        {presence.members.length > 1 ? (
          <CollaboratorsPill members={presence.members} selfId={currentUserId} />
        ) : (
          <span style={{ fontSize: 10, color: 'var(--color-w-line)' }}>Working solo</span>
        )}
      </div>
      <PresenceLayer
        members={presence.members}
        remoteCursors={presence.remoteCursors}
        reportCursor={presence.reportCursor}
        selfId={currentUserId}
        pageKey={activePageKey}
        enabled={cursorsActive}
      >
      {project.project_type === 'recruiting' ? (
        <RecruitingPipeline
          project={project}
          projectId={projectId!}
          onUpdate={(updated) => setProject(updated)}
          streaming={streaming}
          offerPdfUrl={offerPdfUrl}
          onSendInterviews={async (ids, positionTitle) => {
            try {
              const result = await sendProjectInterviews(projectId!, ids, positionTitle)
              if (result.sent.length > 0) {
                const updated = await getProjectDetail(projectId!)
                setProject(updated)
              }
              if (result.failed.length > 0) {
                setError(`Failed to send ${result.failed.length} interview(s): ${result.failed.map((f) => f.error).join(', ')}`)
              }
            } catch (e) {
              setError(e instanceof Error ? e.message : 'Failed to send interviews.')
            }
          }}
          onSyncInterviews={async () => {
            try {
              await syncProjectInterviews(projectId!)
              const updated = await getProjectDetail(projectId!)
              setProject(updated)
            } catch {
              setError('Failed to sync interview statuses.')
            }
          }}
          onAnalyzeCandidates={async () => {
            try {
              await analyzeProjectCandidates(projectId!)
              const updated = await getProjectDetail(projectId!)
              setProject(updated)
            } catch (e) {
              setError(e instanceof Error ? e.message : 'Failed to analyze candidates.')
            }
          }}
          onPromptChat={async (placeholders) => {
            setMessages((prev) => [...prev, makeLocalMsg('assistant', `Let me figure out what's missing...`)])
            try {
              const { questions } = await generatePlaceholderQuestions(placeholders)
              pendingPlaceholders.current = questions
            } catch {
              // Fallback to raw labels
              pendingPlaceholders.current = placeholders.map((p) => ({ ...p, question: `What's the ${p.placeholder}?` }))
            }
            setMessages((prev) => [...prev, makeLocalMsg('assistant', `Let's fill in the missing fields for the posting.`)])
            askNextPlaceholder()
            setTimeout(() => textareaRef.current?.focus(), 50)
          }}
        />
      ) : (
        <ProjectPanel
          projectId={projectId!}
          project={project}
          onProjectUpdate={(updated) => setProject(updated)}
          selfId={currentUserId}
          members={presence.members}
          remoteCarets={presence.remoteCarets}
          onCaretChange={presence.reportCaret}
        />
      )}
      </PresenceLayer>
    </div>
  )
}
