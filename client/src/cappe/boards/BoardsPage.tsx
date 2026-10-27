import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { LayoutDashboard, Loader2, Plus, Trash2 } from 'lucide-react'
import SurfaceShell from '../components/SurfaceShell'
import { ui } from '../components/ui'
import { boardsApi, fileUrl, type Board } from './api'
import { MAX_BOARDS_PER_SITE, TITLE_MAX } from './limits'

function message(e: unknown, fallback: string) {
  return e instanceof Error && e.message ? e.message : fallback
}

/** `sites/:siteId/boards` — the site's mood boards, last changed first. */
export default function BoardsPage() {
  const { siteId } = useParams<{ siteId: string }>()
  const navigate = useNavigate()
  const [boards, setBoards] = useState<Board[] | null>(null)
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!siteId) return
    let alive = true
    boardsApi.list(siteId)
      .then((list) => { if (alive) setBoards(list) })
      .catch((e) => { if (alive) setError(message(e, 'Your mood boards didn’t load.')) })
    return () => { alive = false }
  }, [siteId])

  if (!siteId) return null

  const create = async () => {
    const name = title.trim()
    if (!name || busy) return
    setBusy(true)
    setError(null)
    try {
      const board = await boardsApi.create(siteId, name)
      navigate(`/cappe/sites/${siteId}/boards/${board.id}`)
    } catch (e) {
      setError(message(e, 'That board wasn’t made.'))
      setBusy(false)
    }
  }

  const remove = async (board: Board) => {
    if (!window.confirm(`Delete “${board.title}” and everything pinned on it?`)) return
    try {
      await boardsApi.remove(siteId, board.id)
      setBoards((list) => (list ?? []).filter((b) => b.id !== board.id))
    } catch (e) {
      setError(message(e, 'That board wasn’t deleted.'))
    }
  }

  const full = (boards?.length ?? 0) >= MAX_BOARDS_PER_SITE
  return (
    <SurfaceShell title="Mood boards"
      subtitle="Pin photos, screenshots, documents, notes and links: anything that inspires you. Only you can see them.">
      <form className="mb-6 flex max-w-lg gap-2" onSubmit={(e) => { e.preventDefault(); void create() }}>
        <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={TITLE_MAX} disabled={full}
          placeholder={full ? `You have ${MAX_BOARDS_PER_SITE} boards, the most a site can have` : 'Name a new board, e.g. “Spring issue”'}
          aria-label="New board name" className={ui.input} />
        <button type="submit" disabled={!title.trim() || busy || full} className={ui.btnPrimary}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}New board
        </button>
      </form>
      {error && <p role="alert" className="mb-4 text-sm text-red-300">{error}</p>}
      {boards === null && !error && <p className="flex items-center gap-2 text-sm text-zinc-400"><Loader2 className="h-4 w-4 animate-spin" />Loading…</p>}
      {boards?.length === 0 && (
        <div className={`${ui.card} p-8 text-center text-sm text-zinc-400`}>
          <LayoutDashboard className="mx-auto mb-3 h-8 w-8 text-zinc-600" />
          <p className="font-medium text-zinc-200">No mood boards yet</p>
          <p className="mt-1">Start one for a story, an issue or a look. Then drop in pictures, paste screenshots and links, and jot notes.</p>
        </div>
      )}
      {!!boards?.length && (
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-label="Mood boards">
          {boards.map((board) => (
            <li key={board.id} className={`${ui.cardHover} group relative overflow-hidden`}>
              <Link to={`/cappe/sites/${siteId}/boards/${board.id}`} className="block">
                <div className="grid aspect-[4/3] grid-cols-2 grid-rows-2 gap-0.5 bg-zinc-950">
                  {[0, 1, 2, 3].map((i) => (
                    <div key={i} className="overflow-hidden bg-zinc-800/60">
                      {board.covers[i] && <img src={fileUrl(board.covers[i]) ?? undefined} alt="" loading="lazy" className="h-full w-full object-cover" />}
                    </div>
                  ))}
                </div>
                <div className="p-3">
                  <p className="truncate font-medium text-zinc-100">{board.title}</p>
                  <p className="text-xs text-zinc-500">
                    {board.pin_count} {board.pin_count === 1 ? 'pin' : 'pins'} · {new Date(board.updated_at).toLocaleDateString()}
                  </p>
                </div>
              </Link>
              <button type="button" onClick={() => void remove(board)} aria-label={`Delete ${board.title}`}
                className="absolute right-2 top-2 rounded-md bg-zinc-950/70 p-1.5 text-zinc-400 opacity-0 transition hover:text-red-300 focus:opacity-100 group-hover:opacity-100">
                <Trash2 className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </SurfaceShell>
  )
}
