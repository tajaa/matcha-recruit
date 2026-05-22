import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { api } from '../../api/client'
import type { IRPersonSummary } from '../../types/ir'

type Props = {
  label: string
  value: string[]
  onChange: (names: string[]) => void
  placeholder?: string
}

// Tag-style picker for naming people on an incident. Suggestions come from
// the company's existing IR people index — picking one reuses the exact
// spelling so the backend's name-based dedup actually catches repeats.
// Free text is always allowed (contractors, customers, anyone not seen yet).
export function IRPersonMultiSelect({ label, value, onChange, placeholder }: Props) {
  const [input, setInput] = useState('')
  const [suggestions, setSuggestions] = useState<IRPersonSummary[]>([])
  const [open, setOpen] = useState(false)
  const boxRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const q = input.trim()
    if (!q) {
      setSuggestions([])
      return
    }
    let cancelled = false
    const t = setTimeout(() => {
      api.get<IRPersonSummary[]>(`/ir/incidents/people/search?q=${encodeURIComponent(q)}&limit=8`)
        .then((rows) => { if (!cancelled) setSuggestions(rows || []) })
        .catch(() => { if (!cancelled) setSuggestions([]) })
    }, 200)
    return () => { cancelled = true; clearTimeout(t) }
  }, [input])

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  function addName(name: string) {
    const trimmed = name.trim()
    if (!trimmed) return
    // Case-insensitive dedup within the current selection.
    if (!value.some((v) => v.toLowerCase() === trimmed.toLowerCase())) {
      onChange([...value, trimmed])
    }
    setInput('')
    setSuggestions([])
    setOpen(false)
  }

  function removeName(name: string) {
    onChange(value.filter((v) => v !== name))
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      e.preventDefault()
      addName(input)
    } else if (e.key === 'Backspace' && !input && value.length) {
      removeName(value[value.length - 1])
    }
  }

  // Hide suggestions that exactly match an already-selected name.
  const filtered = suggestions.filter(
    (s) => !value.some((v) => v.toLowerCase() === s.display_name.toLowerCase()),
  )

  return (
    <div ref={boxRef} className="relative">
      {label && <span className="text-xs text-zinc-400 uppercase tracking-wide">{label}</span>}
      <div className="mt-1 flex flex-wrap items-center gap-1.5 bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5 focus-within:border-zinc-600">
        {value.map((name) => (
          <span key={name} className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-200">
            {name}
            <button type="button" onClick={() => removeName(name)} className="text-zinc-500 hover:text-zinc-200">
              <X className="w-3 h-3" />
            </button>
          </span>
        ))}
        <input
          className="flex-1 min-w-[120px] bg-transparent text-sm text-zinc-200 px-1 py-0.5 focus:outline-none"
          value={input}
          placeholder={value.length === 0 ? (placeholder || 'Type a name, Enter to add') : ''}
          onChange={(e) => { setInput(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
        />
      </div>
      {open && filtered.length > 0 && (
        <div className="absolute z-10 mt-1 w-full bg-zinc-900 border border-zinc-700 rounded-lg shadow-lg overflow-hidden">
          {filtered.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => addName(s.display_name)}
              className="w-full flex items-center justify-between px-3 py-1.5 text-left hover:bg-zinc-800"
            >
              <span className="text-sm text-zinc-200">{s.display_name}</span>
              <span className="text-[11px] text-zinc-500">
                {s.incident_count} {s.incident_count === 1 ? 'incident' : 'incidents'}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
