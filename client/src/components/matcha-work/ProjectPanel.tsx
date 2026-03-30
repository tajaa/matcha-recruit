import { useState, useRef, useEffect, useCallback } from 'react'
import { GripVertical, Plus, Trash2, Download, ChevronDown, FileText, Loader2, ImagePlus } from 'lucide-react'
import type { ProjectSection } from '../../types/matcha-work'
import { updateProjectSection, deleteProjectSection, addProjectSection, exportProject, initProject, uploadProjectImage } from '../../api/matchaWork'

interface ProjectPanelProps {
  state: Record<string, unknown>
  threadId: string
  lightMode: boolean
  streaming: boolean
  onStateUpdate: (state: Record<string, unknown>, version: number) => void
}

/** Strip common markdown syntax so users see clean plain text. */
function stripMarkdown(text: string): string {
  return text
    // Bold: **text** or __text__
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/__(.+?)__/g, '$1')
    // Italic: *text* or _text_
    .replace(/(?<!\w)\*(.+?)\*(?!\w)/g, '$1')
    .replace(/(?<!\w)_(.+?)_(?!\w)/g, '$1')
    // Headings: ## text
    .replace(/^#{1,6}\s+/gm, '')
    // Inline code: `text`
    .replace(/`(.+?)`/g, '$1')
    // Links: [text](url) → text
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    // Images: ![alt](url) → (keep as-is for now)
    // Bullet markers: - text or * text → • text
    .replace(/^[\s]*[-*]\s+/gm, '• ')
    // Numbered list cleanup (keep numbers)
    // Horizontal rules
    .replace(/^---+$/gm, '')
    .replace(/^\*\*\*+$/gm, '')
    // Blockquotes: > text → text
    .replace(/^>\s*/gm, '')
    .trim()
}

