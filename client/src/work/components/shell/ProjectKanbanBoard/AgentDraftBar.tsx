import { useState } from 'react'

interface Props {
  busy: boolean
  error: string | null
  status: string | null
  onDraft: (prompt: string) => void
}

export default function AgentDraftBar({ busy, error, status, onDraft }: Props) {
  const [prompt, setPrompt] = useState('')
  return (
    <div className="mx-3 mb-2 space-y-1 rounded-lg border border-w-line bg-w-surface/60 p-2.5">
      <label className="block text-xs font-medium text-w-text" htmlFor="repo-task-prompt">Draft from repository</label>
      <textarea
        id="repo-task-prompt"
        value={prompt}
        onChange={(event) => setPrompt(event.target.value)}
        maxLength={12000}
        rows={2}
        placeholder="Describe the change; Espresso will read the connected repository."
        className="w-full resize-y rounded border border-w-line bg-w-bg p-2 text-xs text-w-text"
      />
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={busy || !prompt.trim()}
          onClick={() => onDraft(prompt)}
          className="rounded bg-w-accent px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
        >
          {busy ? 'Drafting…' : 'Draft with repo'}
        </button>
        {busy && <span className="text-xs text-w-dim">{status === 'running' ? 'Reading repository…' : 'Queued…'}</span>}
      </div>
      {error && <p role="alert" className="text-xs text-orange-400">{error}</p>}
    </div>
  )
}
