import { useEffect, useState } from 'react'
import { api } from '../../../api/client'
import { Check, X, Loader2 } from 'lucide-react'
import type { PendingComment } from './types'

export default function CommentsModerationPanel({ onCountChange }: { onCountChange: (n: number) => void }) {
  const [comments, setComments] = useState<PendingComment[]>([])
  const [loading, setLoading] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const rows = await api.get<PendingComment[]>('/blogs/comments/pending')
      setComments(rows)
      onCountChange(rows.length)
    } catch (e) {
      setError((e as Error).message)
      setComments([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  async function moderate(id: string, status: 'approved' | 'rejected') {
    setBusyId(id)
    try {
      await api.patch(`/blogs/comments/${id}?status=${status}`)
      const remaining = comments.filter(c => c.id !== id)
      setComments(remaining)
      onCountChange(remaining.length)
    } catch (e) {
      alert(`Moderation failed: ${(e as Error).message}`)
    } finally {
      setBusyId(null)
    }
  }

  if (loading) return <div className="flex items-center gap-2 text-zinc-500 text-sm"><Loader2 size={14} className="animate-spin" /> Loading…</div>
  if (error) return <div className="text-amber-400 text-sm">{error}</div>
  if (comments.length === 0) {
    return (
      <div className="text-zinc-500 text-sm py-12 text-center border border-dashed border-zinc-800 rounded">
        No pending comments. New comments will appear here.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {comments.map((c) => (
        <div key={c.id} className="border border-zinc-800 rounded p-4 bg-zinc-950">
          <div className="flex items-baseline justify-between mb-2">
            <div className="text-xs text-zinc-500">
              <span className="text-zinc-300 font-medium">{c.author_name}</span>
              {c.post_title && <> on <span className="text-zinc-300">{c.post_title}</span></>}
              <span className="ml-2">{new Date(c.created_at).toLocaleString()}</span>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => moderate(c.id, 'approved')}
                disabled={busyId === c.id}
                className="text-emerald-400 hover:text-emerald-300 text-xs font-medium px-2.5 py-1 rounded border border-emerald-900/60 disabled:opacity-40 flex items-center gap-1"
              >
                <Check className="w-3 h-3" /> Approve
              </button>
              <button
                onClick={() => moderate(c.id, 'rejected')}
                disabled={busyId === c.id}
                className="text-amber-400 hover:text-amber-300 text-xs font-medium px-2.5 py-1 rounded border border-amber-900/60 disabled:opacity-40 flex items-center gap-1"
              >
                <X className="w-3 h-3" /> Reject
              </button>
            </div>
          </div>
          <p className="text-sm text-zinc-200 whitespace-pre-wrap">{c.content}</p>
        </div>
      ))}
    </div>
  )
}
