import { useState, useRef, useEffect } from 'react'
import { X, Search, UserPlus, Crown, Users } from 'lucide-react'
import { listCollaborators, addCollaborator, removeCollaborator } from '../../api/matchaWork'
import { searchInvitableUsers } from '../../api/channels'
import type { ProjectCollaborator } from '../../types/matcha-work'

interface Props {
  projectId: string
  currentUserRole?: 'owner' | 'collaborator'
  onClose: () => void
}

export default function CollaboratorPanel({ projectId, currentUserRole, onClose }: Props) {
  const [collaborators, setCollaborators] = useState<ProjectCollaborator[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<{ user_id: string; name: string; email: string; avatar_url: string | null }[]>([])
  const [searching, setSearching] = useState(false)
  const [loading, setLoading] = useState(true)
  const searchTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    listCollaborators(projectId).then((data) => {
      setCollaborators(data)
      setLoading(false)
    })
  }, [projectId])

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [onClose])

  function handleSearch(q: string) {
    setSearchQuery(q)
    if (searchTimeout.current) clearTimeout(searchTimeout.current)
    if (q.length < 2) {
      setSearchResults([])
      return
    }
    setSearching(true)
    searchTimeout.current = setTimeout(async () => {
      try {
        const results = await searchInvitableUsers(q)
        const existingIds = new Set(collaborators.map((c) => c.user_id))
        setSearchResults(results.filter((r) => !existingIds.has(r.id)).map((r) => ({ user_id: r.id, name: r.name, email: r.email, avatar_url: r.avatar_url })))
      } catch {
        setSearchResults([])
      }
      setSearching(false)
    }, 300)
  }

  async function handleAdd(userId: string) {
    try {
      const updated = await addCollaborator(projectId, userId)
      setCollaborators(updated)
      setSearchResults((prev) => prev.filter((r) => r.user_id !== userId))
    } catch (err: unknown) {
      console.error('Failed to add collaborator', err)
    }
  }

  async function handleRemove(userId: string) {
    try {
      const updated = await removeCollaborator(projectId, userId)
      setCollaborators(updated)
    } catch (err: unknown) {
      console.error('Failed to remove collaborator', err)
    }
  }

  const isOwner = currentUserRole === 'owner'

  return (
    <div
      ref={panelRef}
      className="absolute right-0 top-full mt-1 z-50 w-80 rounded-lg shadow-xl"
      style={{ background: '#252526', border: '1px solid #444' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2" style={{ borderBottom: '1px solid #333' }}>
        <span className="text-xs font-medium" style={{ color: '#e8e8e8' }}>
          <Users size={12} className="inline mr-1.5" />
          Collaborators
        </span>
        <button onClick={onClose} className="text-[#6a737d] hover:text-[#e8e8e8]">
          <X size={14} />
        </button>
      </div>

      {/* Search (owner only) */}
      {isOwner && (
        <div className="px-3 py-2" style={{ borderBottom: '1px solid #333' }}>
          <div className="flex items-center gap-2 px-2 py-1.5 rounded" style={{ background: '#1e1e1e', border: '1px solid #333' }}>
            <Search size={12} className="text-[#6a737d] shrink-0" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => handleSearch(e.target.value)}
              placeholder="Search admins by name or email..."
              className="bg-transparent text-xs text-[#e8e8e8] outline-none w-full placeholder-[#6a737d]"
            />
          </div>

          {/* Search results */}
          {(searchResults.length > 0 || searching) && (
            <div className="mt-1.5 max-h-32 overflow-y-auto">
              {searching && <div className="text-[10px] text-[#6a737d] px-1 py-1">Searching...</div>}
              {searchResults.map((user) => (
                <div
                  key={user.user_id}
                  className="flex items-center justify-between px-2 py-1.5 rounded hover:bg-[#2a2d2e] group"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <div
                      className="w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-medium shrink-0"
                      style={{ background: '#ce9178', color: '#fff' }}
                    >
                      {user.name.charAt(0).toUpperCase()}
                    </div>
                    <div className="min-w-0">
                      <div className="text-[11px] text-[#e8e8e8] truncate">{user.name}</div>
                      <div className="text-[9px] text-[#6a737d] truncate">{user.email}</div>
                    </div>
                  </div>
                  <button
                    onClick={() => handleAdd(user.user_id)}
                    className="text-[#ce9178] hover:text-white p-0.5"
                    title="Add collaborator"
                  >
                    <UserPlus size={12} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Collaborator list */}
      <div className="px-3 py-2 max-h-48 overflow-y-auto">
        {loading ? (
          <div className="text-[10px] text-[#6a737d] text-center py-3">Loading...</div>
        ) : collaborators.length === 0 ? (
          <div className="text-[10px] text-[#6a737d] text-center py-3">No collaborators yet</div>
        ) : (
          collaborators.map((c) => (
            <div
              key={c.user_id}
              className="flex items-center justify-between py-1.5 group"
            >
              <div className="flex items-center gap-2 min-w-0">
                <div
                  className="w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-medium shrink-0"
                  style={{
                    background: c.role === 'owner' ? '#ce9178' : '#569cd6',
                    color: '#fff',
                  }}
                >
                  {c.name.charAt(0).toUpperCase()}
                </div>
                <div className="min-w-0">
                  <div className="text-[11px] text-[#e8e8e8] truncate flex items-center gap-1">
                    {c.name}
                    {c.role === 'owner' && (
                      <Crown size={9} className="text-[#ce9178] shrink-0" />
                    )}
                  </div>
                  <div className="text-[9px] text-[#6a737d] truncate">{c.email}</div>
                </div>
              </div>
              {isOwner && c.role !== 'owner' && (
                <button
                  onClick={() => handleRemove(c.user_id)}
                  className="text-[#6a737d] hover:text-red-400 p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                  title="Remove collaborator"
                >
                  <X size={12} />
                </button>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
