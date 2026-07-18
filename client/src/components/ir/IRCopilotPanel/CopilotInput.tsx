import { Loader2, Send } from 'lucide-react'

interface CopilotInputProps {
  input: string
  setInput: (value: string) => void
  streaming: boolean
  emergencyAlertActive: boolean
  onSubmit: () => void
}

export function CopilotInput({ input, setInput, streaming, emergencyAlertActive, onSubmit }: CopilotInputProps) {
  return (
    <div className="shrink-0 border-t border-white/[0.06] px-5 pb-2 pt-3">
      <div className="flex items-end gap-2 rounded-md border border-white/[0.08] bg-zinc-900/60 px-3 transition-colors focus-within:border-emerald-500/50">
        <span className="select-none pb-[9px] font-mono text-sm text-emerald-500/80">›</span>
        <input
          type="text"
          value={input}
          disabled={streaming || emergencyAlertActive}
          placeholder={emergencyAlertActive
            ? 'Acknowledge the OSHA reporting alert above to resume…'
            : 'Reply to copilot or ask a question…'}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              onSubmit()
            }
          }}
          className="flex-1 bg-transparent py-2 text-sm text-zinc-100 placeholder-zinc-600 outline-none disabled:opacity-60"
        />
        <button
          type="button"
          aria-label="Send"
          disabled={streaming || !input.trim() || emergencyAlertActive}
          onClick={onSubmit}
          className="mb-1.5 rounded p-1.5 text-emerald-400 transition-colors hover:bg-emerald-500/10 disabled:text-zinc-700 disabled:hover:bg-transparent"
        >
          {streaming ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </button>
      </div>
      <div className="text-[10px] text-zinc-600 mt-1.5">
        Copilot uses incident details + cached AI analyses. Accept a card to act; type to clarify or ask a follow-up.
      </div>
    </div>
  )
}
