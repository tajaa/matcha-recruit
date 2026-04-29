import { useState, type ReactNode } from 'react'
import { Button, Card, Textarea } from './ui'
import { CheckCircle2, Loader2, Sparkles } from 'lucide-react'
import { api } from '../api/client'

type Variant = 'sidebar' | 'page'

type Props = {
  /** Tag describing where the user clicked from (recorded in lead_captures.source). */
  source: string
  /** Headline copy in the card header. */
  title?: string
  /** One-paragraph pitch above the bullets. */
  pitch?: ReactNode
  /** Bullet list of unlocked features. */
  bullets?: string[]
  /**
   * `sidebar` (default) — narrow card sized to fit the IR-detail-style right
   * column. `page` — wider centered card for full-page replacements where
   * a Cap-tier user URL-hops to a feature they haven't unlocked.
   */
  variant?: Variant
}

const DEFAULT_BULLETS = [
  'Policies + handbook mapping',
  'ER Copilot case management',
  'Progressive discipline + e-signature',
  'Compliance monitoring + risk assessment',
]

export function UpgradeUpsellCard({
  source,
  title = 'Upgrade to Matcha Platform',
  pitch,
  bullets = DEFAULT_BULLETS,
  variant = 'sidebar',
}: Props) {
  const [open, setOpen] = useState(false)
  const [message, setMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit() {
    setSubmitting(true)
    setError('')
    try {
      await api.post('/resources/upgrade/inquiry', { message, source })
      setSubmitted(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to send inquiry')
    } finally {
      setSubmitting(false)
    }
  }

  const cardClass =
    variant === 'page'
      ? 'p-0 overflow-hidden border-emerald-900/30 max-w-2xl mx-auto mt-12'
      : 'p-0 overflow-hidden border-emerald-900/30'

  return (
    <Card className={cardClass}>
      <div className="px-5 py-3 border-b border-zinc-800/60 bg-emerald-900/10 flex items-center gap-2">
        <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
        <h3 className="text-xs font-semibold uppercase tracking-wider text-emerald-300">
          {title}
        </h3>
      </div>
      <div className="px-5 py-4 space-y-3">
        {submitted ? (
          <div className="flex items-start gap-2 text-sm text-emerald-300">
            <CheckCircle2 className="w-4 h-4 mt-0.5 flex-shrink-0" />
            <div>
              <div className="font-medium">Inquiry sent.</div>
              <div className="text-xs text-zinc-400 mt-1">
                A member of the team will reach out to you shortly.
              </div>
            </div>
          </div>
        ) : (
          <>
            {pitch && (
              <p className={`${variant === 'page' ? 'text-sm' : 'text-xs'} text-zinc-400 leading-relaxed`}>
                {pitch}
              </p>
            )}
            <ul className={`${variant === 'page' ? 'text-sm' : 'text-xs'} text-zinc-500 space-y-1 list-disc list-inside`}>
              {bullets.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>

            {open && (
              <Textarea
                label="Optional note for our team"
                placeholder="Tell us about your team size, current pain points, etc."
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                rows={3}
                maxLength={2000}
              />
            )}
            {error && <p className="text-xs text-red-400">{error}</p>}

            <div className="flex justify-end gap-2 pt-1">
              {open ? (
                <>
                  <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
                    Cancel
                  </Button>
                  <Button size="sm" onClick={handleSubmit} disabled={submitting}>
                    {submitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : 'Send inquiry'}
                  </Button>
                </>
              ) : (
                <Button size="sm" onClick={() => setOpen(true)}>
                  Talk to sales
                </Button>
              )}
            </div>
          </>
        )}
      </div>
    </Card>
  )
}
