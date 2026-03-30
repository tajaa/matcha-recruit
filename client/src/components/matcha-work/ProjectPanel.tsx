import { useState, useRef, useEffect, useCallback } from 'react'
import { GripVertical, Plus, Trash2, Download, ChevronDown, FileText, Loader2 } from 'lucide-react'
import Markdown from 'react-markdown'
import type { ProjectSection } from '../../types/matcha-work'
import { updateProjectSection, deleteProjectSection, addProjectSection, exportProject, initProject } from '../../api/matchaWork'

interface ProjectPanelProps {
  state: Record<string, unknown>
  threadId: string
  lightMode: boolean
  streaming: boolean
  onStateUpdate: (state: Record<string, unknown>, version: number) => void
}

export default function ProjectPanel({ state, threadId, lightMode, streaming, onStateUpdate }: ProjectPanelProps) {
  const title = (state.project_title as string) ?? 'Untitled Project'
  const sections = (state.project_sections as ProjectSection[]) ?? []

  const [editingSection, setEditingSection] = useState<string | null>(null)
  const [editContent, setEditContent] = useState('')
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState(title)
  const [sectionTitleEditing, setSectionTitleEditing] = useState<string | null>(null)
  const [sectionTitleDraft, setSectionTitleDraft] = useState('')
  const [showExport, setShowExport] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [saving, setSaving] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const exportRef = useRef<HTMLDivElement>(null)

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = textareaRef.current.scrollHeight + 'px'
    }
  }, [editContent])

  // Close export dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (exportRef.current && !exportRef.current.contains(e.target as Node)) setShowExport(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  function startEditing(section: ProjectSection) {
    setEditingSection(section.id)
    setEditContent(section.content)
  }

  const saveSection = useCallback(async (sectionId: string, content: string) => {
    setSaving(true)
    try {
      const result = await updateProjectSection(threadId, sectionId, { content })
      onStateUpdate(result.current_state, result.version)
    } catch {}
    setSaving(false)
    setEditingSection(null)
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
      startEditing({ id: result.section.id, content: '', title: 'New Section', source_message_id: null })
    } catch {}
  }

  async function handleExport(fmt: 'pdf' | 'md' | 'docx') {
    setExporting(true)
    setShowExport(false)
    try {
      if (fmt === 'md') {
        // MD downloads directly as a blob
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

  const lm = lightMode
  const th = {
    bg: lm ? 'bg-white' : 'bg-zinc-950',
    border: lm ? 'border-zinc-200' : 'border-zinc-800',
    text: lm ? 'text-zinc-900' : 'text-zinc-100',
    sub: lm ? 'text-zinc-500' : 'text-zinc-400',
    muted: lm ? 'text-zinc-400' : 'text-zinc-500',
    card: lm ? 'bg-zinc-50 border-zinc-200' : 'bg-zinc-900 border-zinc-800',
    input: lm ? 'bg-zinc-100 text-zinc-900 border-zinc-300' : 'bg-zinc-900 text-white border-zinc-700',
    btn: lm ? 'text-zinc-400 hover:text-zinc-700' : 'text-zinc-500 hover:text-zinc-200',
    prose: lm ? 'prose prose-sm prose-zinc' : 'prose prose-sm prose-invert prose-zinc',
  }

  return (
    <div className={`hidden md:flex md:w-1/2 flex-col ${th.bg}`}>
      {/* Toolbar */}
      <div className={`px-4 py-3 border-b ${th.border} flex items-center justify-between`}>
        <div className="flex-1 min-w-0">
          {editingTitle ? (
            <input
              value={titleDraft}
              onChange={(e) => setTitleDraft(e.target.value)}
              onBlur={() => saveProjectTitle(titleDraft)}
              onKeyDown={(e) => { if (e.key === 'Enter') saveProjectTitle(titleDraft) }}
              autoFocus
              className={`text-sm font-semibold w-full rounded px-2 py-1 border focus:outline-none focus:border-emerald-600 ${th.input}`}
            />
          ) : (
            <h3
              onClick={() => { setTitleDraft(title); setEditingTitle(true) }}
              className={`text-sm font-semibold truncate cursor-pointer hover:opacity-70 ${th.text}`}
            >
              {title}
            </h3>
          )}
          <p className={`text-[10px] ${th.muted} mt-0.5`}>
            {sections.length} section{sections.length !== 1 ? 's' : ''}
            {saving && <Loader2 size={8} className="inline ml-1 animate-spin" />}
          </p>
        </div>

        <div className="relative" ref={exportRef}>
          <button
            onClick={() => setShowExport(!showExport)}
            disabled={sections.length === 0 || exporting}
            className={`flex items-center gap-1 text-[10px] font-medium px-2.5 py-1 rounded transition-colors ${th.btn} disabled:opacity-40`}
          >
            {exporting ? <Loader2 size={10} className="animate-spin" /> : <Download size={10} />}
            Export <ChevronDown size={8} />
          </button>
          {showExport && (
            <div className={`absolute right-0 mt-1 z-20 rounded-lg border shadow-lg py-1 min-w-[120px] ${lm ? 'bg-white border-zinc-200' : 'bg-zinc-900 border-zinc-700'}`}>
              {(['pdf', 'docx', 'md'] as const).map((fmt) => (
                <button
                  key={fmt}
                  onClick={() => handleExport(fmt)}
                  className={`w-full text-left text-xs px-3 py-1.5 ${lm ? 'hover:bg-zinc-100 text-zinc-700' : 'hover:bg-zinc-800 text-zinc-300'}`}
                >
                  {fmt === 'pdf' ? 'PDF' : fmt === 'docx' ? 'Word (DOCX)' : 'Markdown'}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Sections */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {sections.length === 0 && !streaming && (
          <div className={`text-center py-12 ${th.muted}`}>
            <FileText size={24} className="mx-auto mb-2 opacity-40" />
            <p className="text-xs">No sections yet.</p>
            <p className="text-xs mt-1">Add content from chat or create a blank section.</p>
          </div>
        )}

        {sections.map((s) => (
          <div key={s.id} className={`rounded-lg border ${th.card}`}>
            {/* Section header */}
            <div className={`flex items-center gap-1.5 px-3 py-1.5 border-b ${th.border}`}>
              <GripVertical size={12} className={`shrink-0 cursor-grab ${th.muted}`} />
              {sectionTitleEditing === s.id ? (
                <input
                  value={sectionTitleDraft}
                  onChange={(e) => setSectionTitleDraft(e.target.value)}
                  onBlur={() => saveSectionTitle(s.id, sectionTitleDraft)}
                  onKeyDown={(e) => { if (e.key === 'Enter') saveSectionTitle(s.id, sectionTitleDraft) }}
                  autoFocus
                  className={`flex-1 text-xs font-medium rounded px-1.5 py-0.5 border focus:outline-none focus:border-emerald-600 ${th.input}`}
                />
              ) : (
                <span
                  onClick={() => { setSectionTitleEditing(s.id); setSectionTitleDraft(s.title || '') }}
                  className={`flex-1 text-xs font-medium truncate cursor-pointer ${s.title ? th.text : th.muted}`}
                >
                  {s.title || 'Untitled section'}
                </span>
              )}
              <button
                onClick={() => handleDelete(s.id)}
                className={`shrink-0 p-0.5 rounded transition-colors ${lm ? 'text-zinc-300 hover:text-red-500' : 'text-zinc-600 hover:text-red-400'}`}
              >
                <Trash2 size={11} />
              </button>
            </div>

            {/* Section content */}
            <div className="px-3 py-2">
              {editingSection === s.id ? (
                <textarea
                  ref={textareaRef}
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  onBlur={() => saveSection(s.id, editContent)}
                  className={`w-full text-xs font-mono rounded border p-2 focus:outline-none focus:border-emerald-600 resize-none min-h-[80px] ${th.input}`}
                  autoFocus
                />
              ) : (
                <div
                  onClick={() => startEditing(s)}
                  className={`cursor-text min-h-[40px] text-xs ${s.content ? th.prose + ' max-w-none' : th.muted}`}
                >
                  {s.content ? (
                    <Markdown>{s.content}</Markdown>
                  ) : (
                    <p className="italic">Click to edit...</p>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}

        {/* Add section button */}
        <button
          onClick={handleAddBlank}
          className={`w-full py-2 rounded-lg border border-dashed text-xs font-medium transition-colors ${
            lm
              ? 'border-zinc-300 text-zinc-400 hover:border-emerald-500 hover:text-emerald-600'
              : 'border-zinc-700 text-zinc-500 hover:border-emerald-600 hover:text-emerald-400'
          }`}
        >
          <Plus size={12} className="inline mr-1" />
          Add Section
        </button>
      </div>
    </div>
  )
}
