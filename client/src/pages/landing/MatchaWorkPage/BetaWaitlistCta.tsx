import { useState } from 'react'

import { api } from '../../../api/client'
import { INK, BG, MUTED, LINE, DISPLAY } from './constants'

// ---------------------------------------------------------------------------
// Beta Waitlist CTA
// ---------------------------------------------------------------------------

export function BetaWaitlistCta() {
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!email.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      await api.post('/newsletter/subscribe', {
        email: email.trim(),
        name: name.trim() || undefined,
        source: 'matcha_work_beta_waitlist',
      })
      setSubmitted(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="py-16 sm:py-24 md:py-32 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-5 sm:px-10">
        <div className="max-w-xl mx-auto text-center">
          <p
            className="text-[11px] uppercase tracking-[0.2em] mb-4 sm:mb-5"
            style={{ color: MUTED }}
          >
            Private Beta
          </p>
          <h2
            className="tracking-tight"
            style={{
              fontFamily: DISPLAY,
              fontWeight: 400,
              color: INK,
              fontSize: 'clamp(1.75rem, 5vw, 3rem)',
              lineHeight: 1.05,
            }}
          >
            Join the Matcha Work waitlist.
          </h2>
          <p className="mt-4 sm:mt-5 text-base sm:text-lg" style={{ color: MUTED }}>
            Early access opens in waves. We'll email you when your seat is ready.
          </p>

          {submitted ? (
            <div
              className="mt-10 inline-flex items-center px-6 h-12 rounded-full text-[15px]"
              style={{ border: `1px solid ${LINE}`, color: INK }}
            >
              ✓ You're on the list — we'll be in touch.
            </div>
          ) : (
            <form
              onSubmit={handleSubmit}
              className="mt-8 sm:mt-10 flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5 sm:gap-3 max-w-lg mx-auto"
            >
              <input
                type="text"
                placeholder="Your name (optional)"
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={submitting}
                className="sm:w-40 px-4 h-12 rounded-full text-[15px] outline-none transition-colors w-full"
                style={{
                  border: `1px solid ${LINE}`,
                  backgroundColor: 'transparent',
                  color: INK,
                }}
              />
              <input
                type="email"
                required
                placeholder="you@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={submitting}
                className="flex-1 px-4 h-12 rounded-full text-[15px] outline-none transition-colors"
                style={{
                  border: `1px solid ${LINE}`,
                  backgroundColor: 'transparent',
                  color: INK,
                }}
              />
              <button
                type="submit"
                disabled={submitting || !email.trim()}
                className="inline-flex items-center justify-center px-7 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90 disabled:opacity-40"
                style={{ backgroundColor: INK, color: BG }}
              >
                {submitting ? 'Joining…' : 'Join waitlist'}
              </button>
            </form>
          )}

          {error && (
            <p className="mt-4 text-sm" style={{ color: '#c04444' }}>
              {error}
            </p>
          )}

          <p
            className="mt-6 text-[12px]"
            style={{ color: MUTED }}
          >
            No spam. Unsubscribe anytime.
          </p>
        </div>
      </div>
    </section>
  )
}
