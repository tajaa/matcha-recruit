import { useEffect, useRef } from 'react'
import { Loader2 } from 'lucide-react'

interface AddCardInputProps {
  value: string
  onChange: (v: string) => void
  onSubmit: () => void
  onCancel: () => void
  busy: boolean
}

export default function AddCardInput({ value, onChange, onSubmit, onCancel, busy }: AddCardInputProps) {
  const ref = useRef<HTMLTextAreaElement>(null)
  useEffect(() => {
    ref.current?.focus()
  }, [])
  return (
    <div className="rounded-lg border border-w-line bg-w-surface p-2">
      <textarea
        ref={ref}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            onSubmit()
          } else if (e.key === 'Escape') {
            onCancel()
          }
        }}
        rows={2}
        placeholder="Card title…"
        className="w-full resize-none bg-transparent text-sm text-w-text placeholder-w-faint outline-none"
      />
      <div className="mt-2 flex items-center gap-2">
        <button
          onClick={onSubmit}
          disabled={busy || !value.trim()}
          className="flex items-center gap-1 rounded bg-w-accent px-2.5 py-1 text-xs font-medium text-white transition-colors hover:bg-w-accent-hi disabled:opacity-50"
        >
          {busy && <Loader2 className="h-3 w-3 animate-spin" />}
          Add
        </button>
        <button
          onClick={onCancel}
          className="rounded px-2 py-1 text-xs text-w-dim transition-colors hover:text-w-text"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
