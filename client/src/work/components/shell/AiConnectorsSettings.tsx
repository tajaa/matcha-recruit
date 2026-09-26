import { useCallback, useEffect, useState } from 'react'
import { Check, Copy, ExternalLink, Loader2, PlugZap, Unplug } from 'lucide-react'
import {
  disconnectConnector,
  listConnectors,
  type ConnectorKind,
  type ConnectorsState,
  type LaunchClient,
} from '../../api/matchaWork'

const KIND_LABEL: Record<ConnectorKind, string> = {
  claude: 'Claude',
  chatgpt: 'ChatGPT',
  claude_code: 'Claude Code',
  codex: 'Codex',
  other: 'Other assistant',
}

function CopyLine({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text)
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        } catch {
          /* clipboard blocked — the text is selectable */
        }
      }}
      className="mt-1 flex w-full items-center justify-between gap-2 rounded border border-w-line bg-w-bg px-2 py-1 text-left font-mono text-[11px] text-w-text hover:bg-w-surface2"
    >
      <span className="select-all truncate">{text}</span>
      {copied ? <Check className="h-3 w-3 shrink-0 text-w-accent" /> : <Copy className="h-3 w-3 shrink-0 text-w-dim" />}
    </button>
  )
}

/**
 * Settings → AI connectors. Where a person hooks their own Claude, ChatGPT,
 * Claude Code or Codex up to Matcha so research cards run on their plan.
 *
 * Connecting always happens *in the assistant* (it signs in to Matcha through
 * our OAuth consent page) — Matcha never takes a Claude or OpenAI login, so
 * this page only shows the steps and lists / disconnects what is connected.
 */
export default function AiConnectorsSettings() {
  const [state, setState] = useState<ConnectorsState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [disconnecting, setDisconnecting] = useState<string | null>(null)

  const load = useCallback(() => {
    listConnectors()
      .then((s) => {
        setState(s)
        setError(null)
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Could not load connectors.'))
  }, [])

  useEffect(load, [load])

  async function disconnect(clientId: string) {
    setDisconnecting(clientId)
    try {
      await disconnectConnector(clientId)
      load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Could not disconnect.')
    } finally {
      setDisconnecting(null)
    }
  }

  const connected = (k: LaunchClient) => !!state?.connected[k]
  const badge = (k: LaunchClient) =>
    connected(k) ? (
      <span className="ml-2 inline-flex items-center gap-1 text-[11px] font-medium text-w-accent">
        <Check className="h-3 w-3" /> Connected
      </span>
    ) : null

  return (
    <section className="rounded-xl border border-w-line bg-w-surface p-5">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-w-text">
        <PlugZap className="h-4 w-4" /> AI connectors
      </h2>
      <p className="mt-1 text-xs text-w-dim">
        Let your own Claude, ChatGPT, Claude Code or Codex work your research cards. The research runs on your
        plan; Matcha never sees that account — you sign in to Matcha from the assistant, not the other way round.
      </p>

      {!state && !error && <Loader2 className="mt-4 h-4 w-4 animate-spin text-w-dim" />}
      {error && <p className="mt-3 text-xs text-red-400">{error}</p>}

      {state && (
        <>
          {state.grants.length > 0 && (
            <ul className="mt-4 divide-y divide-w-line rounded-lg border border-w-line">
              {state.grants.map((g) => (
                <li key={g.client_id} className="flex items-center justify-between gap-3 px-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm text-w-text">{g.client_name}</p>
                    <p className="text-[11px] text-w-dim">
                      {KIND_LABEL[g.kind]}
                      {g.last_used_at ? ` · last used ${new Date(g.last_used_at).toLocaleDateString()}` : ''}
                    </p>
                  </div>
                  <button
                    type="button"
                    disabled={disconnecting === g.client_id}
                    onClick={() => disconnect(g.client_id)}
                    className="flex shrink-0 items-center gap-1 rounded-lg px-2 py-1 text-xs text-red-400 hover:bg-red-500/10 disabled:opacity-50"
                  >
                    {disconnecting === g.client_id ? <Loader2 className="h-3 w-3 animate-spin" /> : <Unplug className="h-3 w-3" />}
                    Disconnect
                  </button>
                </li>
              ))}
            </ul>
          )}

          <div className="mt-4 space-y-4 text-xs text-w-dim">
            <div>
              <p className="font-medium text-w-text">Connector URL{badge('claude')}</p>
              <CopyLine text={state.mcp_url} />
            </div>

            <div>
              <p className="font-medium text-w-text">Claude (claude.ai / desktop){badge('claude')}</p>
              <p className="mt-0.5">Settings → Connectors → Add custom connector → paste the URL above → Connect.</p>
              <a
                href="https://claude.ai/settings/connectors"
                target="_blank"
                rel="noopener noreferrer"
                className="mt-1 inline-flex items-center gap-1 text-w-accent hover:underline"
              >
                Open Claude connectors <ExternalLink className="h-3 w-3" />
              </a>
            </div>

            <div>
              <p className="font-medium text-w-text">ChatGPT{badge('chatgpt')}</p>
              <p className="mt-0.5">
                Settings → Apps &amp; Connectors → Advanced → turn on Developer mode → Create → paste the URL, choose
                OAuth. Needs Plus, Pro, Business or Enterprise.
              </p>
            </div>

            <div>
              <p className="font-medium text-w-text">Claude Code{badge('claude_code')}</p>
              <p className="mt-0.5">Run this, then type <span className="font-mono">/mcp</span> in Claude Code to sign in:</p>
              <CopyLine text={state.claude_code_command} />
            </div>

            <div>
              <p className="font-medium text-w-text">Codex CLI{badge('codex')}</p>
              <p className="mt-0.5">Run these; the second opens Matcha in your browser to approve:</p>
              {state.codex_commands.map((c) => (
                <CopyLine key={c} text={c} />
              ))}
            </div>

            <p>
              Then open any research card and use <span className="text-w-text">Research with…</span>. Changing your
              password disconnects every assistant.
            </p>
          </div>
        </>
      )}
    </section>
  )
}
