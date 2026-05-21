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
      className="relative w-full overflow-hidden py-28 sm:py-36"
      style={{ backgroundColor: 'var(--color-ivory-ink)' }}
    >
      {/* Caramel radial glow + faint grid for depth */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{ background: 'radial-gradient(58% 80% at 50% -10%, rgba(201,180,142,0.18), transparent 65%)' }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.04]"
        style={{
          backgroundImage:
            'linear-gradient(rgba(240,236,228,0.6) 1px, transparent 1px), linear-gradient(90deg, rgba(240,236,228,0.6) 1px, transparent 1px)',
          backgroundSize: '44px 44px',
          maskImage: 'radial-gradient(60% 60% at 50% 30%, black, transparent 75%)',
          WebkitMaskImage: 'radial-gradient(60% 60% at 50% 30%, black, transparent 75%)',
        }}
      />
      {/* Hairline accent on the top edge */}
      <div
        aria-hidden
        className="absolute inset-x-0 top-0 h-px"
        style={{ background: 'linear-gradient(90deg, transparent, rgba(201,180,142,0.45), transparent)' }}
      />

      <div className="relative max-w-2xl mx-auto px-6 text-center">
        <span
          className="inline-flex items-center gap-2 rounded-full px-3.5 py-1 text-[11px] uppercase tracking-[0.22em] font-medium mb-7"
          style={{
            color: '#dcc79b',
            border: '1px solid rgba(201,180,142,0.28)',
            backgroundColor: 'rgba(201,180,142,0.07)',
          }}
        >
          <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ backgroundColor: '#c9b48e' }} />
          Weekly Brief
        </span>

        <h2
          className="text-4xl sm:text-5xl font-semibold tracking-tight mb-5"
          style={{ color: 'rgba(240,236,228,0.98)', lineHeight: 1.05 }}
        >
          Where HR goes
          <br />
          for{' '}
          <span
            style={{
              background: 'linear-gradient(95deg, #e7d3a8, #c9b48e 60%, #b59a6a)',
              WebkitBackgroundClip: 'text',
              backgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
            }}
          >
            HR problems.
          </span>
        </h2>

        <p
          className="text-base leading-relaxed mb-10 max-w-lg mx-auto"
          style={{ color: 'rgba(228,222,210,0.62)' }}
        >
          One short brief a week — employment-law changes, compliance gotchas, and the occasional template. No pitch.
        </p>

        {status === 'done' ? (
          <div
            className="inline-flex items-center gap-2 rounded-full px-5 py-3 text-sm"
            style={{
              color: 'rgba(240,236,228,0.9)',
              border: '1px solid rgba(201,180,142,0.25)',
              backgroundColor: 'rgba(201,180,142,0.06)',
            }}
          >
            <Check className="w-4 h-4 text-emerald-400" />
            Check your inbox to confirm.
          </div>
        ) : (
          <>
            <form
              onSubmit={handleSubmit}
              className="mx-auto flex max-w-md items-center gap-2 rounded-full p-1.5 transition-shadow focus-within:[box-shadow:0_0_0_4px_rgba(201,180,142,0.18)]"
              style={{
                backgroundColor: 'rgba(255,255,255,0.06)',
                border: '1px solid rgba(255,255,255,0.14)',
              }}
            >
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
                className="flex-1 bg-transparent px-4 py-2.5 text-sm outline-none placeholder:opacity-50"
                style={{ color: 'rgba(240,236,228,0.96)' }}
              />
              <button
                type="submit"
                disabled={status === 'submitting'}
                className="shrink-0 inline-flex items-center gap-1.5 rounded-full px-6 py-2.5 text-sm font-semibold transition-transform hover:scale-[1.03] active:scale-95 disabled:opacity-50"
                style={{
                  backgroundColor: '#c9b48e',
                  color: '#1a1814',
                  boxShadow: '0 6px 20px -6px rgba(201,180,142,0.5)',
                }}
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
