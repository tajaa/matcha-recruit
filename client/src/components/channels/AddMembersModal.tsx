import { useState, useRef, useEffect } from 'react'
import { X, Search, Loader2, UserPlus, Check } from 'lucide-react'
import { searchInvitableUsers, addChannelMembers } from '../../api/channels'

interface Props {
  channelId: string
  channelName: string
  existingMemberIds: string[]
  onClose: () => void
  onAdded: () => void
}

export default function AddMembersModal({ channelId, channelName, existingMemberIds, onClose, onAdded }: Props) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<{ id: string; name: string; email: string; role: string }[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [searching, setSearching] = useState(false)
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState('')
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Auto-load contacts on mount
  useEffect(() => {
    setSearching(true)
    searchInvitableUsers('', channelId)
      .then((data) => setResults(data.filter((u) => !existingMemberIds.includes(u.id))))
      .catch(() => {})
      .finally(() => setSearching(false))
  }, [channelId, existingMemberIds])

  function handleSearch(q: string) {
    setQuery(q)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(async () => {
      setSearching(true)
      try {
        const data = await searchInvitableUsers(q, channelId)
        setResults(data.filter((u) => !existingMemberIds.includes(u.id)))
      } catch { setResults([]) }
      finally { setSearching(false) }
    }, 300)
  }

  function toggleUser(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function handleAdd() {
    if (selected.size === 0) return
    setAdding(true)
    setError('')
    try {
      await addChannelMembers(channelId, Array.from(selected))
      onAdded()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add members')
    } finally {
      setAdding(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 w-full max-w-md mx-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <UserPlus size={18} className="text-emerald-500" />
            <h2 className="text-white font-semibold">Add to #{channelName}</h2>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-white">
            <X size={16} />
          </button>
        </div>

        <div className="relative mb-3">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input
            type="text"
            value={query}
            onChange={(e) => handleSearch(e.target.value)}
            placeholder="Search by name or email..."
            autoFocus
            className="w-full pl-8 pr-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm placeholder:text-zinc-500 focus:outline-none focus:border-emerald-600"
          />
          {searching && <Loader2 size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 animate-spin" />}
        </div>

        <div className="max-h-48 overflow-y-auto space-y-1 mb-3">
          {results.length === 0 && !searching && (
            <p className="text-zinc-500 text-xs py-2 text-center">No users found</p>
          )}
          {results.map((u) => (
            <button
              key={u.id}
              onClick={() => toggleUser(u.id)}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-colors ${
                selected.has(u.id) ? 'bg-emerald-900/30 border border-emerald-700' : 'hover:bg-zinc-800 border border-transparent'
              }`}
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm text-white truncate">{u.name}</p>
                <p className="text-xs text-zinc-500 truncate">{u.email}</p>
              </div>
              {selected.has(u.id) && <Check size={14} className="text-emerald-400 shrink-0" />}
            </button>
          ))}
        </div>

        {selected.size > 0 && (
          <p className="text-xs text-zinc-400 mb-2">{selected.size} user{selected.size !== 1 ? 's' : ''} selected</p>
        )}

        {error && <p className="text-red-400 text-xs mb-2">{error}</p>}

        <button
          onClick={handleAdd}
          disabled={adding || selected.size === 0}
          className="w-full py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
        >
          {adding ? <Loader2 size={16} className="animate-spin mx-auto" /> : `Add ${selected.size || ''} Member${selected.size !== 1 ? 's' : ''}`}
        </button>
      </div>
    </div>
  )
}
