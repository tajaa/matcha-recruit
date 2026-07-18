import { useState } from 'react'
import { Select } from '../../../../components/ui'
import type { EditableSelectProps } from './types'

export function EditableSelect({ label, value, options, onSave }: EditableSelectProps) {
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)

  async function handleChange(newValue: string) {
    if (newValue === (value ?? '')) {
      setEditing(false)
      return
    }
    setSaving(true)
    try {
      await onSave(newValue)
      setEditing(false)
    } finally {
      setSaving(false)
    }
  }

  const displayLabel = options.find((o) => o.value === value)?.label

  if (editing) {
    return (
      <div>
        <dt className="text-zinc-500 text-xs">{label}</dt>
        <dd className="mt-1">
          <Select
            label=""
            options={options}
            value={value ?? ''}
            onChange={(e) => handleChange(e.target.value)}
            onBlur={() => setEditing(false)}
            autoFocus
            disabled={saving}
          />
        </dd>
      </div>
    )
  }

  return (
    <div
      className="cursor-pointer group rounded-md px-2 py-1.5 -mx-2 hover:bg-white/[0.04] transition-colors"
      onClick={() => setEditing(true)}
    >
      <dt className="text-zinc-500 text-xs">{label}</dt>
      <dd className="text-zinc-200 text-sm mt-0.5 flex items-center justify-between gap-2">
        <span>{displayLabel || <span className="text-zinc-600 italic">Not set</span>}</span>
        <svg className="w-3 h-3 text-zinc-600 opacity-0 group-hover:opacity-100 transition-opacity shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
        </svg>
      </dd>
    </div>
  )
}
