import { useEffect, useState, useRef } from 'react'
import { Link2, Plus, Loader2, Copy, Check, Trash2 } from 'lucide-react'
import { fetchLiteReferralTokens, createLiteReferralToken, deactivateLiteReferralToken } from '../../api/broker'
import type { BrokerLiteReferralToken } from '../../types/broker'

function fmtDate(iso: string | null) {
  if (!iso) return 'Never'
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function CopyButton({ url }: { url: string }) {
  const [copied, setCopied] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  function handleCopy() {
    navigator.clipboard.writeText(url)
    setCopied(true)
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => setCopied(false), 2000)
  }

  useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current) }, [])

  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg border border-zinc-700 text-zinc-400 hover:border-zinc-500 hover:text-zinc-200 transition-colors"
    >
      {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
      {copied ? 'Copied!' : 'Copy'}
    </button>
  )
}

export default function BrokerReferralLinks() {
  const [tokens, setTokens] = useState<BrokerLiteReferralToken[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [label, setLabel] = useState('')
  const [expiresDays, setExpiresDays] = useState('')
  const [payer, setPayer] = useState<'business' | 'broker'>('business')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  async function load() {
    try {
      const data = await fetchLiteReferralTokens()
      setTokens(data.tokens)
    } catch {
      setError('Failed to load referral links')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setCreating(true)
    setCreateError(null)
    try {
      const days = expiresDays ? parseInt(expiresDays, 10) : undefined
      const token = await createLiteReferralToken(label.trim() || undefined, days, payer)
      setTokens(prev => [token, ...prev])
      setLabel('')
      setExpiresDays('')
      setPayer('business')
    } catch {
      setCreateError('Failed to generate link')
    } finally {
      setCreating(false)
    }
  }

  async function handleDeactivate(tokenId: string) {
    setTokens(prev => prev.filter(t => t.id !== tokenId))
    try {
      await deactivateLiteReferralToken(tokenId)
    } catch {
      load()
    }
  }

  return (
    <div className="max-w-3xl">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-zinc-100">Referral Links</h1>
        <p className="text-sm text-zinc-500 mt-1">
          Generate shareable Matcha Lite signup links. Companies that sign up via your link are automatically attributed to your account.
        </p>
      </div>

      <form onSubmit={handleCreate} className="mb-8 p-5 border border-zinc-800 rounded-xl flex flex-col gap-4">
        <p className="text-sm font-medium text-zinc-300">Generate new link</p>
        <div className="flex gap-3 flex-wrap">
          <input
            type="text"
            placeholder="Label (optional — e.g. 'Q2 Campaign')"
            value={label}
            onChange={e => setLabel(e.target.value)}
            className="flex-1 min-w-0 px-3 h-9 rounded-lg text-sm bg-transparent border border-zinc-700 text-zinc-100 placeholder-zinc-500 outline-none focus:border-zinc-500"
          />
          <input
            type="number"
            placeholder="Expires in days (optional)"
            min={1}
            value={expiresDays}
            onChange={e => setExpiresDays(e.target.value)}
            className="w-44 px-3 h-9 rounded-lg text-sm bg-transparent border border-zinc-700 text-zinc-100 placeholder-zinc-500 outline-none focus:border-zinc-500"
          />
          <button
            type="submit"
            disabled={creating}
            className="flex items-center gap-2 px-4 h-9 rounded-lg text-sm font-medium bg-zinc-700 text-zinc-100 hover:bg-zinc-600 disabled:opacity-50 transition-colors"
          >
            {creating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
            Generate
          </button>
        </div>
        <div className="flex flex-col gap-1.5">
          <p className="text-xs text-zinc-500">Who pays for Matcha Lite?</p>
          <div className="flex gap-2">
            {(['business', 'broker'] as const).map(p => (
              <button
                key={p}
                type="button"
                onClick={() => setPayer(p)}
                className="px-3 h-8 rounded-lg text-xs font-medium transition-colors"
                style={payer === p
                  ? { backgroundColor: p === 'broker' ? '#15803d' : '#3f3f46', color: '#fff' }
                  : { backgroundColor: 'transparent', border: '1px solid #3f3f46', color: '#71717a' }
                }
              >
                {p === 'business' ? 'Business pays' : 'Broker pays'}
              </button>
            ))}
          </div>
          {payer === 'broker' && (
            <p className="text-xs text-zinc-500">Customer skips Stripe checkout — billed to your broker contract.</p>
          )}
        </div>
        {createError && <p className="text-xs text-red-400">{createError}</p>}
      </form>

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-zinc-500">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading…
        </div>
      ) : error ? (
        <p className="text-sm text-red-400">{error}</p>
      ) : tokens.length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-16 text-zinc-500">
          <Link2 className="w-8 h-8 opacity-30" />
          <p className="text-sm">No referral links yet. Generate one above.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {tokens.map(t => (
            <div key={t.id} className="p-4 border border-zinc-800 rounded-xl flex flex-col gap-3">
              <div className="flex items-start justify-between gap-3">
                <div className="flex flex-col gap-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-zinc-200 truncate">
                      {t.label || <span className="text-zinc-500 italic">Unlabeled</span>}
                    </p>
                    <span
                      className="shrink-0 text-[10px] px-1.5 py-0.5 rounded font-medium"
                      style={t.payer === 'broker'
                        ? { backgroundColor: 'rgba(21,128,61,0.15)', color: '#4ade80' }
                        : { backgroundColor: '#27272a', color: '#71717a' }
                      }
                    >
                      {t.payer === 'broker' ? 'Broker pays' : 'Business pays'}
                    </span>
                  </div>
                  <p className="text-xs text-zinc-500 truncate">{t.referral_url}</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <CopyButton url={t.referral_url} />
                  <button
                    onClick={() => handleDeactivate(t.id)}
                    className="p-1.5 rounded-lg text-zinc-600 hover:text-red-400 hover:bg-zinc-800 transition-colors"
                    title="Deactivate"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
              <div className="flex items-center gap-4 text-xs text-zinc-500">
                <span>{t.use_count} {t.use_count === 1 ? 'signup' : 'signups'}</span>
                <span>Created {fmtDate(t.created_at)}</span>
                <span>Expires {fmtDate(t.expires_at)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
