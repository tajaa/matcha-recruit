import { CheckCircle2, GripVertical, Plus, Trash2, FileText } from 'lucide-react'
import type { ProjectSection } from '../../../types'
import SectionEditor from '../SectionEditor'
import { sectionToHtml } from '../markdownToHtml'
import { c } from './constants'

interface Props {
  sections: ProjectSection[]
  isFinalized: boolean
  saving: boolean
  placeholderCount: number
  sectionTitleEditing: string | null
  setSectionTitleEditing: (id: string | null) => void
  sectionTitleDraft: string
  setSectionTitleDraft: (v: string) => void
  saveSectionTitle: (sectionId: string, newTitle: string) => Promise<void>
  handleDeleteSection: (sectionId: string) => Promise<void>
  handleSectionContentUpdate: (sectionId: string, html: string) => void
  handleAddBlankSection: () => Promise<void>
  finalizePosting: () => Promise<void>
}

export default function PostingTab({
  sections, isFinalized, saving, placeholderCount, sectionTitleEditing, setSectionTitleEditing,
  sectionTitleDraft, setSectionTitleDraft, saveSectionTitle, handleDeleteSection,
  handleSectionContentUpdate, handleAddBlankSection, finalizePosting,
}: Props) {
  return (
    <div>
      {isFinalized && (
        <div className="flex items-center gap-2 px-3 py-2 mx-3 mt-3 rounded" style={{ background: '#22c55e20', border: `1px solid ${c.green}40` }}>
          <CheckCircle2 size={14} style={{ color: c.green }} />
          <span className="text-xs font-medium" style={{ color: c.green }}>Posting Finalized</span>
          <span className="text-[10px] ml-auto" style={{ color: c.muted }}>Drop resumes in the chat to add candidates</span>
        </div>
      )}

      {sections.length === 0 && (
        <div className="text-center py-12" style={{ color: c.muted }}>
          <FileText size={24} className="mx-auto mb-2 opacity-40" />
          <p className="text-xs">No sections yet.</p>
          <p className="text-xs mt-1">Use the chat to describe the role, then click <strong style={{ color: c.accent }}>"Add to Project"</strong> on any message.</p>
        </div>
      )}

      {sections.map((s) => (
        <div key={s.id} style={{ borderBottom: `1px solid ${c.border}` }}>
          {/* Section header */}
          <div className="flex items-center gap-1.5 px-4 py-1.5" style={{ background: c.cardBg }}>
            <GripVertical size={12} className="shrink-0 cursor-grab" style={{ color: c.muted }} />
            {sectionTitleEditing === s.id ? (
              <input
                value={sectionTitleDraft}
                onChange={(e) => setSectionTitleDraft(e.target.value)}
                onBlur={() => saveSectionTitle(s.id, sectionTitleDraft)}
                onKeyDown={(e) => { if (e.key === 'Enter') saveSectionTitle(s.id, sectionTitleDraft) }}
                autoFocus
                className="flex-1 text-xs font-semibold rounded px-1.5 py-0.5 border focus:outline-none"
                style={{ background: c.bg, color: c.heading, borderColor: '#555' }}
              />
            ) : (
              <span
                onClick={() => { setSectionTitleEditing(s.id); setSectionTitleDraft(s.title || '') }}
                className="flex-1 text-xs font-semibold truncate cursor-pointer"
                style={{ color: s.title ? c.heading : c.muted }}
              >
                {s.title || 'Untitled section'}
              </span>
            )}
            <button
              onClick={() => handleDeleteSection(s.id)}
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
          />
        </div>
      ))}

      {/* Add section + finalize */}
      <div className="px-4 py-3 space-y-2">
        <button
          onClick={handleAddBlankSection}
          className="w-full py-2 border border-dashed text-xs font-medium transition-colors"
          style={{ borderColor: '#444', color: c.muted, borderRadius: '2px' }}
          onMouseEnter={(e) => { e.currentTarget.style.borderColor = c.accent; e.currentTarget.style.color = c.accent }}
          onMouseLeave={(e) => { e.currentTarget.style.borderColor = '#444'; e.currentTarget.style.color = c.muted }}
        >
          <Plus size={12} className="inline mr-1" />
          Add Section
        </button>
        {!isFinalized && sections.length > 0 && (
          <button
            onClick={finalizePosting}
            disabled={saving}
            className="w-full py-2 text-xs font-medium rounded transition-colors disabled:opacity-40"
            style={{ background: placeholderCount > 0 ? c.amber : c.green, color: '#fff' }}
          >
            {placeholderCount > 0
              ? `Fill ${placeholderCount} field${placeholderCount !== 1 ? 's' : ''} to finalize`
              : 'Finalize Posting'}
          </button>
        )}
      </div>
    </div>
  )
}
