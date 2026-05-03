import { useState, useEffect, useMemo, lazy, Suspense } from 'react'
import { useNavigate } from 'react-router-dom'
import { Hash, Search, Users, Lock, Loader2, LogIn, Crown } from 'lucide-react'
import { listChannels, discoverChannels, joinChannel, createChannelCheckout } from '../../api/channels'
import type { ChannelSummary } from '../../api/channels'
import { useMe } from '../../hooks/useMe'

const CreateChannelModal = lazy(() => import('../../components/channels/CreateChannelModal'))

type Tab = 'all' | 'free' | 'paid' | 'mine' | 'discover'

function formatPrice(cents: number | null | undefined, _currency?: string): string {
  if (!cents) return ''
  return `$${(cents / 100).toFixed(2)}/mo`
}

export default function ChannelBrowse() {
  const navigate = useNavigate()
  const { me } = useMe()
  const [channels, setChannels] = useState<ChannelSummary[]>([])
  const [discoverList, setDiscoverList] = useState<ChannelSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [discoverLoading, setDiscoverLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [tab, setTab] = useState<Tab>('all')
  const [showCreate, setShowCreate] = useState(false)
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  useEffect(() => {
    listChannels()
      .then(setChannels)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (tab !== 'discover') return
    setDiscoverLoading(true)
    discoverChannels({ q: search || undefined })
      .then(setDiscoverList)
      .catch(() => {})
      .finally(() => setDiscoverLoading(false))
  }, [tab, search])

  const canCreate = me?.user?.role === 'client' || me?.user?.role === 'admin' || me?.user?.role === 'individual'

  const filtered = useMemo(() => {
    if (tab === 'discover') return discoverList  // server-side filtered
    let list = channels
    if (tab === 'free') list = list.filter((ch) => !ch.is_paid)
    else if (tab === 'paid') list = list.filter((ch) => ch.is_paid)
    else if (tab === 'mine') list = list.filter((ch) => ch.is_member)

    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter(
        (ch) =>
          ch.name.toLowerCase().includes(q) ||
          (ch.description && ch.description.toLowerCase().includes(q)),
      )
    }
    return list
  }, [channels, discoverList, tab, search])

  async function handleJoin(ch: ChannelSummary) {
    setActionLoading(ch.id)
    try {
      await joinChannel(ch.id)
      navigate(`/work/channels/${ch.id}`)
    } catch {
      setActionLoading(null)
    }
  }

  async function handleSubscribe(ch: ChannelSummary) {
    setActionLoading(ch.id)
    try {
      const { checkout_url } = await createChannelCheckout(ch.id)
      window.location.href = checkout_url
    } catch {
      setActionLoading(null)
    }
  }

  const tabs: { key: Tab; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'free', label: 'Free' },
    { key: 'paid', label: 'Paid' },
    { key: 'mine', label: 'My Channels' },
    { key: 'discover', label: 'Discover' },
  ]

  return (
    <div className="min-h-screen bg-zinc-950 px-4 py-8 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-6xl">
        {/* Header */}
        <div className="mb-8 flex items-center justify-between">
          <h1 className="text-2xl font-bold text-white">Channels</h1>
          {canCreate && (
            <button
              onClick={() => setShowCreate(true)}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 transition-colors"
            >
              Create Channel
            </button>
          )}
        </div>

        {/* Search */}
        <div className="relative mb-6">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
          <input
            type="text"
            placeholder="Search channels..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border border-zinc-800 bg-zinc-900 py-2.5 pl-10 pr-4 text-sm text-zinc-300 placeholder-zinc-500 outline-none focus:border-zinc-700 transition-colors"
          />
        </div>

        {/* Tabs */}
        <div className="mb-6 flex gap-1 rounded-lg bg-zinc-900 p-1">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                tab === t.key
                  ? 'bg-zinc-800 text-white'
                  : 'text-zinc-400 hover:text-zinc-300'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Content */}
        {tab === 'discover' && discoverLoading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="h-6 w-6 animate-spin text-zinc-500" />
          </div>
        ) : loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="h-6 w-6 animate-spin text-zinc-500" />
          </div>
        ) : channels.length === 0 ? (
          <div className="py-20 text-center text-zinc-500">No channels yet</div>
        ) : filtered.length === 0 ? (
          <div className="py-20 text-center text-zinc-500">No channels found</div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((ch) => {
              const isLoading = actionLoading === ch.id
              const price = formatPrice(ch.price_cents, ch.currency)

              return (
                <div
                  key={ch.id}
                  onClick={() => {
                    if (ch.is_member) navigate(`/work/channels/${ch.id}`)
                  }}
                  className="cursor-pointer rounded-xl border border-zinc-800 bg-zinc-900 p-4 hover:border-zinc-700 transition-colors"
                >
                  {/* Top row */}
                  <div className="mb-2 flex items-center gap-2">
                    <Hash className="h-4 w-4 flex-shrink-0 text-emerald-500" />
                    <span className="truncate font-semibold text-white">{ch.name}</span>
                    {ch.visibility === 'private' && (
                      <Lock className="h-3.5 w-3.5 flex-shrink-0 text-zinc-500" />
                    )}
                    {ch.is_paid && price && (
                      <span className="ml-auto flex-shrink-0 rounded-full bg-emerald-600/20 px-2 py-0.5 text-xs text-emerald-400">
                        {price}
                      </span>
                    )}
                  </div>

                  {/* Description */}
                  {ch.description && (
                    <p className="mb-3 line-clamp-2 text-sm text-zinc-400">{ch.description}</p>
                  )}
                  {!ch.description && <div className="mb-3" />}

                  {/* Bottom row */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3 text-xs text-zinc-500">
                      <span className="flex items-center gap-1">
                        <Users className="h-3.5 w-3.5" />
                        {ch.member_count}
                      </span>
                      {ch.unread_count > 0 && (
                        <span className="rounded-full bg-emerald-600 px-1.5 py-0.5 text-[10px] font-medium text-white">
                          {ch.unread_count}
                        </span>
                      )}
                    </div>

                    {/* Action button */}
                    {ch.is_member ? (
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          navigate(`/work/channels/${ch.id}`)
                        }}
                        className="rounded-lg bg-zinc-800 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-700 transition-colors"
                      >
                        Open
                      </button>
                    ) : ch.is_paid ? (
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          handleSubscribe(ch)
                        }}
                        disabled={isLoading}
                        className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 transition-colors disabled:opacity-50"
                      >
                        {isLoading ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <>
                            <Crown className="h-3.5 w-3.5" />
                            Subscribe{price ? ` \u00b7 ${price}` : ''}
                          </>
                        )}
                      </button>
                    ) : (
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          handleJoin(ch)
                        }}
                        disabled={isLoading}
                        className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 transition-colors disabled:opacity-50"
                      >
                        {isLoading ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <>
                            <LogIn className="h-3.5 w-3.5" />
                            Join
                          </>
                        )}
                      </button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Create Channel Modal */}
      {showCreate && (
        <Suspense fallback={null}>
          <CreateChannelModal
            onClose={() => setShowCreate(false)}
            canCreatePaid={me?.user?.role === 'individual' || me?.user?.role === 'admin'}
            onCreated={(ch) => {
              setShowCreate(false)
              navigate(`/work/channels/${ch.id}`)
            }}
          />
        </Suspense>
      )}
    </div>
  )
}
