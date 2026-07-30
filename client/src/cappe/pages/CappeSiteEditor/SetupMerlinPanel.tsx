import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, Loader2, Sparkles, X, XCircle } from 'lucide-react'
import { useCappeMe } from '../../hooks/useCappeMe'
import type { CappeReadiness, CappeSetupAction, CappeSetupLink, CappeSite } from '../../types'
import { useSetupMerlin } from './useSetupMerlin'

interface SetupMerlinPanelProps {
  site: CappeSite
  autoOpen: boolean
  onSiteChanged: (readiness: CappeReadiness | null) => void
  onPublish: () => void
}

type Chip = { label: string; prompt: string }

const CREATOR_CHIPS: Chip[] = [
  { label: 'Sell a booking session', prompt: 'I want to sell a 1:1 booking session — set one up for me.' },
  { label: 'Sell a digital download', prompt: 'I want to sell a digital download.' },
  { label: 'Make an about-me page', prompt: 'Create an about-me page for my site.' },
  { label: 'Collect emails with a newsletter signup', prompt: 'Add a newsletter signup to my home page.' },
]

const BUSINESS_CHIPS: Chip[] = [
  { label: 'Create a newsletter signup', prompt: 'Add a newsletter signup to my home page.' },
  { label: 'Add a promo banner', prompt: 'Add a promo banner to my site.' },
  { label: 'Sell a product', prompt: 'I want to sell a product on my site.' },
  { label: 'Make an about page', prompt: 'Create an about page for my business.' },
]

function linkHref(siteId: string, target: string): string {
  if (target.startsWith('page:')) return `/cappe/sites/${siteId}/pages/${target.slice(5)}`
  switch (target) {
    case 'shop': return `/cappe/sites/${siteId}/shop`
    case 'subscribers': return `/cappe/sites/${siteId}/subscribers`
    case 'campaigns': return `/cappe/sites/${siteId}/campaigns`
    case 'bookings': return `/cappe/sites/${siteId}/bookings`
    default: return `/cappe/sites/${siteId}`
  }
}

function ActionCard({ action, onApprove, onDismiss, busy }: {
  action: CappeSetupAction
  onApprove: () => void
  onDismiss: () => void
  busy: boolean
}) {
  if (action.status === 'executed') {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-emerald-500/25 bg-emerald-500/[0.06] px-3 py-2.5 text-xs">
        <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" />
        <span className="text-zinc-300">{action.message || action.summary}</span>
      </div>
    )
  }
  if (action.status === 'dismissed') {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-2.5 text-xs text-zinc-500 line-through">
        {action.summary}
      </div>
    )
  }
  if (action.status === 'blocked') {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-amber-500/25 bg-amber-500/[0.06] px-3 py-2.5 text-xs">
        <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-400" />
        <span className="text-zinc-300">{action.message || 'This plan doesn’t allow that.'}</span>
      </div>
    )
  }
  // proposed
  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2.5">
      <p className="text-xs text-zinc-200">{action.summary}</p>
      <div className="mt-2 flex gap-2">
        <button
          onClick={onApprove}
          disabled={busy}
          className="inline-flex items-center gap-1 rounded-md bg-emerald-500 px-2.5 py-1 text-[11px] font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60"
        >
          {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
          Approve
        </button>
        <button
          onClick={onDismiss}
          disabled={busy}
          className="rounded-md border border-zinc-700 px-2.5 py-1 text-[11px] font-medium text-zinc-400 hover:bg-zinc-800 disabled:opacity-60"
        >
          Dismiss
        </button>
      </div>
    </div>
  )
}

