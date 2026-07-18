import { useState } from 'react'
import { X, FileText, ClipboardList, Activity, Presentation, Plus } from 'lucide-react'
import { PROJECT_TEMPLATES, type ProjectTemplate } from '../../data/projectTemplates'

interface Props {
  open: boolean
  onClose: () => void
  /** Called with the selected template id, or `null` for a blank project. */
  onPick: (templateId: string | null) => void
}

const ICONS: Record<string, React.ComponentType<{ size?: number }>> = {
  FileText,
  ClipboardList,
  Activity,
  Presentation,
}

/**
 * Modal shown after a user picks the General project type. Lets them pick a
 * pre-defined section skeleton (Proposal / Project Brief / Status Report /
 * Pitch Deck) or "Blank project" to keep current behavior.
 *
 * The picker stays out of the way for project types that already have their
 * own structured flow (recruiting wizard, presentation outline) — WorkSidebar
 * only opens this for `general`.
 */
export default function TemplatePickerModal({ open, onClose, onPick }: Props) {
  // Guard against double-clicks: while the parent's create+navigate is in
  // flight, ignore additional card clicks. Without this, fast-clicking
  // creates duplicate projects.
  const [picking, setPicking] = useState(false)

  if (!open) return null

  function pick(template: ProjectTemplate | null) {
    if (picking) return
    setPicking(true)
    onPick(template?.id ?? null)
    onClose()
  }

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.6)',
        zIndex: 100,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: '#1e1e1e',
          border: '1px solid #333',
          borderRadius: 8,
          padding: 20,
          width: 'min(720px, 90vw)',
          maxHeight: '85vh',
          overflowY: 'auto',
          color: '#d4d4d4',
        }}
      >
        <div className="flex items-center justify-between mb-4">
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, color: '#e8e8e8' }}>
              Start with a template
            </div>
            <div style={{ fontSize: 11, color: '#6a737d', marginTop: 2 }}>
              Templates pre-fill section structure with placeholders the AI can auto-fill.
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded transition-colors"
            style={{ color: '#6a737d' }}
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
            gap: 10,
          }}
        >
          {/* Blank option first so users who don't want a template see it immediately. */}
          <button
            onClick={() => pick(null)}
            style={cardStyle}
            onMouseEnter={(e) => { e.currentTarget.style.borderColor = '#ce9178' }}
            onMouseLeave={(e) => { e.currentTarget.style.borderColor = '#333' }}
          >
            <div style={iconWrapStyle}>
              <Plus size={18} />
            </div>
            <div style={titleStyle}>Blank project</div>
            <div style={descStyle}>Start with no sections — add them as you go.</div>
          </button>

          {PROJECT_TEMPLATES.map((t) => {
            const Icon = ICONS[t.icon] ?? FileText
            return (
              <button
                key={t.id}
                onClick={() => pick(t)}
                style={cardStyle}
                onMouseEnter={(e) => { e.currentTarget.style.borderColor = '#ce9178' }}
                onMouseLeave={(e) => { e.currentTarget.style.borderColor = '#333' }}
              >
                <div style={iconWrapStyle}>
                  <Icon size={18} />
                </div>
                <div style={titleStyle}>{t.label}</div>
                <div style={descStyle}>{t.description}</div>
                <div style={metaStyle}>
                  {t.sections.length} sections
                </div>
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}

const cardStyle: React.CSSProperties = {
  background: '#252526',
  border: '1px solid #333',
  borderRadius: 6,
  padding: 12,
  textAlign: 'left',
  cursor: 'pointer',
  transition: 'border-color 120ms',
  display: 'flex',
  flexDirection: 'column',
  gap: 6,
  color: '#d4d4d4',
}

const iconWrapStyle: React.CSSProperties = {
  width: 32,
  height: 32,
  background: '#2a2d2e',
  borderRadius: 4,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  color: '#ce9178',
}

const titleStyle: React.CSSProperties = {
  fontSize: 12,
  fontWeight: 600,
  color: '#e8e8e8',
}

const descStyle: React.CSSProperties = {
  fontSize: 10,
  color: '#9a9a9a',
  lineHeight: 1.4,
}

const metaStyle: React.CSSProperties = {
  fontSize: 9,
  color: '#6a737d',
  marginTop: 'auto',
}
