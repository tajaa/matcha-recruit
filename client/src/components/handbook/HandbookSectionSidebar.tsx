import { useState } from 'react'
import { Input } from '../ui'
import type { HandbookSection, HandbookSectionType } from '../../types/handbook'

const GROUPS: { type: HandbookSectionType; label: string }[] = [
  { type: 'core', label: 'Core Policies' },
  { type: 'state', label: 'State Addenda' },
  { type: 'custom', label: 'Company Custom' },
  { type: 'uploaded', label: 'Uploaded' },
]

type Props = {
  sections: HandbookSection[]
  activeId: string | null
  dirtyIds: Set<string>
  onSelect: (section: HandbookSection) => void
}

export function HandbookSectionSidebar({ sections, activeId, dirtyIds, onSelect }: Props) {
  const [search, setSearch] = useState('')
  const [collapsed, setCollapsed] = useState<Set<HandbookSectionType>>(new Set())

  const filtered = sections.filter(
    (s) =>
      s.title.toLowerCase().includes(search.toLowerCase()) ||
      s.section_key.toLowerCase().includes(search.toLowerCase()),
  )

  function toggleGroup(type: HandbookSectionType) {
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(type)) next.delete(type)
      else next.add(type)
      return next
    })
  }

  return (
    <div className="space-y-2">
      <Input
        id="section-search"
        label=""
        placeholder="Search sections..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      {GROUPS.map(({ type, label }) => {
        const items = filtered
          .filter((s) => s.section_type === type)
          .sort((a, b) => a.section_order - b.section_order)
        if (items.length === 0) return null
        const isCollapsed = collapsed.has(type)
        return (
          <div key={type}>
            <button
              type="button"
              onClick={() => toggleGroup(type)}
              className="flex items-center gap-1.5 w-full text-left px-2 py-1.5 text-xs font-semibold text-zinc-400 uppercase tracking-wider hover:text-zinc-200 transition-colors"
            >
              <span className={`transition-transform ${isCollapsed ? '' : 'rotate-90'}`}>&#9654;</span>
              {label}
              <span className="ml-auto text-zinc-600 font-normal normal-case">{items.length}</span>
            </button>
            {!isCollapsed && (
              <div className="space-y-px">
                {items.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => onSelect(s)}
                    className={`w-full text-left px-3 py-1.5 text-sm rounded transition-colors flex items-center gap-2 ${
                      activeId === s.id
                        ? 'bg-zinc-800 text-zinc-100'
                        : 'text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200'
                    }`}
                  >
                    <span className="truncate flex-1">{s.title}</span>
                    {dirtyIds.has(s.id) && (
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0" />
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
