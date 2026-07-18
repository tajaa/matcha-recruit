import { Send } from 'lucide-react'
import { Button } from '../../ui'
import type { ItaSubmissionRow } from './types'

interface ItaFilingPanelProps {
  itaCredConfigured: boolean | null
  showTokenInput: boolean
  setShowTokenInput: (fn: (v: boolean) => boolean) => void
  itaTokenInput: string
  setItaTokenInput: (v: string) => void
  saveItaToken: () => void
  savingToken: boolean
  itaSubmitMsg: { status: string; text: string } | null
  itaSubmissions: ItaSubmissionRow[]
}

export function ItaFilingPanel({
  itaCredConfigured,
  showTokenInput,
  setShowTokenInput,
  itaTokenInput,
  setItaTokenInput,
  saveItaToken,
  savingToken,
  itaSubmitMsg,
  itaSubmissions,
}: ItaFilingPanelProps) {
  return (
    <div className="bg-zinc-900/40 border border-white/[0.06] rounded-lg p-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-[10px] text-zinc-500 uppercase tracking-widest font-bold">
          <Send size={13} /> OSHA ITA Electronic Filing
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-[11px] ${itaCredConfigured ? 'text-emerald-400' : 'text-zinc-500'}`}>
            {itaCredConfigured === null ? '' : itaCredConfigured ? 'API token on file' : 'No API token'}
          </span>
          <Button size="sm" variant="ghost" onClick={() => setShowTokenInput((v) => !v)}>
            {itaCredConfigured ? 'Update token' : 'Add token'}
          </Button>
        </div>
      </div>

      {showTokenInput && (
        <div className="flex flex-col sm:flex-row gap-2">
          <input
            type="password"
            value={itaTokenInput}
            onChange={(e) => setItaTokenInput(e.target.value)}
            placeholder="OSHA ITA API token (from your ITA account)"
            className="flex-1 bg-zinc-950 border border-white/10 rounded-lg text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-zinc-600"
          />
          <Button size="sm" onClick={saveItaToken} disabled={savingToken || !itaTokenInput.trim()}>
            {savingToken ? 'Saving…' : 'Save token'}
          </Button>
        </div>
      )}

      {itaSubmitMsg && (
        <div
          className={`text-[12px] rounded-lg px-3 py-2 border ${
            itaSubmitMsg.status === 'ok'
              ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
              : itaSubmitMsg.status === 'warn'
                ? 'border-amber-500/30 bg-amber-500/10 text-amber-300'
                : 'border-red-500/30 bg-red-500/10 text-red-300'
          }`}
        >
          {itaSubmitMsg.text}
        </div>
      )}

      {itaSubmissions.length > 0 && (
        <div className="text-[11px] text-zinc-400">
          <div className="text-zinc-600 uppercase tracking-wider mb-1">Recent filings</div>
          <div className="space-y-1">
            {itaSubmissions.slice(0, 5).map((s) => (
              <div key={s.id} className="flex items-center justify-between gap-2 font-mono">
                <span>{s.year} · {s.establishment_count} est.</span>
                <span className={
                  s.status === 'submitted' || s.status === 'accepted' ? 'text-emerald-400'
                    : s.status === 'rejected' || s.status === 'error' ? 'text-red-400'
                    : 'text-zinc-500'
                }>
                  {s.status}{s.ita_submission_id ? ` · ${s.ita_submission_id}` : ''}
                </span>
                <span className="text-zinc-600">{new Date(s.submitted_at).toLocaleDateString()}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
