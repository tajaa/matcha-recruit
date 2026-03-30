import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { GripVertical, Plus, Trash2, Download, ChevronDown, FileText, Loader2 } from 'lucide-react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ProjectSection } from '../../types/matcha-work'
import { updateProjectSection, deleteProjectSection, addProjectSection, exportProject, initProject } from '../../api/matchaWork'

interface ProjectPanelProps {
  state: Record<string, unknown>
  threadId: string
  lightMode: boolean
  streaming: boolean
  onStateUpdate: (state: Record<string, unknown>, version: number) => void
}

/** Render line numbers alongside content */
function LineNumbers({ content }: { content: string }) {
  const count = (content.match(/\n/g) || []).length + 1
  return (
    <div className="select-none text-right pr-3 pt-[1px]" style={{ color: '#6a737d', fontSize: '11px', lineHeight: '1.65' }}>
      {Array.from({ length: count }, (_, i) => (
        <div key={i}>{i + 1}</div>
      ))}
    </div>
  )
}

export default function ProjectPanel({ state, threadId, streaming, onStateUpdate }: ProjectPanelProps) {
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

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = textareaRef.current.scrollHeight + 'px'
    }
  }, [editContent])

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

  // Custom markdown components for the dark editor theme
  const mdComponents = useMemo(() => ({
    h1: ({ children, ...props }: React.ComponentProps<'h1'>) => <h1 style={{ color: '#e8e8e8', fontSize: '16px', fontWeight: 700, margin: '16px 0 8px', lineHeight: 1.4 }} {...props}>{children}</h1>,
    h2: ({ children, ...props }: React.ComponentProps<'h2'>) => <h2 style={{ color: '#e8e8e8', fontSize: '14px', fontWeight: 600, margin: '14px 0 6px', lineHeight: 1.4 }} {...props}>{children}</h2>,
    h3: ({ children, ...props }: React.ComponentProps<'h3'>) => <h3 style={{ color: '#e8e8e8', fontSize: '13px', fontWeight: 600, margin: '12px 0 4px', lineHeight: 1.4 }} {...props}>{children}</h3>,
    p: ({ children, ...props }: React.ComponentProps<'p'>) => <p style={{ color: '#d4d4d4', fontSize: '12px', lineHeight: 1.65, margin: '4px 0' }} {...props}>{children}</p>,
    strong: ({ children, ...props }: React.ComponentProps<'strong'>) => <strong style={{ color: '#dcdcaa', fontWeight: 600 }} {...props}>{children}</strong>,
    code: ({ children, ...props }: React.ComponentProps<'code'>) => <code style={{ color: '#ce9178', background: '#2a2d2e', padding: '1px 5px', borderRadius: '3px', fontSize: '11px', fontFamily: 'ui-monospace, monospace' }} {...props}>{children}</code>,
    pre: ({ children, ...props }: React.ComponentProps<'pre'>) => <pre style={{ background: '#1a1a1a', border: '1px solid #333', borderRadius: '4px', padding: '10px', overflow: 'auto', margin: '8px 0', fontSize: '11px' }} {...props}>{children}</pre>,
    li: ({ children, ...props }: React.ComponentProps<'li'>) => <li style={{ color: '#d4d4d4', fontSize: '12px', lineHeight: 1.65 }} {...props}>{children}</li>,
    a: ({ children, ...props }: React.ComponentProps<'a'>) => <a style={{ color: '#ce9178' }} {...props}>{children}</a>,
    hr: (props: React.ComponentProps<'hr'>) => <hr style={{ border: 'none', borderTop: '1px solid #333', margin: '12px 0' }} {...props} />,
    table: ({ children, ...props }: React.ComponentProps<'table'>) => <table style={{ borderCollapse: 'collapse', width: '100%', margin: '8px 0', fontSize: '11px' }} {...props}>{children}</table>,
    th: ({ children, ...props }: React.ComponentProps<'th'>) => <th style={{ border: '1px solid #333', padding: '4px 8px', color: '#dcdcaa', background: '#252526', textAlign: 'left', fontWeight: 600 }} {...props}>{children}</th>,
    td: ({ children, ...props }: React.ComponentProps<'td'>) => <td style={{ border: '1px solid #333', padding: '4px 8px', color: '#d4d4d4' }} {...props}>{children}</td>,
  }), [])

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

            {/* Section content */}
            <div className="flex">
              {/* Line numbers */}
              {editingSection !== s.id && s.content && (
                <LineNumbers content={s.content} />
              )}

              {/* Content area */}
              <div className="flex-1 px-4 py-2 min-w-0">
                {editingSection === s.id ? (
                  <textarea
                    ref={textareaRef}
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    onBlur={() => saveSection(s.id, editContent)}
                    className="w-full text-xs rounded border p-2 focus:outline-none resize-none min-h-[80px]"
                    style={{
                      background: '#1a1a1a',
                      color: '#d4d4d4',
                      borderColor: '#555',
                      fontFamily: 'ui-monospace, monospace',
                      lineHeight: 1.65,
                    }}
                    autoFocus
                  />
                ) : (
                  <div
                    onClick={() => startEditing(s)}
                    className="cursor-text min-h-[40px]"
                  >
                    {s.content ? (
                      <Markdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                        {s.content}
                      </Markdown>
                    ) : (
                      <p className="italic text-xs" style={{ color: '#6a737d' }}>Click to edit...</p>
                    )}
                  </div>
                )}
              </div>
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
