import { useState, type FormEvent } from 'react'
import { Calendar, ChevronDown, ChevronUp, MessageCircle, Pin } from 'lucide-react'
import { tellusApi } from '../api/tellusClient'
import { Button, Card, Chip, ErrorText, Textarea } from './ui'
import { LikeButton } from './LikeButton'
import type { BoardPost, BoardReply } from '../api/types'

const KIND_LABEL: Record<BoardPost['kind'], string> = {
  update: 'Update', deal: 'Deal', event: 'Event', question: 'Question',
}

function fmtRange(start: string | null, end: string | null): string {
  if (!start) return ''
  const opts: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }
  const s = new Date(start).toLocaleString([], opts)
  if (!end) return s
  return `${s} – ${new Date(end).toLocaleString([], opts)}`
}

// Inline-expansion convention (no modal): tapping the reply count loads and
// shows the thread beneath the post. Held replies are only ever shown to
// their own author (a "Pending approval" chip) or a board moderator — the
// server's reply_visible_to predicate is the real gate, this is just what
// the response already contains.
export function BoardPostCard({
  post, viewerRole, slug, brandId, onRedeem, onRemove, paused,
}: {
  post: BoardPost
  viewerRole: 'member' | 'moderator' | 'owner'
  slug: string
  // Only required for moderator actions (approve/reject) — a caller resolving
  // multiple boards must pass it or /board/replies/* 400s "Specify brand_id".
  brandId?: string
  onRedeem?: (listingId: string) => void
  onRemove?: (postId: string) => void
  paused?: boolean
}) {
  const isMod = viewerRole !== 'member'
  const [expanded, setExpanded] = useState(false)
  const [replies, setReplies] = useState<BoardReply[] | null>(null)
  const [loadingReplies, setLoadingReplies] = useState(false)
  const [body, setBody] = useState('')
  const [sending, setSending] = useState(false)
  const [err, setErr] = useState('')
  const [busyId, setBusyId] = useState<string | null>(null)

  async function toggleExpand() {
    const opening = !expanded
    setExpanded(opening)
    if (opening && replies === null) {
      setLoadingReplies(true)
      try {
        setReplies(await tellusApi.get<BoardReply[]>(`/boards/${slug}/posts/${post.id}/replies`))
      } catch (e) {
        setErr(e instanceof Error ? e.message : 'Failed to load replies')
      } finally {
        setLoadingReplies(false)
      }
    }
  }

  async function sendReply(e: FormEvent) {
    e.preventDefault()
    if (!body.trim()) return
    setSending(true); setErr('')
    try {
      const mine = await tellusApi.post<BoardReply>(`/boards/${slug}/posts/${post.id}/replies`, { body })
      setReplies((r) => [...(r ?? []), mine])
      setBody('')
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to send reply')
    } finally {
      setSending(false)
    }
  }

  async function deleteOwn(replyId: string) {
    setBusyId(replyId)
    try {
      await tellusApi.delete(`/boards/${slug}/replies/${replyId}`)
      setReplies((r) => (r ?? []).filter((x) => x.id !== replyId))
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to delete reply')
    } finally {
      setBusyId(null)
    }
  }

  async function moderate(replyId: string, action: 'approve' | 'reject') {
    setBusyId(replyId)
    try {
      const qs = brandId ? `?brand_id=${brandId}` : ''
      await tellusApi.post(`/board/replies/${replyId}/${action}${qs}`)
      setReplies((r) => (r ?? []).map((x) =>
        x.id === replyId ? { ...x, status: action === 'approve' ? 'approved' : 'rejected' } : x))
    } catch (e) {
      setErr(e instanceof Error ? e.message : `Failed to ${action} reply`)
    } finally {
      setBusyId(null)
    }
  }

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          {post.is_pinned && <Pin className="h-3.5 w-3.5 text-tu-accent" />}
          <Chip tone={post.kind === 'deal' ? 'positive' : undefined}>{KIND_LABEL[post.kind]}</Chip>
          {isMod && post.moderation_status !== 'visible' && <Chip tone="negative">{post.moderation_status}</Chip>}
        </div>
        <span className="whitespace-nowrap text-xs text-tu-faint">{new Date(post.created_at).toLocaleDateString()}</span>
      </div>

      <h3 className="mt-2 text-sm font-semibold">{post.title}</h3>
      {post.body && <p className="mt-1 whitespace-pre-wrap text-sm text-tu-dim">{post.body}</p>}

      {post.kind === 'event' && post.event_starts_at && (
        <p className="mt-2 flex items-center gap-1.5 text-xs text-tu-faint">
          <Calendar className="h-3.5 w-3.5" /> {fmtRange(post.event_starts_at, post.event_ends_at)}
        </p>
      )}

      {post.kind === 'deal' && post.listing && (
        <div className="mt-2.5 flex items-center justify-between gap-3 rounded-lg border border-tu-border bg-tu-panel2 px-3 py-2">
          <div>
            <p className="text-sm font-semibold">{post.listing.title}</p>
            <p className="text-xs text-tu-faint">{post.listing.points_cost} pts</p>
          </div>
          {post.listing.is_active === false ? (
            <Chip tone="negative">No longer available</Chip>
          ) : (
            viewerRole === 'member' && onRedeem && (
              <Button size="sm" onClick={() => onRedeem(post.listing!.id)}>Redeem</Button>
            )
          )}
        </div>
      )}

      <div className="mt-3 flex items-center justify-between border-t border-tu-border pt-2">
        <div className="flex items-center gap-3">
          <button type="button" onClick={() => void toggleExpand()} className="flex items-center gap-1.5 text-xs text-tu-dim hover:text-tu-accent">
            <MessageCircle className="h-3.5 w-3.5" />
            {post.approved_reply_count} repl{post.approved_reply_count === 1 ? 'y' : 'ies'}
            {isMod && !!post.held_reply_count && <Chip tone="negative">{post.held_reply_count} pending</Chip>}
            {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>
          <LikeButton
            target="board_post" targetId={post.id}
            count={post.like_count} liked={post.liked_by_me}
            disabled={viewerRole === 'member' && paused}
            onError={setErr}
          />
        </div>
        {isMod && onRemove && (
          <button
            type="button"
            onClick={() => { if (confirm('Remove this post?')) onRemove(post.id) }}
            className="text-xs text-tu-bad hover:underline"
          >
            Remove
          </button>
        )}
      </div>

      {expanded && (
        <div className="mt-2 space-y-2 border-t border-tu-border pt-2.5">
          {loadingReplies && <p className="text-xs text-tu-faint">Loading…</p>}
          {replies?.map((r) => (
            <div key={r.id} className="rounded-md bg-tu-panel2 px-2.5 py-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-semibold">{r.author_name}</span>
                <div className="flex items-center gap-1.5">
                  {r.status === 'held' && r.is_mine && <Chip>Pending approval</Chip>}
                  {r.status === 'rejected' && <Chip tone="negative">Not approved</Chip>}
                  {isMod && r.status === 'held' && (
                    <>
                      <button type="button" disabled={busyId === r.id} onClick={() => void moderate(r.id, 'approve')}
                        className="text-xs font-semibold text-tu-accent hover:underline disabled:opacity-50">
                        Approve
                      </button>
                      <button type="button" disabled={busyId === r.id} onClick={() => void moderate(r.id, 'reject')}
                        className="text-xs text-tu-bad hover:underline disabled:opacity-50">
                        Reject
                      </button>
                    </>
                  )}
                  {r.is_mine && r.status === 'held' && (
                    <button type="button" disabled={busyId === r.id} onClick={() => void deleteOwn(r.id)}
                      className="text-xs text-tu-faint hover:underline disabled:opacity-50">
                      Delete
                    </button>
                  )}
                </div>
              </div>
              <p className="mt-0.5 whitespace-pre-wrap text-sm">{r.body}</p>
              {r.status === 'approved' && (
                <div className="mt-1">
                  <LikeButton
                    target="board_reply" targetId={r.id}
                    count={r.like_count} liked={r.liked_by_me}
                    disabled={viewerRole === 'member' && paused}
                    onError={setErr}
                  />
                </div>
              )}
            </div>
          ))}
          {replies && replies.length === 0 && !loadingReplies && <p className="text-xs text-tu-faint">No replies yet.</p>}

          {viewerRole === 'member' && !paused && (
            <form onSubmit={sendReply} className="flex items-end gap-2">
              <div className="flex-1"><Textarea rows={1} value={body} onChange={(e) => setBody(e.target.value)} placeholder="Reply…" /></div>
              <Button size="sm" type="submit" loading={sending}>Send</Button>
            </form>
          )}
          {viewerRole === 'member' && paused && (
            <p className="text-xs text-tu-faint">Board paused — replies disabled.</p>
          )}
          <ErrorText>{err}</ErrorText>
        </div>
      )}
    </Card>
  )
}