export default function ProjectPanel({ state, threadId, streaming, onStateUpdate }: ProjectPanelProps) {
  const title = (state.project_title as string) ?? 'Untitled Project'
  const sections = (state.project_sections as ProjectSection[]) ?? []

  // Per-section local content — always editable, no read/edit toggle
  const [localContent, setLocalContent] = useState<Record<string, string>>({})
  const saveTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({})
  const [activeSection, setActiveSection] = useState<string | null>(null) // which section shows toolbar
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState(title)
  const [sectionTitleEditing, setSectionTitleEditing] = useState<string | null>(null)
  const [sectionTitleDraft, setSectionTitleDraft] = useState('')
  const [showExport, setShowExport] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [saving, setSaving] = useState(false)
  const textareaRefs = useRef<Record<string, HTMLTextAreaElement | null>>({})
  const exportRef = useRef<HTMLDivElement>(null)
  const imageInputRef = useRef<HTMLInputElement>(null)
  const [uploadingImage, setUploadingImage] = useState(false)

  // Sync local content when sections change from server (new section added, etc.)
  useEffect(() => {
    setLocalContent((prev) => {
      const next = { ...prev }
      for (const s of sections) {
        if (!(s.id in next)) next[s.id] = stripMarkdown(s.content)
      }
      return next
    })
  }, [sections])

  // Auto-resize all visible textareas
  useEffect(() => {
    for (const ta of Object.values(textareaRefs.current)) {
      if (ta) { ta.style.height = 'auto'; ta.style.height = ta.scrollHeight + 'px' }
    }
  }, [localContent])

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (exportRef.current && !exportRef.current.contains(e.target as Node)) setShowExport(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  function updateSectionContent(sectionId: string, content: string) {
    setLocalContent((prev) => ({ ...prev, [sectionId]: content }))
    // Debounce save — 1 second after last keystroke
    clearTimeout(saveTimers.current[sectionId])
    saveTimers.current[sectionId] = setTimeout(() => {
      flushSave(sectionId, content)
    }, 1000)
  }

  const flushSave = useCallback(async (sectionId: string, content: string) => {
    setSaving(true)
    try {
      const result = await updateProjectSection(threadId, sectionId, { content })
      onStateUpdate(result.current_state, result.version)
    } catch {}
    setSaving(false)
  }, [threadId, onStateUpdate])

  async function saveSectionTitle(sectionId: string, newTitle: string) {
    setSaving(true)
    try {
      const result = await updateProjectSection(threadId, sectionId, { title: newTitle })
      onStateUpdate(result.current_state, result.version)
    } catch {}
    setSaving(false)
    setSectionTitleEditing(null)
  }

  async function saveProjectTitle(newTitle: string) {
    try {
      const result = await initProject(threadId, newTitle)
      onStateUpdate(result.current_state, result.version)
    } catch {}
    setEditingTitle(false)
  }

  async function handleDelete(sectionId: string) {
    try {
      const result = await deleteProjectSection(threadId, sectionId)
      onStateUpdate(result.current_state, result.version)
    } catch {}
  }

  async function handleAddBlank() {
    try {
      const result = await addProjectSection(threadId, { content: '', title: 'New Section' })
      onStateUpdate(result.current_state, result.version)
      setActiveSection(result.section.id)
    } catch {}
  }

  async function handleImageUpload(file: File) {
    if (!file.type.startsWith('image/') || !activeSection) return
    setUploadingImage(true)
    try {
      const { url, filename } = await uploadProjectImage(threadId, file)
      const tag = `![${filename}](${url})`
      const ta = textareaRefs.current[activeSection]
      const current = localContent[activeSection] || ''
      if (ta) {
        const pos = ta.selectionStart
        updateSectionContent(activeSection, current.slice(0, pos) + tag + current.slice(pos))
      } else {
        updateSectionContent(activeSection, current + '\n' + tag)
      }
    } catch {}
    setUploadingImage(false)
  }

  async function handleExport(fmt: 'pdf' | 'md' | 'docx') {
    setExporting(true)
    setShowExport(false)
    try {
      if (fmt === 'md') {
        const BASE = import.meta.env.VITE_API_URL ?? '/api'
        const token = localStorage.getItem('matcha_access_token')
        const res = await fetch(`${BASE}/matcha-work/threads/${threadId}/project/export/md`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        })
        const blob = await res.blob()
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${title}.md`
        a.click()
        URL.revokeObjectURL(url)
      } else {
        const result = await exportProject(threadId, fmt)
        const url = result.pdf_url || result.docx_url
        if (url) window.open(url, '_blank')
      }
    } catch {}
    setExporting(false)
  }

  return (
    <div className="hidden md:flex md:w-1/2 flex-col" style={{ background: '#1e1e1e' }}>
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

      {/* Sections */}
      <div className="flex-1 overflow-y-auto py-2">
        {sections.length === 0 && !streaming && (
          <div className="text-center py-12" style={{ color: '#6a737d' }}>
            <FileText size={24} className="mx-auto mb-2 opacity-40" />
            <p className="text-xs">No sections yet.</p>
            <p className="text-xs mt-1">Add content from chat or create a blank section.</p>
          </div>
        )}

        {sections.map((s, sIdx) => (
          <div key={s.id} style={{ borderBottom: '1px solid #333' }}>
            {/* Section header */}
            <div className="flex items-center gap-1.5 px-4 py-1.5" style={{ background: '#252526' }}>
              <GripVertical size={12} className="shrink-0 cursor-grab" style={{ color: '#6a737d' }} />
              <span style={{ color: '#ce9178', fontSize: '12px', fontWeight: 600, fontFamily: 'ui-monospace, monospace' }}>
                ##
              </span>
              {sectionTitleEditing === s.id ? (
                <input
                  value={sectionTitleDraft}
                  onChange={(e) => setSectionTitleDraft(e.target.value)}
                  onBlur={() => saveSectionTitle(s.id, sectionTitleDraft)}
                  onKeyDown={(e) => { if (e.key === 'Enter') saveSectionTitle(s.id, sectionTitleDraft) }}
                  autoFocus
                  className="flex-1 text-xs font-semibold rounded px-1.5 py-0.5 border focus:outline-none"
                  style={{ background: '#1e1e1e', color: '#e8e8e8', borderColor: '#555', fontFamily: 'ui-monospace, monospace' }}
                />
              ) : (
                <span
                  onClick={() => { setSectionTitleEditing(s.id); setSectionTitleDraft(s.title || '') }}
                  className="flex-1 text-xs font-semibold truncate cursor-pointer"
                  style={{ color: s.title ? '#e8e8e8' : '#6a737d', fontFamily: 'ui-monospace, monospace' }}
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

            {/* Section content — always editable, plain text */}
            <div className="px-4 py-2">
              <input
                ref={imageInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0]
                  if (f) handleImageUpload(f)
                  e.target.value = ''
                }}
              />
              <textarea
                ref={(el) => { textareaRefs.current[s.id] = el }}
                value={localContent[s.id] ?? s.content}
                onChange={(e) => updateSectionContent(s.id, e.target.value)}
                onFocus={() => setActiveSection(s.id)}
                onPaste={(e) => {
                  const items = e.clipboardData.items
                  for (const item of items) {
                    if (item.type.startsWith('image/')) {
                      e.preventDefault()
                      const file = item.getAsFile()
                      if (file) handleImageUpload(file)
                      return
                    }
                  }
                }}
                placeholder="Start typing..."
                className="w-full text-xs rounded border p-2 focus:outline-none resize-none min-h-[60px]"
                style={{
                  background: '#1a1a1a',
                  color: '#d4d4d4',
                  borderColor: activeSection === s.id ? '#555' : '#333',
                  fontFamily: 'ui-monospace, monospace',
                  lineHeight: 1.65,
                }}
              />
            </div>
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
    </div>
  )
}
