import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Hash, LayoutGrid, Plus, Compass, Loader2 } from 'lucide-react'
import { listChannels } from '../../api/channels'
import type { ChannelSummary } from '../../api/channels'
import { listProjects, createProjectNew } from '../../api/matchaWork'
import type { MWProject } from '../../types/matcha-work'
import CreateChannelModal from '../../components/channels/CreateChannelModal'
import { useWorkBase, useWorkBrand } from '../../routes/WorkSurfaceContext'
import { useMe } from '../../hooks/useMe'

// werk-lite landing: just the two things the product is — Channels + Boards.
// Deliberately not MatchaWorkList (threads/projects/tasks tabs, recruiting).
export default function WerkLiteHome() {
  const navigate = useNavigate()
  const base = useWorkBase()
  const brand = useWorkBrand()
  const { me } = useMe()
  const canCreateChannel = ['client', 'admin', 'individual'].includes(me?.user?.role ?? '')

  const [channels, setChannels] = useState<ChannelSummary[]>([])
  const [boards, setBoards] = useState<MWProject[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreateChannel, setShowCreateChannel] = useState(false)
  const [creatingBoard, setCreatingBoard] = useState(false)

  useEffect(() => {
    Promise.allSettled([listChannels(), listProjects()])
      .then(([ch, pr]) => {
        if (ch.status === 'fulfilled') setChannels(ch.value)
        // Boards = general kanban projects only (filter out recruiting/
        // presentation/discipline projects that share the mw_projects table).
        if (pr.status === 'fulfilled') setBoards(pr.value.filter((b) => b.project_type === 'general'))
      })
      .finally(() => setLoading(false))
  }, [])

  async function handleCreateBoard() {
    if (creatingBoard) return
    setCreatingBoard(true)
    try {
      const board = await createProjectNew('New Board', 'general')
      navigate(`${base}/boards/${board.id}`)
    } catch { /* surfaced by the API error reporter */ } finally {
      setCreatingBoard(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="animate-spin text-w-dim" size={24} />
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-10">
      <h1 className="text-2xl font-semibold text-white mb-1">{brand}</h1>
      <p className="text-sm text-w-dim mb-8">Team chat, calls, and boards.</p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Channels */}
        <section className="rounded-xl border border-w-line bg-w-surface/60 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-w-line">
            <div className="flex items-center gap-2 text-w-text font-medium text-sm">
              <Hash size={16} className="text-w-accent" /> Channels
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => navigate(`${base}/channels`)}
                className="p-1.5 rounded text-w-dim hover:text-w-accent hover:bg-w-surface2 transition-colors"
                title="Browse channels"
              >
                <Compass size={15} />
              </button>
              {canCreateChannel && (
                <button
                  onClick={() => setShowCreateChannel(true)}
                  className="p-1.5 rounded text-w-dim hover:text-w-accent hover:bg-w-surface2 transition-colors"
                  title="New channel"
                >
                  <Plus size={15} />
                </button>
              )}
            </div>
          </div>
          <div className="p-2">
            {channels.length === 0 ? (
              <p className="px-2 py-6 text-center text-[13px] text-w-faint">No channels yet — create one to start chatting.</p>
            ) : (
              channels.map((ch) => (
                <button
                  key={ch.id}
                  onClick={() => navigate(`${base}/channels/${ch.id}`)}
                  className="w-full flex items-center gap-2 px-2.5 py-2 rounded-md text-[13px] text-w-text hover:bg-w-surface2/60 transition-colors text-left"
                >
                  <Hash size={14} className="text-w-dim shrink-0" />
                  <span className={`flex-1 min-w-0 truncate ${ch.unread_count > 0 ? 'font-semibold text-white' : ''}`}>{ch.name}</span>
                  {ch.unread_count > 0 && (
                    <span className="w-4 h-4 rounded-full bg-w-accent text-[9px] font-bold text-white flex items-center justify-center shrink-0">
                      {ch.unread_count > 9 ? '9+' : ch.unread_count}
                    </span>
                  )}
                </button>
              ))
            )}
          </div>
        </section>

        {/* Boards */}
        <section className="rounded-xl border border-w-line bg-w-surface/60 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-w-line">
            <div className="flex items-center gap-2 text-w-text font-medium text-sm">
              <LayoutGrid size={16} className="text-[#ce9178]" /> Boards
            </div>
            {canCreateChannel && (
              <button
                onClick={handleCreateBoard}
                disabled={creatingBoard}
                className="p-1.5 rounded text-w-dim hover:text-w-accent hover:bg-w-surface2 transition-colors disabled:opacity-50"
                title="New board"
              >
                {creatingBoard ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}
              </button>
            )}
          </div>
          <div className="p-2">
            {boards.length === 0 ? (
              <p className="px-2 py-6 text-center text-[13px] text-w-faint">No boards yet — create one to track work.</p>
            ) : (
              boards.map((b) => (
                <button
                  key={b.id}
                  onClick={() => navigate(`${base}/boards/${b.id}`)}
                  className="w-full flex items-center gap-2 px-2.5 py-2 rounded-md text-[13px] text-w-text hover:bg-w-surface2/60 transition-colors text-left"
                >
                  <LayoutGrid size={14} className="text-w-dim shrink-0" />
                  <span className="flex-1 min-w-0 truncate">{b.title}</span>
                </button>
              ))
            )}
          </div>
        </section>
      </div>

      {showCreateChannel && (
        <CreateChannelModal
          onClose={() => setShowCreateChannel(false)}
          canCreatePaid={me?.user?.role === 'admin'}
          onCreated={(ch) => {
            setShowCreateChannel(false)
            navigate(`${base}/channels/${ch.id}`)
          }}
        />
      )}
    </div>
  )
}
