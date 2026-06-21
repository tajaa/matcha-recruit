import { useEffect, useRef, useState } from 'react'
import { Users, Plus, Loader2, Copy, Check, Trash2, Building2 } from 'lucide-react'
import { HelpHint } from '../../components/broker/HelpHint'
import { fetchBrokerSeats, createClientInvite, revokeClientInvite } from '../../api/broker'
import type { BrokerClientInvite, BrokerSeatsResponse, ClientInviteTier } from '../../types/broker'

function fmtDate(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function CopyButton({ url }: { url: string }) {
  const [copied, setCopied] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current) }, [])
  function handleCopy() {
    navigator.clipboard.writeText(url)
    setCopied(true)
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => setCopied(false), 2000)
  }
  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg border border-zinc-700 text-zinc-400 hover:border-zinc-500 hover:text-zinc-200 transition-colors"
    >
      {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
      {copied ? 'Copied!' : 'Copy link'}
    </button>
  )
}

const STATUS_TONE: Record<string, { bg: string; text: string; label: string }> = {
  outstanding: { bg: '#27272a', text: '#a1a1aa', label: 'Link sent' },
  redeemed: { bg: 'rgba(21,128,61,0.15)', text: '#4ade80', label: 'Signed up' },
  revoked: { bg: 'rgba(127,29,29,0.15)', text: '#f87171', label: 'Revoked' },
}

const inputCls = 'px-3 h-9 rounded-lg text-sm bg-zinc-900/60 border border-zinc-700 text-zinc-100 placeholder-zinc-500 outline-none focus:border-zinc-500 focus:ring-1 focus:ring-zinc-600/50 transition-colors'

