import { useState } from 'react'
import { Check, Loader2 } from 'lucide-react'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

export function NewsletterHeroSection() {
  const [email, setEmail] = useState('')
  const [status, setStatus] = useState<'idle' | 'submitting' | 'done' | 'error'>('idle')
  const [error, setError] = useState<string | null>(null)
  const [honeypot, setHoneypot] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!email.trim() || !email.includes('@')) {
      setError('Enter a valid email.')
      return
    }
    setStatus('submitting')
    setError(null)

    const params = new URLSearchParams(window.location.search)
    const utm = {
      utm_source: params.get('utm_source') || undefined,
      utm_medium: params.get('utm_medium') || undefined,
      utm_campaign: params.get('utm_campaign') || undefined,
    }

    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    const token = localStorage.getItem('matcha_access_token')
    if (token) headers.Authorization = `Bearer ${token}`

    try {
      const res = await fetch(`${BASE}/newsletter/subscribe`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          email: email.trim().toLowerCase(),
          source: 'landing_hero',
          website: honeypot,
          ...utm,
        }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setError(data.detail ?? 'Something went wrong. Try again.')
        setStatus('error')
        return
      }
      setStatus('done')
    } catch {
      setError('Network error. Try again.')
      setStatus('error')
    }
  }

  return (
    <section
      className="w-full py-24 sm:py-32"
      style={{ backgroundColor: 'var(--color-ivory-ink)' }}
    >
      <div className="max-w-2xl mx-auto px-6 text-center">
        <p
          className="text-[11px] uppercase tracking-[0.2em] font-medium mb-4"
          style={{ color: '#c9b48e' }}
        >
          Weekly Brief
        </p>
        <h2
          className="text-3xl sm:text-4xl font-semibold tracking-tight mb-4"
          style={{ color: 'rgba(240,236,228,0.97)' }}
        >
          Where HR goes for HR problems.
        </h2>
        <p
          className="text-base leading-relaxed mb-10"
          style={{ color: 'rgba(228,222,210,0.6)' }}
        >
          One short brief a week — employment-law changes, compliance gotchas, and the occasional template. No pitch.
        </p>

        {status === 'done' ? (
          <div
            className="inline-flex items-center gap-2 text-sm"
            style={{ color: 'rgba(240,236,228,0.85)' }}
          >
            <Check className="w-4 h-4 text-emerald-400" />
            Check your inbox to confirm.
          </div>
        ) : (
          <>
            <form onSubmit={handleSubmit} className="flex gap-3 max-w-md mx-auto">
              <input
                type="text"
                name="website"
                tabIndex={-1}
                autoComplete="off"
                aria-hidden="true"
                value={honeypot}
                onChange={e => setHoneypot(e.target.value)}
                style={{ position: 'absolute', left: '-9999px', width: 1, height: 1, opacity: 0 }}
              />
              <input
                type="email"
                required
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="you@company.com"
                className="flex-1 rounded-lg px-4 py-3 text-sm outline-none"
                style={{
                  backgroundColor: 'rgba(255,255,255,0.07)',
                  border: '1px solid rgba(255,255,255,0.12)',
                  color: 'rgba(240,236,228,0.95)',
                }}
              />
              <button
                type="submit"
                disabled={status === 'submitting'}
                className="px-5 py-3 rounded-lg text-sm font-medium transition-opacity hover:opacity-90 disabled:opacity-50 inline-flex items-center gap-1.5 shrink-0"
                style={{ backgroundColor: '#c9b48e', color: '#1a1814' }}
              >
                {status === 'submitting' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
                Subscribe
              </button>
            </form>
            {error && (
              <p className="mt-3 text-xs" style={{ color: '#e07a6a' }}>{error}</p>
            )}
            <p className="mt-4 text-[11px]" style={{ color: 'rgba(228,222,210,0.4)' }}>
              We'll send a confirmation email. Unsubscribe anytime.
            </p>
          </>
        )}
      </div>
    </section>
  )
}
