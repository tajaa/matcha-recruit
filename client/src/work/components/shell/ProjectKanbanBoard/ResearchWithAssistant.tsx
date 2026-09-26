import { useEffect, useState } from 'react'
import { Check, Copy, ExternalLink, Loader2, Sparkles } from 'lucide-react'
import type { MWProjectTask } from '../../../types'
import { launchResearchWith, listConnectors, type ConnectorsState, type LaunchClient } from '../../../api/matchaWork'

const OPEN_COLUMNS = new Set(['todo', 'changes_requested', 'in_progress'])

/**
 * "Research with Claude / ChatGPT" for a research card.
 *
 * Opens a prefilled chat in the person's own assistant; the model runs on
 * their plan and reads/publishes the card through the Matcha connector
 * (backend: routes/mcp_connector). AutoPR's server-side run stays available —
 * this is the alternative when the person has an assistant connected.
 */
export default function ResearchWithAssistant({ projectId, task }: { projectId: string; task: MWProjectTask }) {
  const [state, setState] = useState<ConnectorsState | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState<string | null>(null)

  const eligible = task.category === 'research' && OPEN_COLUMNS.has(task.board_column)

  useEffect(() => {
    if (!eligible) return
    listConnectors().then(setState).catch(() => setState(null))
  }, [eligible])

  if (!eligible) return null

  async function copy(text: string, key: string) {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(key)
      setTimeout(() => setCopied(null), 1500)
    } catch {
      /* clipboard blocked — the text is still visible */
    }
  }

  async function launch(client: LaunchClient) {
    setBusy(client)
    setError(null)
    try {
      const res = await launchResearchWith(projectId, task.id, client)
      if (res.url) window.open(res.url, '_blank', 'noopener,noreferrer')
      else if (res.command) await copy(res.command, client)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Could not start the research chat.')
    } finally {
      setBusy(null)
    }
  }

  const connected = state?.connected
  const anyConnected = !!connected && Object.values(connected).some(Boolean)

  return (
    <div className="rounded-lg border border-w-line bg-w-surface/60 p-3">
      <div className="flex items-center gap-1.5 text-xs font-medium text-w-dim">
        <Sparkles className="h-3.5 w-3.5" /> Research with your assistant
      </div>
      <p className="mt-1 text-xs text-w-dim">
        Runs on your own Claude or ChatGPT plan and posts the report back here.
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        {(['claude', 'chatgpt'] as const).map((client) => (
          <button
            key={client}
            onClick={() => launch(client)}
            disabled={busy !== null}
            className="flex items-center gap-1.5 rounded-lg border border-w-line px-2.5 py-1.5 text-xs font-medium text-w-text transition-colors hover:bg-w-surface disabled:opacity-50"
          >
            {busy === client ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ExternalLink className="h-3.5 w-3.5" />}
            {client === 'claude' ? 'Claude' : 'ChatGPT'}
            {connected?.[client] && <Check className="h-3 w-3 text-w-accent" />}
          </button>
        ))}
        {(['claude_code', 'codex'] as const).map((client) => (
          <button
            key={client}
            onClick={() => launch(client)}
            disabled={busy !== null}
            title={`Copy a \`${client === 'codex' ? 'codex' : 'claude'}\` command that works this card from your terminal`}
            className="flex items-center gap-1.5 rounded-lg border border-w-line px-2.5 py-1.5 text-xs font-medium text-w-text transition-colors hover:bg-w-surface disabled:opacity-50"
          >
            {copied === client ? <Check className="h-3.5 w-3.5 text-w-accent" /> : <Copy className="h-3.5 w-3.5" />}
            {client === 'codex' ? 'Codex' : 'Claude Code'}
            {connected?.[client] && <Check className="h-3 w-3 text-w-accent" />}
          </button>
        ))}
      </div>
      {state && !anyConnected && (
        <div className="mt-2 text-xs text-w-dim">
          Not connected yet — set one up in Settings → AI connectors, or add this URL as a connector:
          <button
            onClick={() => copy(state.mcp_url, 'url')}
            className="mt-1 flex w-full items-center justify-between gap-2 rounded border border-w-line px-2 py-1 font-mono text-[11px] text-w-text"
          >
            <span className="truncate">{state.mcp_url}</span>
            {copied === 'url' ? <Check className="h-3 w-3 shrink-0 text-w-accent" /> : <Copy className="h-3 w-3 shrink-0" />}
          </button>
        </div>
      )}
      {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
    </div>
  )
}
