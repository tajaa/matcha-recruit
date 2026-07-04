import { useState } from 'react'
import { Sparkles, Loader2, AlertTriangle } from 'lucide-react'

interface AiDraftBarProps {
  drafting: boolean
  error: string | null
  onDraft: (prompt: string) => void
}

export default function AiDraftBar({ drafting, error, onDraft }: AiDraftBarProps) {
  const [prompt, setPrompt] = useState('')

  function submit() {
    const trimmed = prompt.trim()
    if (!trimmed || drafting) return
    onDraft(trimmed)
    setPrompt('')
  }

  return (
    <div className="mx-3 mb-1">
      <div className="flex items-center gap-1.5 rounded-md border border-emerald-600/25 bg-emerald-500/5 px-2.5 py-1.5">
        <Sparkles className="h-3 w-3 shrink-0 text-emerald-400" />
        <input
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') submit()
          }}
          placeholder="Describe a task to draft…"
          title='e.g. "fix the 503 in console <error> and assign haley"'
          className="min-w-0 flex-1 bg-transparent text-xs text-zinc-100 placeholder-zinc-500 outline-none"
        />
        <button
          onClick={submit}
          disabled={drafting || !prompt.trim()}
          className="flex shrink-0 items-center gap-1 rounded bg-emerald-600 px-2 py-1 text-[11px] font-semibold text-white transition-colors hover:bg-emerald-500 disabled:opacity-50"
        >
          {drafting && <Loader2 className="h-3 w-3 animate-spin" />}
          Draft
        </button>
      </div>
      {error && (
        <p className="mt-1 flex items-center gap-1 text-[11px] text-orange-400">
          <AlertTriangle className="h-3 w-3 shrink-0" />
          {error}
        </p>
      )}
    </div>
  )
}
