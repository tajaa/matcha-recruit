import { Download, ChevronDown, Loader2, Eye, PenLine } from 'lucide-react'
import type { ProjectPanelController } from './useProjectPanel'

export default function ProjectToolbar({ ctl }: { ctl: ProjectPanelController }) {
  const {
    title, sections, saving,
    editingTitle, setEditingTitle, titleDraft, setTitleDraft, saveProjectTitle,
    togglePreview, previewMode, loadingPreview,
    showExport, setShowExport, exporting, handleExport, exportRef,
  } = ctl

  return (
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

        <div className="relative" ref={exportRef} data-tour="export-button">
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
  )
}
