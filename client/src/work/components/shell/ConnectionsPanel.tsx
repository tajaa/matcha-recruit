import { useEffect, useState, useCallback } from 'react'
import { Users, UserPlus, UserCheck, UserX, Search, X, Shield } from 'lucide-react'
import {
  listConnections,
  listPendingConnections,
  listSentConnections,
  sendConnectionRequest,
  acceptConnection,
  declineConnection,
  blockConnection,
  searchInvitableUsers,
} from '../../api/channels'
import type { UserConnection } from '../../api/channels'

type Tab = 'connections' | 'pending' | 'find'

interface SearchResult {
  id: string
  name: string
  email: string
  role: string
  avatar_url: string | null
}

export default function ConnectionsPanel() {
  const [tab, setTab] = useState<Tab>('connections')
  const [connections, setConnections] = useState<UserConnection[]>([])
  const [pending, setPending] = useState<UserConnection[]>([])
  const [sent, setSent] = useState<UserConnection[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<SearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [loading, setLoading] = useState(true)
  const [sentRequests, setSentRequests] = useState<Set<string>>(new Set())

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const [conn, pend, s] = await Promise.all([listConnections(), listPendingConnections(), listSentConnections()])
      setConnections(conn)
      setPending(pend)
      setSent(s)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    if (tab !== 'find' || searchQuery.length < 2) {
      setSearchResults([])
      return
    }
    const timeout = setTimeout(async () => {
      setSearching(true)
      try {
        const results = await searchInvitableUsers(searchQuery)
        // Filter out already-connected users
        const connectedIds = new Set(connections.map((c) => c.user_id))
        const pendingIds = new Set(pending.map((p) => p.user_id))
        const sentIds = new Set(sent.map((s) => s.user_id))
        setSearchResults(
          results.filter((r) => !connectedIds.has(r.id) && !pendingIds.has(r.id) && !sentIds.has(r.id))
        )
      } catch {
        // ignore
      } finally {
        setSearching(false)
      }
    }, 300)
    return () => clearTimeout(timeout)
  }, [searchQuery, tab, connections, pending, sent])

  async function handleAccept(userId: string) {
    try {
      await acceptConnection(userId)
      await refresh()
    } catch {
      // ignore
    }
  }

  async function handleDecline(userId: string) {
    try {
      await declineConnection(userId)
      setPending((prev) => prev.filter((p) => p.user_id !== userId))
    } catch {
      // ignore
    }
  }

  async function handleRemove(userId: string) {
    try {
      await declineConnection(userId)
      setConnections((prev) => prev.filter((c) => c.user_id !== userId))
    } catch {
      // ignore
    }
  }

  async function handleBlock(userId: string) {
    try {
      await blockConnection(userId)
      setConnections((prev) => prev.filter((c) => c.user_id !== userId))
      setPending((prev) => prev.filter((p) => p.user_id !== userId))
    } catch {
      // ignore
    }
  }

  async function handleConnect(userId: string) {
    try {
      const match = searchResults.find((r) => r.id === userId)
      const res = await sendConnectionRequest(userId)
      if (res.status === 'accepted') {
        await refresh()
      } else {
        setSentRequests((prev) => new Set(prev).add(userId))
        if (match) {
          setSent((prev) => [...prev, { user_id: match.id, name: match.name, email: match.email, avatar_url: match.avatar_url, created_at: new Date().toISOString() }])
        }
      }
      setSearchResults((prev) => prev.filter((r) => r.id !== userId))
    } catch {
      // ignore
    }
  }

  function Avatar({ name, url, size = 'md' }: { name: string; url: string | null; size?: 'sm' | 'md' }) {
    const dim = size === 'sm' ? 'w-8 h-8' : 'w-10 h-10'
    const textSize = size === 'sm' ? 'text-[11px]' : 'text-sm'
    if (url) {
      return <img src={url} alt={name} className={`${dim} rounded-full object-cover shrink-0`} />
    }
    return (
      <div className={`${dim} rounded-full bg-w-surface2 flex items-center justify-center ${textSize} font-medium text-w-dim shrink-0`}>
        {name.charAt(0).toUpperCase()}
      </div>
    )
  }

  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: 'connections', label: 'Connections', count: connections.length || undefined },
    { key: 'pending', label: 'Pending', count: (pending.length + sent.length) || undefined },
    { key: 'find', label: 'Find People' },
  ]

  return (
    <div className="flex-1 flex flex-col bg-w-surface min-h-0">
      {/* Header */}
      <div className="px-6 pt-6 pb-4 border-b border-w-line">
        <div className="flex items-center gap-2 mb-4">
          <Users size={20} className="text-w-accent" />
          <h1 className="text-lg font-semibold text-white">People</h1>
        </div>

        {/* Tabs */}
        <div className="flex gap-1">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                tab === t.key
                  ? 'bg-w-surface2 text-white'
                  : 'text-w-dim hover:text-w-text hover:bg-w-surface2/50'
              }`}
            >
              {t.label}
              {t.count != null && t.count > 0 && (
                <span className={`ml-1.5 inline-flex items-center justify-center min-w-[18px] h-[18px] rounded-full text-[10px] font-bold ${
                  t.key === 'pending' ? 'bg-w-accent text-white' : 'bg-w-surface2 text-w-text'
                }`}>
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {tab === 'connections' && (
          <div className="space-y-2">
            {loading ? (
              <p className="text-w-dim text-sm">Loading...</p>
            ) : connections.length === 0 ? (
              <div className="text-center py-12">
                <Users size={32} className="mx-auto text-w-faint mb-3" />
                <p className="text-w-dim text-sm">No connections yet</p>
                <button
                  onClick={() => setTab('find')}
                  className="mt-3 text-w-accent text-sm hover:text-w-accent transition-colors"
                >
                  Find people to connect with
                </button>
              </div>
            ) : (
              connections.map((c) => (
                <div key={c.user_id} className="flex items-center gap-3 p-3 rounded-lg hover:bg-w-surface2/50 group transition-colors">
                  <Avatar name={c.name} url={c.avatar_url} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-w-text truncate">{c.name}</p>
                    <p className="text-xs text-w-dim truncate">{c.email}</p>
                  </div>
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={() => handleBlock(c.user_id)}
                      className="p-1.5 rounded text-w-faint hover:text-red-400 hover:bg-w-surface2 transition-colors"
                      title="Block"
                    >
                      <Shield size={14} />
                    </button>
                    <button
                      onClick={() => handleRemove(c.user_id)}
                      className="p-1.5 rounded text-w-faint hover:text-red-400 hover:bg-w-surface2 transition-colors"
                      title="Remove connection"
                    >
                      <X size={14} />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {tab === 'pending' && (
          <div className="space-y-4">
            {loading ? (
              <p className="text-w-dim text-sm">Loading...</p>
            ) : pending.length === 0 && sent.length === 0 ? (
              <div className="text-center py-12">
                <UserCheck size={32} className="mx-auto text-w-faint mb-3" />
                <p className="text-w-dim text-sm">No pending requests</p>
              </div>
            ) : (
              <>
                {pending.length > 0 && (
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-w-dim mb-2">Incoming Requests</p>
                    <div className="space-y-2">
                      {pending.map((p) => (
                        <div key={p.user_id} className="flex items-center gap-3 p-3 rounded-lg bg-w-surface2/30 transition-colors">
                          <Avatar name={p.name} url={p.avatar_url} />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-w-text truncate">{p.name}</p>
                            <p className="text-xs text-w-dim truncate">{p.email}</p>
                          </div>
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => handleAccept(p.user_id)}
                              className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-w-accent hover:bg-w-accent-hi text-white text-xs font-medium transition-colors"
                            >
                              <UserCheck size={13} />
                              Accept
                            </button>
                            <button
                              onClick={() => handleDecline(p.user_id)}
                              className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-w-surface2 hover:bg-w-faint text-w-text text-xs font-medium transition-colors"
                            >
                              <UserX size={13} />
                              Decline
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {sent.length > 0 && (
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-w-dim mb-2">Sent Requests</p>
                    <div className="space-y-2">
                      {sent.map((s) => (
                        <div key={s.user_id} className="flex items-center gap-3 p-3 rounded-lg bg-w-surface2/30 transition-colors">
                          <Avatar name={s.name} url={s.avatar_url} />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-w-text truncate">{s.name}</p>
                            <p className="text-xs text-w-dim truncate">{s.email}</p>
                          </div>
                          <span className="text-xs text-w-dim px-3 py-1.5">Awaiting response</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {tab === 'find' && (
          <div>
            <div className="relative mb-4">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-w-dim" />
              <input
                type="text"
                placeholder="Search by name or email..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-4 py-2.5 rounded-lg bg-w-surface2 border border-w-line text-sm text-w-text placeholder-w-faint outline-none focus:border-w-accent transition-colors"
                autoFocus
              />
            </div>

            {searchQuery.length < 2 && (
              <p className="text-w-dim text-sm text-center py-8">
                Type at least 2 characters to search
              </p>
            )}

            {searching && (
              <p className="text-w-dim text-sm text-center py-4">Searching...</p>
            )}

            {!searching && searchQuery.length >= 2 && searchResults.length === 0 && (
              <p className="text-w-dim text-sm text-center py-8">No results found</p>
            )}

            <div className="space-y-2">
              {searchResults.map((r) => (
                <div key={r.id} className="flex items-center gap-3 p-3 rounded-lg hover:bg-w-surface2/50 transition-colors">
                  <Avatar name={r.name} url={r.avatar_url} size="sm" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-w-text truncate">{r.name}</p>
                    <p className="text-xs text-w-dim truncate">{r.email}</p>
                  </div>
                  {sentRequests.has(r.id) ? (
                    <span className="text-xs text-w-dim px-3 py-1.5">Sent</span>
                  ) : (
                    <button
                      onClick={() => handleConnect(r.id)}
                      className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-w-accent/20 hover:bg-w-accent-hi/30 text-w-accent text-xs font-medium transition-colors"
                    >
                      <UserPlus size={13} />
                      Connect
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
