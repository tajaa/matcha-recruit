import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { CappeApiError, cappePublicPost } from '../api'
import { ui } from './ui'

type State = 'idle' | 'sending' | 'sent' | 'limited' | 'error'

interface Props {
  /** Address to resend to. Omit to ask for it (the expired-link page has no
   *  other way to know who is asking). */
  email?: string
  label?: string
}

// Re-sends the confirmation email and says what actually happened. The endpoint
// answers 202 whether or not the address has an account, so "sent" is worded
// conditionally; a rate limit or a failed request is shown as such and can be
// retried, instead of a tick that claims an email went out.
export default function ResendVerification({ email: fixedEmail, label = 'Resend confirmation email' }: Props) {
  const [typed, setTyped] = useState('')
  const [state, setState] = useState<State>('idle')
  const email = (fixedEmail ?? typed).trim()

  async function send(e?: React.FormEvent) {
    e?.preventDefault()
    if (!email || state === 'sending') return
    setState('sending')
    try {
      await cappePublicPost('/auth/resend-verification', { email })
      setState('sent')
    } catch (err) {
      setState(err instanceof CappeApiError && err.status === 429 ? 'limited' : 'error')
    }
  }

  const button = (
    <button
      type={fixedEmail ? 'button' : 'submit'}
      onClick={fixedEmail ? () => send() : undefined}
      disabled={state === 'sending' || !email}
      className="inline-flex items-center gap-1.5 text-sm font-medium text-lime-400 hover:text-lime-300 disabled:opacity-60"
    >
      {state === 'sending' && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
      {state === 'sent' ? 'Send it again' : label}
    </button>
  )

  return (
    <div className="space-y-2 text-left">
      {fixedEmail ? button : (
        <form onSubmit={send} className="space-y-2">
          <label htmlFor="cappe-resend-email" className={ui.label}>Email you signed up with</label>
          <input
            id="cappe-resend-email"
            type="email"
            required
            autoComplete="email"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            className={ui.input}
            placeholder="you@example.com"
          />
          {button}
        </form>
      )}
      <p role="status" aria-live="polite" className="text-xs leading-relaxed">
        {state === 'sent' && (
          <span className="text-zinc-400">
            If {email} has an unconfirmed account, a new link is on its way. It can take a minute, and it replaces any earlier link.
          </span>
        )}
        {state === 'limited' && (
          <span className="text-amber-400">Too many requests just now. Wait a minute, then try again.</span>
        )}
        {state === 'error' && (
          <span className="text-red-400">We couldn’t send that. Check your connection and try again.</span>
        )}
      </p>
    </div>
  )
}
