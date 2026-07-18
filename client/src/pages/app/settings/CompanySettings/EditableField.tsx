import { useState } from 'react'
import { Input } from '../../../../components/ui'
import type { EditableFieldProps } from './types'

export function EditableField({ label, value, onSave, type = 'text' }: EditableFieldProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value ?? '')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')

  async function handleBlur() {
    const trimmed = draft.trim()
    if (trimmed === (value ?? '')) {
      setEditing(false)
      return
    }
    setSaving(true)
    setSaveError('')
    try {
      await onSave(trimmed)
      setEditing(false)
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  if (editing) {
    return (
      <div>
        <dt className="text-zinc-500 text-xs">{label}</dt>
        <dd className="mt-1">
          <Input
            label=""
            type={type}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={handleBlur}
            onKeyDown={(e) => { if (e.key === 'Enter') handleBlur() }}
            autoFocus
            disabled={saving}
            className="!py-1 text-sm"
          />
          {saveError && <p className="text-[10px] text-red-400 mt-0.5">{saveError}</p>}
        </dd>
      </div>
    )
  }

  return (
    <div
      className="cursor-pointer group rounded-md px-2 py-1.5 -mx-2 hover:bg-white/[0.04] transition-colors"
      onClick={() => { setDraft(value ?? ''); setEditing(true) }}
    >
      <dt className="text-zinc-500 text-xs">{label}</dt>
      <dd className="text-zinc-200 text-sm mt-0.5 flex items-center justify-between gap-2">
        <span>{value || <span className="text-zinc-600 italic">Not set</span>}</span>
        <svg className="w-3 h-3 text-zinc-600 opacity-0 group-hover:opacity-100 transition-opacity shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
        </svg>
      </dd>
    </div>
  )
}
