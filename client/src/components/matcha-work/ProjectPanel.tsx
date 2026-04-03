import { useState, useRef, useEffect, useCallback, lazy, Suspense } from 'react'
import { GripVertical, Plus, Trash2, Download, ChevronDown, FileText, Loader2, Eye, PenLine, Pencil } from 'lucide-react'
import type { ProjectSection, MWProject } from '../../types/matcha-work'
import { updateProjectSection, deleteProjectSection, addProjectSection, exportProject, initProject, uploadProjectImage, updateProjectSectionNew, deleteProjectSectionNew, addProjectSectionNew, exportProjectNew, updateProjectMeta } from '../../api/matchaWork'
import SectionEditor from './SectionEditor'
import { sectionToHtml } from './markdownToHtml'

const DiagramEditor = lazy(() => import('./DiagramEditor'))

interface ProjectPanelPropsLegacy {
  state: Record<string, unknown>
  threadId: string
  lightMode: boolean
  streaming: boolean
  onStateUpdate: (state: Record<string, unknown>, version: number) => void
  projectId?: undefined
  project?: undefined
  onProjectUpdate?: undefined
}

interface ProjectPanelPropsNew {
  projectId: string
  project: MWProject
  onProjectUpdate: (project: MWProject) => void
  state?: undefined
  threadId?: undefined
  lightMode?: boolean
  streaming?: boolean
  onStateUpdate?: undefined
}

type ProjectPanelProps = ProjectPanelPropsLegacy | ProjectPanelPropsNew

