import { useState } from 'react'

interface Props {
  isSupervisor: boolean
  onChange: (next: boolean) => Promise<void>
  disabled?: boolean
}

export default function SupervisorToggle({ isSupervisor, onChange, disabled }: Props) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function toggle() {
    if (saving || disabled) return
    setError(null)
    setSaving(true)
    try {
      await onChange(!isSupervisor)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <dt className="text-zinc-500 text-xs">Supervisor</dt>
      <dd className="mt-1 flex items-center gap-2">
        <button
          type="button"
          role="switch"
          aria-checked={isSupervisor}
          disabled={saving || disabled}
          onClick={toggle}
          className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full transition-colors disabled:opacity-50 ${
            isSupervisor ? 'bg-emerald-500' : 'bg-zinc-700'
          }`}
        >
          <span
            className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
              isSupervisor ? 'translate-x-4' : 'translate-x-0.5'
            } translate-y-0.5`}
          />
        </button>
        <span className="text-zinc-200 text-sm">{isSupervisor ? 'Yes' : 'No'}</span>
        {saving && <span className="text-zinc-500 text-xs">Saving…</span>}
      </dd>
      {error && <p className="text-xs text-red-400 mt-1">{error}</p>}
      <p className="text-[10px] text-zinc-600 mt-1 leading-snug">
        Determines who receives 2-hour CA SB 1343 supervisor training (vs 1-hour employee variant).
      </p>
    </div>
  )
}