export function SetupMerlinPanel({ site, autoOpen, onSiteChanged, onPublish }: SetupMerlinPanelProps) {
  const { account } = useCappeMe()
  // Fires on the REST approve path too (handleApprove, below) — this callback
  // is the ONE place a chat-confirmed execute (no REST round trip) also
  // reaches the dashboard's SetupGuide/pages refresh.
  const merlin = useSetupMerlin(site.id, onSiteChanged)
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const [busyActionId, setBusyActionId] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const autoOpenedRef = useRef(false)

  useEffect(() => {
    if (autoOpenedRef.current || !merlin.hydrated) return
    autoOpenedRef.current = true
    if (autoOpen && !merlin.hadPriorConversation) setOpen(true)
  }, [autoOpen, merlin.hydrated, merlin.hadPriorConversation])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [merlin.messages, merlin.stagedActions, merlin.liveStatus, merlin.liveSteps])

  async function handleApprove(actionId: string) {
    setBusyActionId(actionId)
    const readinessNow = await merlin.approve(actionId)
    setBusyActionId(null)
    onSiteChanged(readinessNow)
  }

  async function handleDismiss(actionId: string) {
    setBusyActionId(actionId)
    await merlin.dismiss(actionId)
    setBusyActionId(null)
  }

  function submit(text: string) {
    const trimmed = text.trim()
    if (!trimmed) return
    setDraft('')
    merlin.send(trimmed)
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 z-40 inline-flex items-center gap-2 rounded-full bg-emerald-500 px-4 py-3 text-sm font-semibold text-zinc-950 shadow-lg shadow-emerald-500/20 hover:bg-emerald-400"
      >
        <Sparkles className="h-4 w-4" /> Merlin
      </button>
    )
  }

  const firstName = (account?.name || '').split(' ')[0] || 'there'
  const chips = account?.account_type === 'personal' ? CREATOR_CHIPS : BUSINESS_CHIPS
  const showGreeting = merlin.messages.length === 0

  const pendingActions = merlin.stagedActions.filter((a) => a.status === 'proposed')
  const settledActions = merlin.stagedActions.filter((a) => a.status !== 'proposed')

  return (
    <div className="fixed bottom-6 right-6 z-40 flex h-[32rem] w-96 flex-col overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-950 shadow-2xl shadow-black/40">
      <div className="flex items-center justify-between border-b border-zinc-800 bg-zinc-900 px-4 py-3">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-emerald-400" />
          <span className="text-sm font-semibold text-zinc-100">Merlin</span>
        </div>
        <button onClick={() => setOpen(false)} className="text-zinc-500 hover:text-zinc-300">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {showGreeting && (
          <div>
            <p className="text-sm text-zinc-200">
              Hey {firstName}, let's set up your website — where should we start?
            </p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {chips.map((c) => (
                <button
                  key={c.label}
                  onClick={() => submit(c.prompt)}
                  disabled={merlin.sending}
                  className="rounded-full border border-zinc-700 bg-zinc-900 px-2.5 py-1 text-[11px] text-zinc-300 hover:border-emerald-500/50 hover:text-emerald-300 disabled:opacity-60"
                >
                  {c.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {merlin.messages.map((m, i) => (
          <div key={m.id || i} className={m.role === 'user' ? 'text-right' : 'text-left'}>
            <div
              className={`inline-block max-w-[85%] rounded-lg px-3 py-2 text-xs leading-relaxed ${
                m.role === 'user'
                  ? 'bg-emerald-500/15 text-emerald-100'
                  : 'bg-zinc-900 text-zinc-200'
              }`}
            >
              {m.content}
            </div>
            {m.role === 'assistant' && m.links && m.links.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {m.links.map((l: CappeSetupLink) =>
                  l.target === 'publish' ? (
                    <button
                      key={l.target}
                      onClick={onPublish}
                      className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-2 py-1 text-[11px] font-medium text-emerald-300 hover:bg-emerald-500/20"
                    >
                      {l.label}
                    </button>
                  ) : (
                    <Link
                      key={l.target}
                      to={linkHref(site.id, l.target)}
                      className="rounded-md border border-zinc-700 px-2 py-1 text-[11px] font-medium text-zinc-300 hover:border-emerald-500/50 hover:text-emerald-300"
                    >
                      {l.label}
                    </Link>
                  ),
                )}
              </div>
            )}
          </div>
        ))}

        {merlin.liveSteps.length > 0 && (
          <div className="space-y-0.5">
            {merlin.liveSteps.map((s, i) => (
              <div key={i} className="text-[11px] text-zinc-600">✓ {s.label}</div>
            ))}
          </div>
        )}

        {merlin.liveStatus && (
          <div className="flex items-center gap-1.5 text-[11px] text-zinc-500">
            <Loader2 className="h-3 w-3 animate-spin" /> {merlin.liveStatus}
          </div>
        )}

        {pendingActions.length > 0 && (
          <div className="space-y-2 border-t border-zinc-800 pt-3">
            {pendingActions.map((a) => (
              <ActionCard
                key={a.id}
                action={a}
                busy={busyActionId === a.id}
                onApprove={() => handleApprove(a.id)}
                onDismiss={() => handleDismiss(a.id)}
              />
            ))}
          </div>
        )}
        {settledActions.length > 0 && (
          <div className="space-y-2">
            {settledActions.map((a) => (
              <ActionCard key={a.id} action={a} busy={false} onApprove={() => {}} onDismiss={() => {}} />
            ))}
          </div>
        )}

        {merlin.error && <p className="text-xs text-red-400">{merlin.error}</p>}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          submit(draft)
        }}
        className="flex items-center gap-2 border-t border-zinc-800 bg-zinc-900 px-3 py-2.5"
      >
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Ask Merlin to set something up…"
          disabled={merlin.sending}
          className="flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-2.5 py-1.5 text-xs text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500 disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={merlin.sending || !draft.trim()}
          className="rounded-lg bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-50"
        >
          {merlin.sending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Send'}
        </button>
      </form>
    </div>
  )
}
