import { useState } from 'react'
import { useAsync } from '../../hooks/useAsync'
import { relativeTime, shortDateWithYear } from '../../utils/format'

// Public page: an absolute date after a week (a dated comment is more useful
// than "23d ago"), and echo an unparseable timestamp rather than rendering a
// bare em dash to a visitor.
const formatRelative = (iso: string) =>
  relativeTime(iso, {
    maxRelativeDays: 7,
    absolute: shortDateWithYear,
    onInvalid: (raw) => String(raw),
  })
import { api } from '../../api/client'

const INK = 'var(--color-ivory-ink)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'

type Comment = {
  id: string
  author_name: string
  content: string
  created_at: string
}

export default function BlogComments({ slug }: { slug: string }) {
  const { data: comments, loading } = useAsync(
    () => (slug ? api.get<Comment[]>(`/blogs/${slug}/comments`) : Promise.resolve([])),
    [slug],
    [],
  )
  const [authorName, setAuthorName] = useState('')
  const [content, setContent] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!content.trim() || !authorName.trim() || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      await api.post(`/blogs/${slug}/comments`, {
        author_name: authorName.trim(),
        content: content.trim(),
      })
      setSubmitted(true)
      setContent('')
    } catch (err) {
      setError((err as Error).message || 'Failed to submit comment.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="mt-20 pt-10 border-t" style={{ borderColor: LINE }}>
      <h2 className="text-2xl mb-6" style={{ fontFamily: 'var(--font-display)', fontWeight: 500, color: INK }}>
        Comments
      </h2>

      {loading ? (
        <p className="text-sm" style={{ color: MUTED }}>Loading…</p>
      ) : comments.length === 0 ? (
        <p className="text-sm" style={{ color: MUTED }}>Be the first to leave a comment.</p>
      ) : (
        <ul className="space-y-6 mb-10">
          {comments.map((c) => (
            <li key={c.id} className="pb-5 border-b" style={{ borderColor: LINE }}>
              <div className="flex items-baseline gap-3 mb-2">
                <span className="text-sm font-medium" style={{ color: INK }}>{c.author_name}</span>
                <span className="text-xs" style={{ color: MUTED }}>{formatRelative(c.created_at)}</span>
              </div>
              <p className="text-sm whitespace-pre-wrap" style={{ color: INK, lineHeight: 1.6 }}>{c.content}</p>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-10">
        <h3 className="text-sm uppercase tracking-widest mb-4" style={{ color: MUTED }}>Leave a comment</h3>
        {submitted ? (
          <div className="px-5 py-4 text-sm border" style={{ borderColor: LINE, color: INK }}>
            Comment submitted. It will appear once an admin approves it.
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-3">
            <input
              type="text"
              value={authorName}
              onChange={(e) => setAuthorName(e.target.value)}
              placeholder="Your name"
              maxLength={120}
              required
              className="w-full px-3 py-2 text-sm border bg-transparent outline-none focus:border-current"
              style={{ borderColor: LINE, color: INK }}
            />
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="Your comment…"
              rows={4}
              maxLength={4000}
              required
              className="w-full px-3 py-2 text-sm border bg-transparent outline-none focus:border-current resize-y"
              style={{ borderColor: LINE, color: INK }}
            />
            {error && <p className="text-xs" style={{ color: '#a00' }}>{error}</p>}
            <div className="flex items-center justify-between">
              <p className="text-xs" style={{ color: MUTED }}>Comments are reviewed before being published.</p>
              <button
                type="submit"
                disabled={submitting || !content.trim() || !authorName.trim()}
                className="px-5 py-2 text-sm border disabled:opacity-40"
                style={{ borderColor: INK, color: INK }}
              >
                {submitting ? 'Submitting…' : 'Submit'}
              </button>
            </div>
          </form>
        )}
      </div>
    </section>
  )
}

