import { Button, Input, Textarea } from '../ui'
import type { HandbookSectionInput } from '../../types/handbook'

type Props = {
  sections: HandbookSectionInput[]
  onChange: (sections: HandbookSectionInput[]) => void
}

export function HandbookCustomSections({ sections, onChange }: Props) {
  function addSection() {
    onChange([
      ...sections,
      {
        section_key: `custom_${Date.now()}`,
        title: '',
        content: '',
        section_order: 500 + sections.length,
        section_type: 'custom',
      },
    ])
  }

  function updateSection(index: number, partial: Partial<HandbookSectionInput>) {
    const updated = sections.map((s, i) => (i === index ? { ...s, ...partial } : s))
    onChange(updated)
  }

  function removeSection(index: number) {
    onChange(sections.filter((_, i) => i !== index))
  }

  return (
    <div className="space-y-3">
      {sections.map((s, i) => (
        <div key={s.section_key} className="border border-zinc-800 rounded-lg p-3 space-y-2">
          <div className="flex items-center gap-2">
            <Input
              id={`custom-title-${i}`}
              label=""
              placeholder="Section title"
              value={s.title}
              onChange={(e) => updateSection(i, { title: e.target.value, section_key: e.target.value.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '') || s.section_key })}
              className="flex-1"
            />
            <Button size="sm" variant="ghost" onClick={() => removeSection(i)}>Remove</Button>
          </div>
          <Textarea
            id={`custom-content-${i}`}
            label=""
            placeholder="Section content (optional, will be AI-generated if blank)"
            value={s.content}
            onChange={(e) => updateSection(i, { content: e.target.value })}
            rows={4}
          />
        </div>
      ))}
      <Button size="sm" variant="secondary" onClick={addSection}>
        Add Custom Section
      </Button>
    </div>
  )
}