export default function ProjectPanel(props: ProjectPanelProps) {
  const isNewMode = !!props.projectId
  const title = isNewMode ? props.project!.title : ((props.state?.project_title as string) ?? 'Untitled Project')
  const sections = isNewMode ? (props.project!.sections ?? []) : ((props.state?.project_sections as ProjectSection[]) ?? [])
  const threadId = props.threadId ?? ''
  const projectId = props.projectId ?? ''
  const streaming = props.streaming ?? false

  const [editingTitle, setEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState(title)
  const [sectionTitleEditing, setSectionTitleEditing] = useState<string | null>(null)
  const [sectionTitleDraft, setSectionTitleDraft] = useState('')
  const [showExport, setShowExport] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [uploadingImage, setUploadingImage] = useState(false)
  const [editingDiagram, setEditingDiagram] = useState<{ sectionId: string; diagramData: NonNullable<ProjectSection['diagram_data']>; imageUrl: string } | null>(null)
  const [previewMode, setPreviewMode] = useState(false)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [loadingPreview, setLoadingPreview] = useState(false)
  const exportRef = useRef<HTMLDivElement>(null)
  const saveTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({})

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (exportRef.current && !exportRef.current.contains(e.target as Node)) setShowExport(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  function handleSectionContentUpdate(sectionId: string, html: string) {
    clearTimeout(saveTimers.current[sectionId])
    saveTimers.current[sectionId] = setTimeout(() => {
      flushSave(sectionId, html)
    }, 1000)
  }

  const flushSave = useCallback(async (sectionId: string, content: string) => {
    setSaving(true)
    try {
      if (isNewMode) {
        await updateProjectSectionNew(projectId, sectionId, { content })
        if (props.onProjectUpdate) {
          const { getProjectDetail } = await import('../../api/matchaWork')
          const updated = await getProjectDetail(projectId)
          props.onProjectUpdate(updated)
        }
      } else {
        const result = await updateProjectSection(threadId, sectionId, { content })
        props.onStateUpdate?.(result.current_state, result.version)
      }
    } catch {}
    setSaving(false)
  }, [threadId, projectId, isNewMode, props])

  async function saveSectionTitle(sectionId: string, newTitle: string) {
    setSaving(true)
    try {
      if (isNewMode) {
        await updateProjectSectionNew(projectId, sectionId, { title: newTitle })
        if (props.onProjectUpdate) {
          const { getProjectDetail } = await import('../../api/matchaWork')
          props.onProjectUpdate(await getProjectDetail(projectId))
        }
      } else {
        const result = await updateProjectSection(threadId, sectionId, { title: newTitle })
        props.onStateUpdate?.(result.current_state, result.version)
      }
    } catch {}
    setSaving(false)
    setSectionTitleEditing(null)
  }

  async function saveProjectTitle(newTitle: string) {
    try {
      if (isNewMode) {
        await updateProjectMeta(projectId, { title: newTitle })
        if (props.onProjectUpdate) {
          const { getProjectDetail } = await import('../../api/matchaWork')
          props.onProjectUpdate(await getProjectDetail(projectId))
        }
      } else {
        const result = await initProject(threadId, newTitle)
        props.onStateUpdate?.(result.current_state, result.version)
      }
    } catch {}
    setEditingTitle(false)
  }

  async function handleDelete(sectionId: string) {
    try {
      if (isNewMode) {
        await deleteProjectSectionNew(projectId, sectionId)
        if (props.onProjectUpdate) {
          const { getProjectDetail } = await import('../../api/matchaWork')
          props.onProjectUpdate(await getProjectDetail(projectId))
        }
      } else {
        const result = await deleteProjectSection(threadId, sectionId)
        props.onStateUpdate?.(result.current_state, result.version)
      }
    } catch {}
  }

  async function handleAddBlank() {
    try {
      if (isNewMode) {
        await addProjectSectionNew(projectId, { content: '', title: 'New Section' })
        if (props.onProjectUpdate) {
          const { getProjectDetail } = await import('../../api/matchaWork')
          props.onProjectUpdate(await getProjectDetail(projectId))
        }
      } else {
        await addProjectSection(threadId, { content: '', title: 'New Section' })
        // Legacy mode refresh handled by caller
      }
    } catch {}
  }

  async function handleImageUpload(file: File): Promise<string | null> {
    setUploadingImage(true)
    try {
      const { url } = await uploadProjectImage(threadId, file)
      return url
    } catch {
      return null
    } finally {
      setUploadingImage(false)
    }
  }

  async function togglePreview() {
    if (previewMode) {
      setPreviewMode(false)
      setPreviewUrl(null)
      return
    }
    setLoadingPreview(true)
    setPreviewMode(true)
    try {
      const result = isNewMode
        ? await exportProjectNew(projectId, 'pdf')
        : await exportProject(threadId, 'pdf')
      if (result.pdf_url) setPreviewUrl(result.pdf_url)
    } catch {}
    setLoadingPreview(false)
  }

  async function handleExport(fmt: 'pdf' | 'md' | 'docx') {
    setExporting(true)
    setShowExport(false)
    try {
      if (isNewMode) {
        if (fmt === 'md') {
          const BASE = import.meta.env.VITE_API_URL ?? '/api'
          const token = localStorage.getItem('matcha_access_token')
          const res = await fetch(`${BASE}/matcha-work/projects/${projectId}/export/md`, {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
          })
          const blob = await res.blob()
          const url = URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = url; a.download = `${title}.md`; a.click()
          URL.revokeObjectURL(url)
        } else {
          const result = await exportProjectNew(projectId, fmt)
          const url = result.pdf_url || result.docx_url
          if (url) window.open(url, '_blank')
        }
      } else {
        if (fmt === 'md') {
          const BASE = import.meta.env.VITE_API_URL ?? '/api'
          const token = localStorage.getItem('matcha_access_token')
          const res = await fetch(`${BASE}/matcha-work/threads/${threadId}/project/export/md`, {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
          })
          const blob = await res.blob()
          const url = URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = url; a.download = `${title}.md`; a.click()
          URL.revokeObjectURL(url)
        } else {
          const result = await exportProject(threadId, fmt)
          const url = result.pdf_url || result.docx_url
          if (url) window.open(url, '_blank')
        }
      }
    } catch {}
    setExporting(false)
  }

  return (
    <div className="flex w-full flex-col" style={{ background: '#1e1e1e' }}>
      {/* Toolbar */}
      <div className="px-4 py-3 flex items-center justify-between" style={{ borderBottom: '1px solid #333' }}>
        <div className="flex-1 min-w-0">
          {editingTitle ? (
            <input
              value={titleDraft}
              onChange={(e) => setTitleDraft(e.target.value)}
              onBlur={() => saveProjectTitle(titleDraft)}
              onKeyDown={(e) => { if (e.key === 'Enter') saveProjectTitle(titleDraft) }}
              autoFocus
              className="text-sm font-semibold w-full rounded px-2 py-1 border focus:outline-none"
              style={{ background: '#252526', color: '#e8e8e8', borderColor: '#555' }}
            />
          ) : (
            <h3
              onClick={() => { setTitleDraft(title); setEditingTitle(true) }}
              className="text-sm font-semibold truncate cursor-pointer hover:opacity-70"
              style={{ color: '#e8e8e8' }}
            >
              {title}
            </h3>
          )}
          <p className="text-[10px] mt-0.5" style={{ color: '#6a737d' }}>
            {sections.length} section{sections.length !== 1 ? 's' : ''}
            {saving && <Loader2 size={8} className="inline ml-1 animate-spin" />}
          </p>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            onClick={togglePreview}
            disabled={sections.length === 0 || loadingPreview}
            className="flex items-center gap-1 text-[10px] font-medium px-2.5 py-1 rounded transition-colors disabled:opacity-40"
            style={{ color: previewMode ? '#e8e8e8' : '#6a737d', background: previewMode ? '#2a2d2e' : 'transparent' }}
          >
            {loadingPreview ? <Loader2 size={10} className="animate-spin" /> : previewMode ? <PenLine size={10} /> : <Eye size={10} />}
            {previewMode ? 'Edit' : 'Preview'}
          </button>

          <div className="relative" ref={exportRef}>
          <button
            onClick={() => setShowExport(!showExport)}
            disabled={sections.length === 0 || exporting}
            className="flex items-center gap-1 text-[10px] font-medium px-2.5 py-1 rounded transition-colors disabled:opacity-40"
            style={{ color: '#ce9178' }}
          >
            {exporting ? <Loader2 size={10} className="animate-spin" /> : <Download size={10} />}
            Export <ChevronDown size={8} />
          </button>
          {showExport && (
            <div className="absolute right-0 mt-1 z-20 rounded border shadow-lg py-1 min-w-[120px]" style={{ background: '#252526', borderColor: '#444' }}>
              {(['pdf', 'docx', 'md'] as const).map((fmt) => (
                <button
                  key={fmt}
                  onClick={() => handleExport(fmt)}
                  className="w-full text-left text-xs px-3 py-1.5 hover:opacity-80"
                  style={{ color: '#d4d4d4' }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = '#2a2d2e')}
                  onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                >
                  {fmt === 'pdf' ? 'PDF' : fmt === 'docx' ? 'Word (DOCX)' : 'Markdown'}
                </button>
              ))}
            </div>
          )}
          </div>
        </div>
      </div>

      {/* Preview mode — show PDF iframe */}
      {previewMode && (
        <div className="flex-1 overflow-hidden" style={{ background: '#252526' }}>
          {loadingPreview ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 size={20} className="animate-spin" style={{ color: '#6a737d' }} />
            </div>
          ) : previewUrl ? (
            <iframe src={previewUrl} className="w-full h-full border-0" title="PDF Preview" />
          ) : (
            <div className="flex items-center justify-center h-full">
              <p className="text-xs" style={{ color: '#6a737d' }}>Could not generate preview</p>
            </div>
          )}
        </div>
      )}

      {/* Sections — hidden when preview is active */}
      {!previewMode && (
      <div className="flex-1 overflow-y-auto py-2">
        {sections.length === 0 && !streaming && (
          <div className="text-center py-12" style={{ color: '#6a737d' }}>
            <FileText size={24} className="mx-auto mb-2 opacity-40" />
            <p className="text-xs">No sections yet.</p>
            <p className="text-xs mt-1">Add content from chat or create a blank section.</p>
          </div>
        )}

        {sections.map((s) => (
          <div key={s.id} style={{ borderBottom: '1px solid #333' }}>
            {/* Section header */}
            <div className="flex items-center gap-1.5 px-4 py-1.5" style={{ background: '#252526' }}>
              <GripVertical size={12} className="shrink-0 cursor-grab" style={{ color: '#6a737d' }} />
              {sectionTitleEditing === s.id ? (
                <input
                  value={sectionTitleDraft}
                  onChange={(e) => setSectionTitleDraft(e.target.value)}
                  onBlur={() => saveSectionTitle(s.id, sectionTitleDraft)}
                  onKeyDown={(e) => { if (e.key === 'Enter') saveSectionTitle(s.id, sectionTitleDraft) }}
                  autoFocus
                  className="flex-1 text-xs font-semibold rounded px-1.5 py-0.5 border focus:outline-none"
                  style={{ background: '#1e1e1e', color: '#e8e8e8', borderColor: '#555' }}
                />
              ) : (
                <span
                  onClick={() => { setSectionTitleEditing(s.id); setSectionTitleDraft(s.title || '') }}
                  className="flex-1 text-xs font-semibold truncate cursor-pointer"
                  style={{ color: s.title ? '#e8e8e8' : '#6a737d' }}
                >
                  {s.title || 'Untitled section'}
                </span>
              )}
              <button
                onClick={() => handleDelete(s.id)}
                className="shrink-0 p-0.5 rounded transition-opacity opacity-30 hover:opacity-100"
                style={{ color: '#f87171' }}
              >
                <Trash2 size={11} />
              </button>
            </div>

            {/* Rich text editor */}
            <SectionEditor
              content={sectionToHtml(s)}
              onUpdate={(html) => handleSectionContentUpdate(s.id, html)}
              onImageUpload={handleImageUpload}
              uploadingImage={uploadingImage}
            />

            {/* Edit Diagram button for sections with diagram data */}
            {s.diagram_data && s.diagram_data.length > 0 && (
              <button
                onClick={() => setEditingDiagram({
                  sectionId: s.id,
                  diagramData: s.diagram_data!,
                  imageUrl: s.diagram_data![0].storage_url,
                })}
                className="flex items-center gap-1.5 mx-3 mb-2 px-2.5 py-1.5 text-[10px] font-medium rounded transition-colors"
                style={{ color: '#ce9178', background: '#2a2d2e' }}
              >
                <Pencil size={10} />
                Edit Diagram
              </button>
            )}
          </div>
        ))}

        {/* Add section button */}
        <div className="px-4 py-3">
          <button
            onClick={handleAddBlank}
            className="w-full py-2 border border-dashed text-xs font-medium transition-colors"
            style={{ borderColor: '#444', color: '#6a737d', borderRadius: '2px' }}
            onMouseEnter={(e) => { e.currentTarget.style.borderColor = '#ce9178'; e.currentTarget.style.color = '#ce9178' }}
            onMouseLeave={(e) => { e.currentTarget.style.borderColor = '#444'; e.currentTarget.style.color = '#6a737d' }}
          >
            <Plus size={12} className="inline mr-1" />
            Add Section
          </button>
        </div>
      </div>
      )}
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
              if (props.onProjectUpdate) props.onProjectUpdate(updated)
              setEditingDiagram(null)
            }}
          />
        </Suspense>
      )}
    </div>
  )
}
