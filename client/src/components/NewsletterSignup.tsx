import { useState } from 'react'
import { Mail, Check, Loader2 } from 'lucide-react'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

type Variant = 'inline' | 'card' | 'footer'

type Props = {
  source: string
  variant?: Variant
  headline?: string
  description?: string
  className?: string
  /** When false, renders only the form — caller handles their own headline. */
  showHeadline?: boolean
}

const DEFAULT_HEADLINE = 'HR insights, in your inbox.'
const DEFAULT_DESCRIPTION = "One short brief a week — employment-law changes, compliance gotchas, and the occasional template. No pitch."

/**
 * Drop-in newsletter signup. Three variants share the same submit logic but
 * differ in chrome:
 * - `inline`: input + button on one row, light card around it. Use mid-page.
 * - `card`: bigger card with headline + description above the form.
 * - `footer`: dense layout for site footer; minimal copy.
 *
 * Auth bearer is forwarded if present so the backend can derive a tier-tag
 * (tier-free / tier-lite / tier-platform / tier-personal) for segmentation.
 * UTM params are sniffed from the URL and forwarded as metadata.
 */
export default function NewsletterSignup({
  source,
  variant = 'card',
  headline = DEFAULT_HEADLINE,
  description = DEFAULT_DESCRIPTION,
  className = '',
  showHeadline = true,
}: Props) {
  const [email, setEmail] = useState('')
  const [status, setStatus] = useState<'idle' | 'submitting' | 'done' | 'error'>('idle')
  const [error, setError] = useState<string | null>(null)

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
          source,
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

  if (status === 'done') {
    return (
      <div className={`${rootCls(variant)} ${className}`}>
        <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--color-ivory-ink)' }}>
          <Check className="w-4 h-4 text-emerald-600" />
          <span>Check your inbox to confirm.</span>
        </div>
      </div>
    )
  }

  return (
    <div className={`${rootCls(variant)} ${className}`}>
      {showHeadline && (
        <div className={variant === 'footer' ? 'mb-3' : 'mb-4'}>
          <div
            className={variant === 'footer' ? 'text-xs uppercase tracking-wider mb-1' : 'flex items-center gap-2 text-sm font-semibold mb-1'}
            style={{ color: variant === 'footer' ? 'var(--color-ivory-muted)' : 'var(--color-ivory-ink)' }}
          >
            {variant !== 'footer' && <Mail className="w-4 h-4 opacity-70" />}
            {headline}
          </div>
          {description && (
            <p className="text-xs leading-relaxed" style={{ color: 'var(--color-ivory-muted)' }}>
              {description}
            </p>
          )}
        </div>
      )}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@company.com"
          className="flex-1 rounded-lg px-3 py-2 text-sm outline-none"
          style={{
            backgroundColor: 'rgba(31,29,26,0.02)',
            border: '1px solid var(--color-ivory-line)',
            color: 'var(--color-ivory-ink)',
          }}
        />
        <button
          type="submit"
          disabled={status === 'submitting'}
          className="px-4 py-2 rounded-lg text-sm font-medium transition-opacity hover:opacity-90 disabled:opacity-50 inline-flex items-center gap-1.5"
          style={{ backgroundColor: 'var(--color-ivory-ink)', color: 'var(--color-ivory-bg)' }}
        >
          {status === 'submitting' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
          Subscribe
        </button>
      </form>
      {error && (
        <p className="mt-2 text-xs" style={{ color: '#8a4a3a' }}>{error}</p>
      )}
      <p className="mt-2 text-[10px]" style={{ color: 'var(--color-ivory-muted)' }}>
        We'll send a confirmation email. Unsubscribe anytime.
      </p>
    </div>
  )
}

function rootCls(variant: Variant): string {
  switch (variant) {
    case 'inline':
      return 'rounded-xl p-4 border'
    case 'footer':
      return ''
    case 'card':
    default:
      return 'rounded-2xl p-6 border'
  }
}