export default function BrokerClientSeats({ embedded = false }: { embedded?: boolean }) {
  const [data, setData] = useState<BrokerSeatsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [companyName, setCompanyName] = useState('')
  const [seatCount, setSeatCount] = useState('')
  const [tier, setTier] = useState<ClientInviteTier>('matcha_lite')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  async function load() {
    try {
      setData(await fetchBrokerSeats())
    } catch {
      setError('Failed to load seats')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    const seats = parseInt(seatCount, 10)
    if (!companyName.trim() || isNaN(seats) || seats < 1) return
    setCreating(true)
    setCreateError(null)
    try {
      await createClientInvite({ company_name: companyName.trim(), seat_count: seats, tier })
      setCompanyName('')
      setSeatCount('')
      setTier('matcha_lite')
      await load()
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Failed to create signup link')
    } finally {
      setCreating(false)
    }
  }

  async function handleRevoke(invite: BrokerClientInvite) {
    try {
      await revokeClientInvite(invite.id)
      await load()
    } catch {
      load()
    }
  }

  const allocated = data?.allocated ?? 0
  const committed = data?.committed ?? 0
  const remaining = data?.remaining ?? 0
  const pct = allocated > 0 ? Math.min(100, Math.round((committed / allocated) * 100)) : 0
  const seats = parseInt(seatCount, 10)
  const seatsValid = !isNaN(seats) && seats >= 1
  const overRemaining = seatsValid && seats > remaining

  return (
    <div>
      {!embedded && (
        <div className="mb-6">
          <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight text-zinc-100">Client Seats <HelpHint text="Your seat pool — licenses allocated to you, used, and remaining. Issue company-pinned invites that draw from it; the client signs up with seats pre-set, no Stripe checkout." /></h1>
          <p className="mt-1 text-sm text-zinc-500">
            Apportion your seat allocation across your book. Each client gets a ready-to-send signup
            link with their company name and seats pre-set — no Stripe checkout.
          </p>
        </div>
      )}

      {/* Pool meter */}
      <div className="mb-6 max-w-3xl p-5 rounded-2xl border border-zinc-800 bg-zinc-900/40">
        <div className="flex items-end justify-between mb-3">
          <div className="flex gap-6">
            <div>
              <div className="text-2xl font-light font-mono text-zinc-100">{allocated}</div>
              <div className="text-[10px] uppercase tracking-widest text-zinc-600 font-bold">Allocated</div>
            </div>
            <div>
              <div className="text-2xl font-light font-mono text-amber-400">{committed}</div>
              <div className="text-[10px] uppercase tracking-widest text-zinc-600 font-bold">Apportioned</div>
            </div>
            <div>
              <div className="text-2xl font-light font-mono text-emerald-400">{remaining}</div>
              <div className="text-[10px] uppercase tracking-widest text-zinc-600 font-bold">Remaining</div>
            </div>
          </div>
        </div>
        <div className="h-2 rounded-full bg-zinc-800 overflow-hidden">
          <div className="h-full bg-emerald-600 transition-all" style={{ width: `${pct}%` }} />
        </div>
        {allocated === 0 && (
          <p className="mt-3 text-xs text-zinc-500">
            No seats allocated yet — contact your Matcha account manager to set your allocation.
          </p>
        )}
      </div>

      {/* Create form */}
      <form onSubmit={handleCreate} className="mb-6 flex max-w-3xl flex-col gap-4 rounded-2xl border border-zinc-800 bg-zinc-900/40 p-5">
        <p className="text-[11px] font-bold uppercase tracking-widest text-zinc-500">New client signup link</p>
        <div className="flex gap-3 flex-wrap">
          <input
            type="text"
            placeholder="Client company name"
            value={companyName}
            onChange={e => setCompanyName(e.target.value)}
            className={`flex-1 min-w-0 ${inputCls}`}
          />
          <input
            type="number"
            placeholder="Seats"
            min={1}
            value={seatCount}
            onChange={e => setSeatCount(e.target.value)}
            className={`w-28 ${inputCls}`}
          />
          <button
            type="submit"
            disabled={creating || !companyName.trim() || !seatsValid || overRemaining || allocated === 0}
            className="flex items-center gap-2 px-4 h-9 rounded-lg text-sm font-medium bg-emerald-700 text-white hover:bg-emerald-600 disabled:opacity-50 transition-colors"
          >
            {creating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
            Create link
          </button>
        </div>
        <div className="flex flex-col gap-1.5">
          <p className="text-xs text-zinc-500">Product</p>
          <div className="flex gap-2">
            {(['matcha_lite', 'matcha_x'] as const).map(t => (
              <button
                key={t}
                type="button"
                onClick={() => setTier(t)}
                className="px-3 h-8 rounded-lg text-xs font-medium transition-colors"
                style={tier === t
                  ? { backgroundColor: '#15803d', color: '#fff' }
                  : { backgroundColor: 'transparent', border: '1px solid #3f3f46', color: '#71717a' }
                }
              >
                {t === 'matcha_lite' ? 'Matcha Lite' : 'Matcha-X'}
              </button>
            ))}
          </div>
        </div>
        {overRemaining && (
          <p className="text-xs text-amber-400">Only {remaining} seats remaining in your pool.</p>
        )}
        {createError && <p className="text-xs text-red-400">{createError}</p>}
      </form>

      {/* Client list */}
      {loading ? (
        <div className="flex items-center gap-2 text-sm text-zinc-500">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading…
        </div>
      ) : error ? (
        <p className="text-sm text-red-400">{error}</p>
      ) : !data || data.clients.length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-16 text-zinc-500">
          <Users className="w-8 h-8 opacity-30" />
          <p className="text-sm">No client links yet. Create one above to start onboarding your book.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {data.clients.map(c => {
            const tone = STATUS_TONE[c.status] ?? STATUS_TONE.outstanding
            const redeemed = c.status === 'redeemed'
            return (
              <div key={c.id} className="p-4 border border-zinc-800 rounded-xl flex flex-col gap-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex flex-col gap-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <Building2 className="w-3.5 h-3.5 text-zinc-500 shrink-0" />
                      <p className="text-sm font-medium text-zinc-200 truncate">
                        {c.redeemed_company_name || c.company_name || 'Unnamed'}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span
                        className="shrink-0 text-[10px] px-1.5 py-0.5 rounded font-medium"
                        style={{ backgroundColor: tone.bg, color: tone.text }}
                      >
                        {tone.label}
                      </span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded font-medium bg-zinc-800 text-zinc-400">
                        {c.tier === 'matcha_x' ? 'Matcha-X' : 'Lite'}
                      </span>
                    </div>
                  </div>
                  {!redeemed && (
                    <button
                      onClick={() => handleRevoke(c)}
                      className="p-1.5 rounded-lg text-zinc-600 hover:text-red-400 hover:bg-zinc-800 transition-colors shrink-0"
                      title="Revoke link (frees seats)"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>

                <div className="flex items-center gap-3 text-xs text-zinc-400">
                  <span className="text-zinc-200 font-medium">{c.seat_count} seats</span>
                  {redeemed && (
                    <span>{c.employees_used ?? 0} / {c.seat_count} used</span>
                  )}
                </div>

                {!redeemed ? (
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[11px] text-zinc-600 truncate">{c.signup_url}</span>
                    <CopyButton url={c.signup_url} />
                  </div>
                ) : (
                  <p className="text-[11px] text-zinc-600">Activated {fmtDate(c.created_at)}</p>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
