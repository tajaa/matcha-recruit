import { useEffect, useState } from 'react'
import { X } from 'lucide-react'

import { api } from '../../../api/client'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

interface Props {
  open: boolean
  onClose: () => void
  asset: { slug: string; name: string } | null
}

type LeadResponse = {
  ok: boolean
  download_url: string
  asset_name: string
}

export default function EmailGateModal({ open, onClose, asset }: Props) {
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  useEffect(() => {
    if (open) {
      setEmail('')
      setName('')
      setError(null)
      setDone(false)
      setSubmitting(false)
    }
  }, [open, asset?.slug])

  if (!open || !asset) return null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.includes('@')) {
      setError('Enter a valid email.')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const res = await api.post<LeadResponse>('/resources/lead-capture', {
        email: email.trim(),
        name: name.trim() || undefined,
        asset_slug: asset.slug,
        source: 'resources_templates',
      })
      const a = document.createElement('a')
      a.href = res.download_url
      a.download = res.download_url.split('/').pop() ?? asset.slug
      document.body.appendChild(a)
      a.click()
      a.remove()
      setDone(true)
    } catch (err: any) {
      setError(err?.message ?? 'Something went wrong. Try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center px-4"
      style={{ backgroundColor: 'rgba(15, 15, 15, 0.55)' }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-2xl p-8 relative"
        style={{ backgroundColor: BG, border: `1px solid ${LINE}` }}
        onClick={e => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-1 transition-opacity hover:opacity-60"
          style={{ color: INK }}
          aria-label="Close"
        >
          <X className="w-5 h-5" />
        </button>

        {done ? (
          <div className="text-center py-4">
            <h3 className="text-2xl mb-3" style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}>
              Download started
            </h3>
            <p className="text-sm mb-6" style={{ color: MUTED }}>
              Check your downloads folder for <strong style={{ color: INK }}>{asset.name}</strong>.
              We'll send occasional updates on new HR resources — unsubscribe anytime.
            </p>
            <button
              onClick={onClose}
              className="px-5 h-10 rounded-full text-sm font-medium"
              style={{ backgroundColor: INK, color: BG }}
            >
              Browse more templates
            </button>
          </div>
        ) : (
          <>
            <h3 className="text-2xl mb-2" style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}>
              Get {asset.name}
            </h3>
            <p className="text-sm mb-6" style={{ color: MUTED }}>
              Enter your email and we'll send the file straight to your downloads.
              No spam — just occasional HR resources.
            </p>

            <form onSubmit={handleSubmit} className="flex flex-col gap-3">
              <input
                type="email"
                placeholder="you@company.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                autoFocus
                className="px-4 h-11 rounded-lg text-sm outline-none"
                style={{
                  backgroundColor: 'transparent',
                  border: `1px solid ${LINE}`,
                  color: INK,
                }}
              />
              <input
                type="text"
                placeholder="Name (optional)"
                value={name}
                onChange={e => setName(e.target.value)}
                className="px-4 h-11 rounded-lg text-sm outline-none"
                style={{
                  backgroundColor: 'transparent',
                  border: `1px solid ${LINE}`,
                  color: INK,
                }}
              />
              {error && (
                <p className="text-sm" style={{ color: '#c1543a' }}>{error}</p>
              )}
              <button
                type="submit"
                disabled={submitting}
                className="mt-2 h-11 rounded-full text-sm font-medium transition-opacity disabled:opacity-50"
                style={{ backgroundColor: INK, color: BG }}
              >
                {submitting ? 'Sending…' : 'Download'}
              </button>
              <p className="text-xs mt-2" style={{ color: MUTED }}>
                By downloading you agree to receive resource emails from Matcha.
              </p>
            </form>
          </>
        )}
      </div>
    </div>
  )
}
