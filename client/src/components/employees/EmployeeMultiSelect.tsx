import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { api } from '../../api/client'
import type { Employee } from '../../types/employee'

type Props = {
  label: string
  // Selected employee UUIDs.
  value: string[]
  onChange: (ids: string[]) => void
  placeholder?: string
  // UUID → display name for already-linked employees (e.g. fed from the
  // incident's hydrated involved_employees) so pills show names without an
  // extra fetch on mount.
  initialLabels?: Record<string, string>
}

function empName(e: Pick<Employee, 'first_name' | 'last_name' | 'email'>): string {
  const full = [e.first_name, e.last_name].filter(Boolean).join(' ').trim()
  return full || e.email || 'Unknown'
}

// Roster picker for linking real employees to an incident. Suggestions come
// from the company's employee roster (GET /employees?search=), so this is
// ONLY meaningful for tenants with the employees feature. Unlike
// IRPersonMultiSelect this does NOT accept free text — non-employees go in
// the separate free-text witnesses field.
export function EmployeeMultiSelect({ label, value, onChange, placeholder, initialLabels }: Props) {
  const [input, setInput] = useState('')
  const [suggestions, setSuggestions] = useState<Employee[]>([])
  const [open, setOpen] = useState(false)
  // id → display name, accumulated from initial labels + picked suggestions
  // so removable pills can render a name for any selected id.
  const [labels, setLabels] = useState<Record<string, string>>(initialLabels || {})
  const boxRef = useRef<HTMLDivElement>(null)

  // Keep labels in sync if the parent's initial set arrives/changes (detail
  // page hydrates involved_employees after the incident loads).
  useEffect(() => {
    if (!initialLabels) return
    setLabels((prev) => ({ ...initialLabels, ...prev }))
  }, [initialLabels])

  useEffect(() => {
    const q = input.trim()
    if (!q) {
      setSuggestions([])
      return
    }
    let cancelled = false
    const t = setTimeout(() => {
      api.get<Employee[]>(`/employees?search=${encodeURIComponent(q)}`)
        .then((rows) => { if (!cancelled) setSuggestions((rows || []).slice(0, 8)) })
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

  function addEmployee(emp: Employee) {
    if (!value.includes(emp.id)) {
      setLabels((prev) => ({ ...prev, [emp.id]: empName(emp) }))
      onChange([...value, emp.id])
    }
    setInput('')
    setSuggestions([])
    setOpen(false)
  }

  function removeEmployee(id: string) {
    onChange(value.filter((v) => v !== id))
  }

  // Hide already-selected employees from the suggestion list.
  const filtered = suggestions.filter((s) => !value.includes(s.id))

  return (
    <div ref={boxRef} className="relative">
      {label && <span className="text-xs text-zinc-400 uppercase tracking-wide">{label}</span>}
      <div className="mt-1 flex flex-wrap items-center gap-1.5 bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5 focus-within:border-zinc-600">
        {value.map((id) => (
          <span key={id} className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-200">
            {labels[id] || `${id.slice(0, 8)}…`}
            <button type="button" onClick={() => removeEmployee(id)} className="text-zinc-500 hover:text-zinc-200">
              <X className="w-3 h-3" />
            </button>
          </span>
        ))}
        <input
          className="flex-1 min-w-[140px] bg-transparent text-sm text-zinc-200 px-1 py-0.5 focus:outline-none"
          value={input}
          placeholder={value.length === 0 ? (placeholder || 'Search employees…') : ''}
          onChange={(e) => { setInput(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
        />
      </div>
      {open && filtered.length > 0 && (
        <div className="absolute z-10 mt-1 w-full bg-zinc-900 border border-zinc-700 rounded-lg shadow-lg overflow-hidden">
          {filtered.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => addEmployee(s)}
              className="w-full flex items-center justify-between px-3 py-1.5 text-left hover:bg-zinc-800"
            >
              <span className="text-sm text-zinc-200">{empName(s)}</span>
              {(s.job_title || s.department) && (
                <span className="text-[11px] text-zinc-500">
                  {[s.job_title, s.department].filter(Boolean).join(' · ')}
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
