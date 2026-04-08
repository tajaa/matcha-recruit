import { useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { CheckCircle, Loader2, ArrowLeft } from 'lucide-react'

const API = import.meta.env.VITE_API_URL ?? '/api'

export default function Subscribe() {
  const [params] = useSearchParams()
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!email.trim()) return
    setSubmitting(true)
    setError('')
    try {
      const res = await fetch(`${API}/newsletter/subscribe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: email.trim(),
          name: name.trim() || undefined,
          source: params.get('utm_source') || 'website',
          utm_source: params.get('utm_source') || undefined,
          utm_medium: params.get('utm_medium') || undefined,
          utm_campaign: params.get('utm_campaign') || undefined,
        }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || 'Failed to subscribe')
      }
      setDone(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#1e1e1e] flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <Link to="/" className="inline-block">
            <span className="text-2xl font-bold text-[#ce9178]">Matcha</span>
          </Link>
        </div>

        {done ? (
          <div className="text-center space-y-4">
            <CheckCircle size={48} className="mx-auto text-emerald-500" />
            <h1 className="text-xl font-semibold text-[#e4e4e7]">You're subscribed!</h1>
            <p className="text-sm text-[#9ca3af]">
              You'll receive HR insights, compliance updates, and industry news straight to your inbox.
            </p>
            <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-[#569cd6] hover:underline mt-4">
              <ArrowLeft size={14} />
              Back to Matcha
            </Link>
          </div>
        ) : (
          <>
            <h1 className="text-xl font-semibold text-[#e4e4e7] text-center mb-2">
              Stay ahead of HR compliance
            </h1>
            <p className="text-sm text-[#9ca3af] text-center mb-8">
              Get actionable HR insights, regulatory updates, and compliance tips delivered weekly.
            </p>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Your email address"
                  required
                  autoFocus
                  className="w-full px-4 py-3 rounded-lg border border-[#333] bg-[#252526] text-[#e4e4e7] text-sm placeholder-[#6a737d] outline-none focus:border-[#ce9178] transition-colors"
                />
              </div>
              <div>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Your name (optional)"
                  className="w-full px-4 py-3 rounded-lg border border-[#333] bg-[#252526] text-[#e4e4e7] text-sm placeholder-[#6a737d] outline-none focus:border-[#ce9178] transition-colors"
                />
              </div>
              {error && <p className="text-sm text-red-400">{error}</p>}
              <button
                type="submit"
                disabled={submitting || !email.trim()}
                className="w-full py-3 rounded-lg bg-[#ce9178] hover:bg-[#d7a189] text-white font-medium text-sm transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {submitting ? <Loader2 size={16} className="animate-spin" /> : null}
                {submitting ? 'Subscribing...' : 'Subscribe'}
              </button>
            </form>

            <p className="text-[11px] text-[#6a737d] text-center mt-4">
              No spam. Unsubscribe anytime.
            </p>
          </>
        )}
      </div>
    </div>
  )
}
