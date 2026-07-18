import { GripVertical, Plus, Trash2, ChevronDown, ChevronRight, FileText, Pencil, Paperclip } from 'lucide-react'
import SectionEditor from '../SectionEditor'
import { sectionToHtml } from '../markdownToHtml'
import type { ProjectPanelController } from './useProjectPanel'

export default function SectionsList({ ctl }: { ctl: ProjectPanelController }) {
  const {
    sections, streaming, isNewMode, files, fileInputRef,
    collapsedSections, toggleCollapse,
    dragIdx, setDragIdx, overIdx, setOverIdx, handleReorder,
    sectionTitleEditing, setSectionTitleEditing, sectionTitleDraft, setSectionTitleDraft, saveSectionTitle,
    handleDelete, handleSectionContentUpdate, handleImageUpload, uploadingImage,
    selfId, members, remoteCarets, onCaretChange,
    setEditingDiagram, handleAddBlank,
  } = ctl

  return (
    <div className="flex-1 overflow-y-auto py-2">
      {sections.length === 0 && !streaming && (
        <div className="text-center py-12" style={{ color: '#6a737d' }}>
          <FileText size={24} className="mx-auto mb-2 opacity-40" />
          <p className="text-xs">No sections yet.</p>
          <p className="text-xs mt-1">Add content from chat or create a blank section.</p>
          {isNewMode && files.length === 0 && (
            <button
              onClick={() => fileInputRef.current?.click()}
              className="mt-3 text-[10px] px-3 py-1.5 rounded transition-colors"
              style={{ color: '#ce9178', border: '1px dashed #ce917850' }}
            >
              <Paperclip size={10} className="inline mr-1" />
              Attach files
            </button>
          )}
        </div>
      )}

      {sections.map((s, idx) => {
        const isCollapsed = collapsedSections.has(s.id)
        return (
        <div
          key={s.id}
          style={{
            borderBottom: '1px solid #333',
            ...(overIdx === idx && dragIdx !== null && dragIdx !== idx
              ? { borderTop: '2px solid #ce9178' }
              : {}),
          }}
          onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); setOverIdx(idx) }}
          onDrop={(e) => {
            e.preventDefault(); e.stopPropagation()
            if (dragIdx !== null && dragIdx !== idx) handleReorder(dragIdx, idx)
            setDragIdx(null); setOverIdx(null)
          }}
        >
          {/* Section header */}
          <div
            className="flex items-center gap-1.5 px-4 py-1.5"
            style={{ background: dragIdx === idx ? '#333' : '#252526' }}
          >
            <div
              draggable
              onDragStart={(e) => { setDragIdx(idx); e.dataTransfer.effectAllowed = 'move' }}
              onDragEnd={() => { setDragIdx(null); setOverIdx(null) }}
              className="shrink-0 cursor-grab active:cursor-grabbing"
            >
              <GripVertical size={12} style={{ color: '#6a737d' }} />
            </div>
            <button
              onClick={() => toggleCollapse(s.id)}
              className="shrink-0 p-0.5 transition-colors"
              style={{ color: '#6a737d' }}
            >
              {isCollapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
            </button>
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

          {/* Rich text editor — hidden when collapsed */}
          {!isCollapsed && (
            <>
              <SectionEditor
                content={sectionToHtml(s)}
                onUpdate={(html) => handleSectionContentUpdate(s.id, html)}
                onImageUpload={handleImageUpload}
                uploadingImage={uploadingImage}
                sectionId={s.id}
                selfId={selfId}
                members={members}
                remoteCarets={remoteCarets}
                onCaretChange={onCaretChange}
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
            </>
          )}
        </div>
        )
      })}

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
  )
}
