import { useState, useRef, useEffect, useCallback } from 'react'
import { Plus, Search, X, Crown } from 'lucide-react'
import {
  listThreadCollaborators,
  addThreadCollaborator,
  removeThreadCollaborator,
  searchThreadInvitableUsers,
} from '../../api/matchaWork'
import type { ThreadCollaborator } from '../../api/matchaWork'
import { useMe } from '../../hooks/useMe'

interface ThreadCollaboratorsProps {
  threadId: string
  onlineUsers: { id: string; name: string }[]
  lightMode: boolean
}

const AVATAR_COLORS = ['#ce9178', '#569cd6', '#b5cea8', '#dcdcaa', '#c586c0', '#4ec9b0', '#9cdcfe']

function avatarColor(userId: string): string {
  let hash = 0
  for (let i = 0; i < userId.length; i++) {
    hash = ((hash << 5) - hash + userId.charCodeAt(i)) | 0
  }
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length]
}

export default function ThreadCollaborators({ threadId, onlineUsers, lightMode }: ThreadCollaboratorsProps) {
  const { me } = useMe()
  const [collaborators, setCollaborators] = useState<ThreadCollaborator[]>([])
  const [showSearch, setShowSearch] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<{ id: string; name: string; email: string; avatar_url: string | null }[]>([])
  const [searching, setSearching] = useState(false)
  const [contextMenu, setContextMenu] = useState<{ userId: string; x: number; y: number } | null>(null)
  const searchTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const onlineSet = new Set(onlineUsers.map((u) => u.id))
  const currentUserRole = collaborators.find((c) => c.user_id === me?.user?.id)?.role
  const isOwner = currentUserRole === 'owner'

  useEffect(() => {
    listThreadCollaborators(threadId)
      .then(setCollaborators)
      .catch(() => {})
  }, [threadId])

  // Close dropdown on outside click
  useEffect(() => {
    if (!showSearch && !contextMenu) return
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowSearch(false)
        setContextMenu(null)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [showSearch, contextMenu])

  const handleSearch = useCallback((q: string) => {
    setSearchQuery(q)
    if (searchTimeout.current) clearTimeout(searchTimeout.current)
    if (q.length < 2) {
      setSearchResults([])
      return
    }
    setSearching(true)
    searchTimeout.current = setTimeout(async () => {
      try {
        const results = await searchThreadInvitableUsers(q)
        const existingIds = new Set(collaborators.map((c) => c.user_id))
        setSearchResults(results.filter((r) => !existingIds.has(r.id)))
      } catch {
        setSearchResults([])
      }
      setSearching(false)
    }, 300)
  }, [collaborators])

  async function handleAdd(userId: string) {
    try {
      await addThreadCollaborator(threadId, userId)
      const updated = await listThreadCollaborators(threadId)
      setCollaborators(updated)
      setSearchResults((prev) => prev.filter((r) => r.id !== userId))
      setSearchQuery('')
    } catch (err: unknown) {
      console.error('Failed to add collaborator', err)
    }
  }

  async function handleRemove(userId: string) {
    try {
      await removeThreadCollaborator(threadId, userId)
      const updated = await listThreadCollaborators(threadId)
      setCollaborators(updated)
      setContextMenu(null)
    } catch (err: unknown) {
      console.error('Failed to remove collaborator', err)
    }
  }

  const bg = lightMode ? 'bg-zinc-100' : 'bg-zinc-800'
  const dropdownBg = lightMode ? 'bg-white border-zinc-200' : 'bg-zinc-800 border-zinc-700'
  const textPrimary = lightMode ? 'text-zinc-800' : 'text-zinc-200'
  const textSecondary = lightMode ? 'text-zinc-500' : 'text-zinc-400'
  const hoverBg = lightMode ? 'hover:bg-zinc-100' : 'hover:bg-zinc-700'

  return (
    <div className="relative flex items-center gap-1" ref={dropdownRef}>
      {/* Avatar row */}
      <div className="flex items-center -space-x-1.5">
        {collaborators.map((c) => (
          <div
            key={c.user_id}
            className="relative shrink-0"
            title={`${c.name}${c.role === 'owner' ? ' (owner)' : ''}`}
            onContextMenu={(e) => {
              if (!isOwner || c.role === 'owner') return
              e.preventDefault()
              setContextMenu({ userId: c.user_id, x: e.clientX, y: e.clientY })
            }}
          >
            {c.avatar_url ? (
              <img
                src={c.avatar_url}
                alt={c.name}
                className="w-7 h-7 rounded-full border-2"
                style={{ borderColor: lightMode ? '#f4f4f5' : '#27272a' }}
              />
            ) : (
              <div
                className="w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-semibold text-white border-2"
                style={{ background: avatarColor(c.user_id), borderColor: lightMode ? '#f4f4f5' : '#27272a' }}
              >
                {c.name.charAt(0).toUpperCase()}
              </div>
            )}
            {/* Online indicator */}
            {onlineSet.has(c.user_id) && (
              <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-emerald-500 border-2" style={{ borderColor: lightMode ? '#f4f4f5' : '#27272a' }} />
            )}
            {/* Owner crown */}
            {c.role === 'owner' && (
              <span className="absolute -top-1 -right-1">
                <Crown size={8} className="text-amber-400" />
              </span>
            )}
          </div>
        ))}
      </div>

      {/* Add button */}
      {isOwner && (
        <button
          onClick={() => setShowSearch(!showSearch)}
          className={`w-7 h-7 rounded-full flex items-center justify-center transition-colors ${
            lightMode
              ? 'bg-zinc-200 hover:bg-zinc-300 text-zinc-500'
              : 'bg-zinc-700 hover:bg-zinc-600 text-zinc-400'
          }`}
          title="Add collaborator"
        >
          <Plus size={12} />
        </button>
      )}

      {/* Search dropdown */}
      {showSearch && (
        <div className={`absolute top-full left-0 mt-1 z-50 w-64 rounded-lg shadow-xl border ${dropdownBg}`}>
          <div className="p-2">
            <div className={`flex items-center gap-2 px-2 py-1.5 rounded ${bg}`}>
              <Search size={12} className={textSecondary} />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => handleSearch(e.target.value)}
                placeholder="Search by name or email..."
                className={`bg-transparent text-xs ${textPrimary} outline-none w-full placeholder:${textSecondary}`}
                autoFocus
              />
            </div>
          </div>

          {(searchResults.length > 0 || searching) && (
            <div className="px-2 pb-2 max-h-40 overflow-y-auto">
              {searching && <div className={`text-[10px] ${textSecondary} px-1 py-1`}>Searching...</div>}
              {searchResults.map((user) => (
                <button
                  key={user.id}
                  onClick={() => handleAdd(user.id)}
                  className={`flex items-center gap-2 w-full px-2 py-1.5 rounded text-left ${hoverBg} transition-colors`}
                >
                  {user.avatar_url ? (
                    <img src={user.avatar_url} alt={user.name} className="w-5 h-5 rounded-full shrink-0" />
                  ) : (
                    <div
                      className="w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-medium text-white shrink-0"
                      style={{ background: avatarColor(user.id) }}
                    >
                      {user.name.charAt(0).toUpperCase()}
                    </div>
                  )}
                  <div className="min-w-0">
                    <div className={`text-[11px] ${textPrimary} truncate`}>{user.name}</div>
                    <div className={`text-[9px] ${textSecondary} truncate`}>{user.email}</div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Context menu for remove */}
      {contextMenu && (
        <div
          className={`fixed z-[100] rounded-lg shadow-xl border ${dropdownBg} py-1`}
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          <button
            onClick={() => handleRemove(contextMenu.userId)}
            className={`flex items-center gap-2 px-3 py-1.5 text-xs text-red-400 hover:bg-red-500/10 w-full text-left transition-colors`}
          >
            <X size={12} />
            Remove collaborator
          </button>
        </div>
      )}
    </div>
  )
}
