import { useState, useRef, useEffect, useCallback } from 'react'
import type { ProjectSection } from '../../../types'
import { updateProjectSection, deleteProjectSection, addProjectSection, exportProject, initProject, uploadProjectImage, updateProjectSectionNew, deleteProjectSectionNew, addProjectSectionNew, exportProjectNew, updateProjectMeta, listProjectFiles, uploadProjectFile, deleteProjectFile, reorderProjectSectionsNew, reorderProjectSections } from '../../../api/matchaWork'
import type { ProjectFile } from '../../../api/matchaWork'
import { ensureFreshToken } from '../../../../api/client'
import { ALLOWED_FILE_EXT } from './constants'
import { formatBytes } from './helpers'
import type { ProjectPanelProps } from './types'

export function useProjectPanel(props: ProjectPanelProps) {
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
  const [panelTab, setPanelTab] = useState<'sections' | 'research'>('sections')
  const [previewMode, setPreviewMode] = useState(false)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [loadingPreview, setLoadingPreview] = useState(false)
  const exportRef = useRef<HTMLDivElement>(null)
  const saveTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({})

  // Collapsible sections
  const [collapsedSections, setCollapsedSections] = useState<Set<string>>(new Set())
  function toggleCollapse(id: string) {
    setCollapsedSections(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  // Drag-and-drop reorder
  const [dragIdx, setDragIdx] = useState<number | null>(null)
  const [overIdx, setOverIdx] = useState<number | null>(null)

  async function handleReorder(fromIdx: number, toIdx: number) {
    if (fromIdx === toIdx) return
    const ids = sections.map(s => s.id)
    const [moved] = ids.splice(fromIdx, 1)
    ids.splice(toIdx, 0, moved)
    try {
      if (isNewMode) {
        const { getProjectDetail } = await import('../../../api/matchaWork')
        await reorderProjectSectionsNew(projectId, ids)
        props.onProjectUpdate?.(await getProjectDetail(projectId))
      } else {
        const result = await reorderProjectSections(threadId, ids)
        props.onStateUpdate?.(result.current_state, result.version)
      }
    } catch {}
  }

  // File attachments
  const [files, setFiles] = useState<ProjectFile[]>([])
  const [uploadingFiles, setUploadingFiles] = useState<string[]>([])
  const [isDragOver, setIsDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!isNewMode || !projectId) return
    listProjectFiles(projectId).then(setFiles).catch(() => {})
  }, [projectId, isNewMode])

  async function handleFileUploadList(fileList: File[]) {
    const valid = fileList.filter(f => ALLOWED_FILE_EXT.test(f.name) && f.size <= 10 * 1024 * 1024)
    if (valid.length === 0) return
    for (const file of valid) {
      setUploadingFiles(prev => [...prev, file.name])
      try {
        const uploaded = await uploadProjectFile(projectId, file)
        setFiles(prev => [uploaded, ...prev])
      } catch {}
      setUploadingFiles(prev => prev.filter(n => n !== file.name))
    }
  }

  async function handleDeleteFile(fileId: string) {
    try {
      await deleteProjectFile(projectId, fileId)
      setFiles(prev => prev.filter(f => f.id !== fileId))
    } catch {}
  }

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
          const { getProjectDetail } = await import('../../../api/matchaWork')
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
          const { getProjectDetail } = await import('../../../api/matchaWork')
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
          const { getProjectDetail } = await import('../../../api/matchaWork')
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
          const { getProjectDetail } = await import('../../../api/matchaWork')
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
          const { getProjectDetail } = await import('../../../api/matchaWork')
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
          const token = await ensureFreshToken()
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
          if (url) window.open(url, '_blank', 'noopener')
        }
      } else {
        if (fmt === 'md') {
          const BASE = import.meta.env.VITE_API_URL ?? '/api'
          const token = await ensureFreshToken()
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
          if (url) window.open(url, '_blank', 'noopener')
        }
      }
    } catch {}
    setExporting(false)
  }

  return {
    // props passthrough
    project: props.project,
    onProjectUpdate: props.onProjectUpdate,
    selfId: props.selfId,
    members: props.members,
    remoteCarets: props.remoteCarets,
    onCaretChange: props.onCaretChange,
    // derived
    isNewMode, title, sections, threadId, projectId, streaming,
    // title editing
    editingTitle, setEditingTitle, titleDraft, setTitleDraft, saveProjectTitle,
    // section title editing
    sectionTitleEditing, setSectionTitleEditing, sectionTitleDraft, setSectionTitleDraft, saveSectionTitle,
    // export / preview
    showExport, setShowExport, exporting, handleExport, exportRef,
    previewMode, previewUrl, loadingPreview, togglePreview,
    // status
    saving,
    // image upload
    uploadingImage, handleImageUpload,
    // diagram
    editingDiagram, setEditingDiagram,
    // tabs
    panelTab, setPanelTab,
    // collapse
    collapsedSections, toggleCollapse,
    // drag reorder
    dragIdx, setDragIdx, overIdx, setOverIdx, handleReorder,
    // files
    files, uploadingFiles, isDragOver, setIsDragOver, fileInputRef,
    handleFileUploadList, handleDeleteFile, formatBytes,
    // section mutations
    handleSectionContentUpdate, handleDelete, handleAddBlank,
  }
}

export type ProjectPanelController = ReturnType<typeof useProjectPanel>
