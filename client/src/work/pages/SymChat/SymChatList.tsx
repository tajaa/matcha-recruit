import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, Plus, Users } from 'lucide-react'
import { useWorkBase } from '../../routes/WorkSurfaceContext'
import { getSharedChannelSocket } from '../../api/channelSocket'
import { listSymChats, type SymChatSummary } from '../../api/matchaWork/symChat'
import { KIND_LABEL, STATUS_LABEL, resolutionText, statusClass } from './format'
import NewSymChatModal from './NewSymChatModal'

export default function SymChatList() {
  const navigate = useNavigate()
  const base = useWorkBase()
  const [chats, setChats] = useState<SymChatSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  const refresh = useCallback((): Promise<void> => listSymChats().then(
    (res) => {
      setChats(res.sym_chats)
      setError(null)
      setLoading(false)
    },
    (err) => {
      setError(err instanceof Error && err.message ? err.message : 'Could not load sym-chats')
      setLoading(false)
    },
  ), [])

  useEffect(() => { void refresh() }, [refresh])

  useEffect(() => {
    const socket = getSharedChannelSocket()
    const onUpdate = () => { void refresh() }
    socket.addSymChatListener(onUpdate)
    return () => socket.removeSymChatListener(onUpdate)
  }, [refresh])

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-2xl space-y-4 px-4 py-5">
        <header className="flex items-center justify-between gap-3">
          <div>
            <h1 className="text-lg font-semibold text-w-text">Sym-chats</h1>
            <p className="text-xs text-w-faint">Small group chats that settle one thing — a time or a decision.</p>
          </div>
          <button
            onClick={() => setCreating(true)}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-w-accent px-3 py-1.5 text-sm font-medium text-w-on-accent hover:bg-w-accent-hi"
          >
            <Plus size={14} /> New
          </button>
        </header>

        {loading ? (
          <div className="flex justify-center py-10"><Loader2 size={18} className="animate-spin text-w-faint" /></div>
        ) : error ? (
          <p role="alert" className="text-sm text-red-400">{error}</p>
        ) : chats.length === 0 ? (
          <div className="rounded-xl border border-dashed border-w-line px-6 py-10 text-center">
            <Users size={20} className="mx-auto mb-2 text-w-faint" />
            <p className="text-sm text-w-dim">No sym-chats yet.</p>
            <p className="text-xs text-w-faint">Start one to find a meeting time or make a group decision.</p>
          </div>
        ) : (
          <ul className="space-y-2">
            {chats.map((chat) => (
              <li key={chat.id}>
                <button
                  onClick={() => navigate(`${base}/sym-chat/${chat.id}`)}
                  className="w-full space-y-1 rounded-xl border border-w-line bg-w-surface px-4 py-3 text-left transition-colors hover:bg-w-surface2"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="truncate text-sm font-medium text-w-text">{chat.title}</span>
                    <span className="flex shrink-0 items-center gap-1.5">
                      {chat.status === 'open' && !chat.i_responded && (
                        <span className="rounded-full bg-w-accent px-2 py-0.5 text-[10px] font-semibold text-w-on-accent">Your turn</span>
                      )}
                      <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${statusClass(chat.status)}`}>
                        {STATUS_LABEL[chat.status]}
                      </span>
                    </span>
                  </div>
                  <p className="truncate text-xs text-w-dim">
                    {chat.status === 'resolved' && chat.resolution ? `Settled: ${resolutionText(chat.resolution)}` : chat.summary}
                  </p>
                  <p className="text-[11px] text-w-faint">
                    {KIND_LABEL[chat.kind]} · {chat.responded_count}/{chat.participant_count} responded
                    {chat.is_organizer && ' · you organized'}
                  </p>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {creating && (
        <NewSymChatModal
          onClose={() => setCreating(false)}
          onCreated={(chat) => { setCreating(false); navigate(`${base}/sym-chat/${chat.id}`) }}
        />
      )}
    </div>
  )
}
