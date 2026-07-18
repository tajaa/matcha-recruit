import { lazy, Suspense } from 'react'
import { Upload } from 'lucide-react'
import ResearchPanel from './ResearchPanel'
import { useProjectPanel } from './ProjectPanel/useProjectPanel'
import type { ProjectPanelProps } from './ProjectPanel/types'
import ProjectToolbar from './ProjectPanel/ProjectToolbar'
import PanelTabs from './ProjectPanel/PanelTabs'
import AttachmentsPanel from './ProjectPanel/AttachmentsPanel'
import PreviewPane from './ProjectPanel/PreviewPane'
import SectionsList from './ProjectPanel/SectionsList'

const DiagramEditor = lazy(() => import('./DiagramEditor'))

export default function ProjectPanel(props: ProjectPanelProps) {
  const ctl = useProjectPanel(props)
  const {
    isNewMode, projectId, project, onProjectUpdate,
    panelTab, files, uploadingFiles, previewMode,
    isDragOver, setIsDragOver, fileInputRef, handleFileUploadList,
    editingDiagram, setEditingDiagram,
  } = ctl

  return (
    <div
      className="flex w-full flex-col relative"
      style={{ background: '#1e1e1e' }}
      onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); if (isNewMode) setIsDragOver(true) }}
      onDragLeave={(e) => { if (e.currentTarget.contains(e.relatedTarget as Node)) return; setIsDragOver(false) }}
      onDrop={(e) => {
        e.preventDefault(); e.stopPropagation(); setIsDragOver(false)
        if (!isNewMode) return
        const droppedFiles = Array.from(e.dataTransfer.files)
        if (droppedFiles.length > 0) handleFileUploadList(droppedFiles)
      }}
    >
      {/* Drag overlay */}
      {isDragOver && (
        <div className="absolute inset-0 z-10 border-2 border-dashed rounded-lg flex items-center justify-center pointer-events-none"
          style={{ background: 'rgba(206, 145, 120, 0.06)', borderColor: '#ce9178' }}>
          <div className="text-center">
            <Upload size={20} className="mx-auto mb-1" style={{ color: '#ce9178' }} />
            <p className="text-sm font-medium" style={{ color: '#ce9178' }}>Drop files to attach</p>
          </div>
        </div>
      )}

      {/* Toolbar */}
      <ProjectToolbar ctl={ctl} />

      {/* Panel tabs — show when in new project mode */}
      {isNewMode && <PanelTabs ctl={ctl} />}

      {/* Research panel */}
      {isNewMode && panelTab === 'research' && (
        <ResearchPanel
          project={project!}
          projectId={projectId}
          onUpdate={(updated) => onProjectUpdate?.(updated)}
        />
      )}

      {/* Sections tab content (hidden when research tab is active) */}
      {(!isNewMode || panelTab === 'sections') && <>

      {/* Attachments */}
      {isNewMode && (files.length > 0 || uploadingFiles.length > 0) && (
        <AttachmentsPanel ctl={ctl} />
      )}

      {/* Preview mode — show PDF iframe */}
      {previewMode && <PreviewPane ctl={ctl} />}

      {/* Sections — hidden when preview is active */}
      {!previewMode && <SectionsList ctl={ctl} />}
      {/* Hidden file input — always mounted so ref is stable */}
      {isNewMode && (
        <input ref={fileInputRef} type="file" multiple hidden onChange={(e) => { handleFileUploadList(Array.from(e.target.files ?? [])); e.target.value = '' }} />
      )}

      </>}
      {/* End sections tab content */}

      {/* Diagram Editor Modal */}
      {editingDiagram && (
        <Suspense fallback={null}>
          <DiagramEditor
            projectId={projectId}
            sectionId={editingDiagram.sectionId}
            diagramData={editingDiagram.diagramData}
            imageUrl={editingDiagram.imageUrl}
            onClose={() => setEditingDiagram(null)}
            onUpdated={(updated) => {
              if (onProjectUpdate) onProjectUpdate(updated)
              setEditingDiagram(null)
            }}
          />
        </Suspense>
      )}
    </div>
  )
}
