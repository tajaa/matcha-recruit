import { useState, useEffect } from 'react'
import { Button, Badge, Textarea } from '../ui'
import type { HandbookSection } from '../../types/handbook'

type Props = {
  section: HandbookSection
  onSave: (sectionId: string, content: string) => Promise<void>
  onMarkReviewed: (sectionId: string) => Promise<void>
  onDirtyChange: (sectionId: string, dirty: boolean) => void
}

export function HandbookSectionEditor({ section, onSave, onMarkReviewed, onDirtyChange }: Props) {
  const [content, setContent] = useState(section.content)
  const [saving, setSaving] = useState(false)
  const [reviewing, setReviewing] = useState(false)

  const isDirty = content !== section.content

  useEffect(() => {
    setContent(section.content)
  }, [section.id, section.content])

  useEffect(() => {
    onDirtyChange(section.id, isDirty)
  }, [isDirty, section.id, onDirtyChange])

  async function handleSave() {
    setSaving(true)
    try {
      await onSave(section.id, content)
    } finally {
      setSaving(false)
    }
  }

  async function handleMarkReviewed() {
    setReviewing(true)
    try {
      await onMarkReviewed(section.id)
    } finally {
      setReviewing(false)
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-zinc-100">{section.title}</h3>
          <div className="flex items-center gap-2 mt-1">
            <Badge variant="neutral">{section.section_type}</Badge>
            <span className="text-xs text-zinc-500">{section.section_key}</span>
            {section.last_reviewed_at && (
              <span className="text-xs text-zinc-600">
                Reviewed {new Date(section.last_reviewed_at).toLocaleDateString()}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button size="sm" variant="ghost" onClick={handleMarkReviewed} disabled={reviewing}>
            {reviewing ? 'Marking...' : 'Mark Reviewed'}
          </Button>
          {isDirty && (
            <Button size="sm" onClick={handleSave} disabled={saving}>
              {saving ? 'Saving...' : 'Save'}
            </Button>
          )}
        </div>
      </div>
      <Textarea
        id={`section-${section.id}`}
        label=""
        value={content}
        onChange={(e) => setContent(e.target.value)}
        rows={20}
        className="font-mono text-xs"
      />
    </div>
  )
}
