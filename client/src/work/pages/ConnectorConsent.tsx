import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Loader2, PlugZap, ShieldCheck } from 'lucide-react'
import { useMe } from '../../hooks/useMe'
import {
  decideConnectorConsent,
  describeConnectorConsent,
  type ConsentDescription,
} from '../api/matchaWork'

const SCOPE_COPY: Record<string, string> = {
  'kanban:read': 'Read the research cards on your boards, their attachments and earlier reports',
  'kanban:write': 'Start research cards and attach finished reports (moves the card to Review)',
}

/**
 * OAuth consent for the Matcha AI connector (`/oauth/consent?request=…`).
 *
 * Claude / ChatGPT send the person here while connecting Matcha. The page is
 * routed at the app root, outside any surface provider, and the handle in
 * `request` is a signed, 10-minute authorize request — not a credential.
 * Approving mints a one-time code bound to the signed-in person and returns
 * them to the assistant; nothing about their Claude or ChatGPT account ever
 * reaches Matcha.
 */
export default function ConnectorConsent() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const request = params.get('request') || ''
  const { me, loading: meLoading, authFailed } = useMe()

  const [info, setInfo] = useState<ConsentDescription | null>(null)
  const [error, setError] = useState<string | null>(request ? null : 'This link is missing its connection request.')
  const [deciding, setDeciding] = useState<'approve' | 'deny' | null>(null)

  // Tokens are per-tab, and assistants open this in a fresh tab — so a signed
  // out visitor is sent through login and straight back here.
  useEffect(() => {
    if (!meLoading && authFailed && request) {
      const next = `/oauth/consent?request=${encodeURIComponent(request)}`
      navigate(`/login?next=${encodeURIComponent(next)}`, { replace: true })
    }
  }, [meLoading, authFailed, request, navigate])

  useEffect(() => {
    if (!me || !request) return
    describeConnectorConsent(request)
      .then(setInfo)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'This connection request is no longer valid.'))
  }, [me, request])

  async function decide(approve: boolean) {
    setDeciding(approve ? 'approve' : 'deny')
    setError(null)
    try {
      const { redirect_url } = await decideConnectorConsent(request, approve)
      window.location.assign(redirect_url)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Could not complete the connection.')
      setDeciding(null)
    }
  }

  const loading = !error && !info && (meLoading || !!me || authFailed)

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center px-4">
      <div className="w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-900/60 p-6 shadow-xl">
        <div className="flex items-center gap-3 mb-5">
          <div className="h-10 w-10 rounded-xl bg-emerald-500/10 ring-1 ring-inset ring-emerald-500/30 flex items-center justify-center">
            <PlugZap className="h-5 w-5 text-emerald-300" />
          </div>
          <div>
            <h1 className="text-base font-semibold">Connect an assistant to Matcha</h1>
            {me?.user?.email && <p className="text-xs text-zinc-400">Signed in as {me.user.email}</p>}
          </div>
        </div>

        {loading && (
          <div className="flex items-center gap-2 text-sm text-zinc-400 py-6">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading request…
          </div>
        )}

        {error && <p className="text-sm text-red-300 py-2">{error}</p>}

        {info && (
          <>
            <p className="text-sm text-zinc-300 leading-relaxed">
              <span className="font-medium text-zinc-100">{info.client_name}</span> wants to work with
              your Matcha boards. The assistant runs on your own {info.client_kind === 'chatgpt' || info.client_kind === 'codex' ? 'ChatGPT' : info.client_kind === 'other' ? 'assistant' : 'Claude'} plan;
              Matcha never sees that account.
            </p>
            <p className="mt-3 text-xs text-zinc-400">
              You will be returned to <span className="font-mono text-zinc-200">{info.redirect_host}</span>.
              Only continue if you started this from that assistant.
            </p>

            <ul className="mt-5 space-y-2">
              {info.scopes.map((scope) => (
                <li key={scope} className="flex gap-2 text-sm text-zinc-300">
                  <ShieldCheck className="h-4 w-4 mt-0.5 shrink-0 text-emerald-300" />
                  <span>{SCOPE_COPY[scope] ?? scope}</span>
                </li>
              ))}
            </ul>

            <p className="mt-5 text-xs text-zinc-500">
              You can disconnect it any time from Settings → AI connectors. Changing your password
              disconnects every assistant.
            </p>

            <div className="mt-6 flex gap-3 justify-end">
              <button
                type="button"
                disabled={deciding !== null}
                onClick={() => decide(false)}
                className="px-4 py-2 rounded-lg text-sm text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
              >
                {deciding === 'deny' ? 'Cancelling…' : 'Cancel'}
              </button>
              <button
                type="button"
                disabled={deciding !== null}
                onClick={() => decide(true)}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-emerald-500/15 text-emerald-200 ring-1 ring-inset ring-emerald-500/40 hover:bg-emerald-500/25 disabled:opacity-50"
              >
                {deciding === 'approve' ? 'Connecting…' : 'Allow'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
