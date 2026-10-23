import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, Mail, Send } from 'lucide-react'
import { cappeApi } from '../../api'
import { ui } from '../../components/ui'
import type { CappeIssue, CappePost, CappeSubscriber } from '../../types'

/** `sites/:siteId/emails` — send a published story to the magazine's
 *  followers, try it on yourself first, and see what went out. The email is
 *  Gummfit's template; a story goes out once. (The API still calls these
 *  "issues"; an issue in print is `../issues/IssuesPage.tsx`.) */
export default function Emails() {
  const { siteId } = useParams<{ siteId: string }>()
  const [issues, setIssues] = useState<CappeIssue[] | null>(null)
  const [stories, setStories] = useState<CappePost[]>([])
  const [followers, setFollowers] = useState(0)
  const [storyId, setStoryId] = useState('')
  const [subject, setSubject] = useState('')
  const [whole, setWhole] = useState(false)
  const [busy, setBusy] = useState<'' | 'test' | 'send'>('')
  const [note, setNote] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    Promise.all([
      cappeApi.get<CappeIssue[]>(`/sites/${siteId}/issues`),
      cappeApi.get<CappePost[]>(`/sites/${siteId}/posts`),
      cappeApi.get<CappeSubscriber[]>(`/sites/${siteId}/subscribers`),
    ]).then(([i, p, s]) => {
      if (!live) return
      setIssues(i)
      // Magazine stories, flowing or made in Studio (the send takes either).
      setStories(p.filter((x) => x.status === 'published' && x.format !== 'markdown' && !x.hidden))
      setFollowers(s.filter((x) => x.status === 'subscribed').length)
    }).catch((e) => { if (live) setError(e instanceof Error ? e.message : 'Could not load your emails') })
    return () => { live = false }
  }, [siteId])

  const sent = useMemo(() => new Set((issues || []).map((i) => i.story_id)), [issues])
  const unsent = stories.filter((s) => !sent.has(s.id))
  const chosen = unsent.find((s) => s.id === storyId) || unsent[0]
  const paid = chosen?.access === 'paid'

  const send = async (test: boolean) => {
    if (!chosen) return
    if (!test && !window.confirm(`Send “${chosen.title}” to ${followers} follower${followers === 1 ? '' : 's'}? A story goes out once.`)) return
    setBusy(test ? 'test' : 'send')
    setError(null)
    setNote(null)
    const body = { subject: subject.trim() || null, include_body: whole && !paid }
    try {
      if (test) {
        const res = await cappeApi.post<{ to: string }>(`/sites/${siteId}/posts/${chosen.id}/issue/test`, body)
        setNote(`A test is on its way to ${res.to}.`)
      } else {
        const issue = await cappeApi.post<CappeIssue>(`/sites/${siteId}/posts/${chosen.id}/issue`, body)
        setIssues((list) => [issue, ...(list || [])])
        setStoryId('')
        setSubject('')
        setNote('Sending. It can take a few minutes to reach everyone.')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'That didn’t send')
    } finally {
      setBusy('')
    }
  }

  if (issues === null && !error) return <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <div>
        <h1 className={ui.heading}>Emails</h1>
        <p className={ui.subtitle}>Send a published story to the {followers} {followers === 1 ? 'person who follows' : 'people who follow'} your magazine. Replies go to your account email.</p>
      </div>

      <section className={`${ui.card} space-y-4 p-5`} aria-label="Send a story">
        {unsent.length === 0 ? (
          <p className="text-sm text-zinc-400">Publish a story to email it. Each story goes out once.</p>
        ) : (
          <>
            <label className="block">
              <span className={ui.label}>Story</span>
              <select value={chosen?.id || ''} onChange={(e) => setStoryId(e.target.value)} className={ui.input}>
                {unsent.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
              </select>
            </label>
            <label className="block">
              <span className={ui.label}>Subject</span>
              <input value={subject} onChange={(e) => setSubject(e.target.value)} maxLength={200} className={ui.input}
                placeholder={chosen?.title || ''} />
            </label>
            <label className="flex items-start gap-2 text-sm text-zinc-300">
              <input type="checkbox" checked={whole && !paid} disabled={paid} onChange={(e) => setWhole(e.target.checked)} className="mt-0.5" />
              <span>Send the whole story, not just its opening.{paid && ' (A story for subscribers only ever sends its opening.)'}</span>
            </label>
            <div className="flex flex-wrap gap-2">
              <button type="button" className={ui.btnGhost} disabled={!!busy} onClick={() => send(true)}>
                {busy === 'test' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mail className="h-4 w-4" />} Send me a test
              </button>
              <button type="button" className={ui.btnPrimary} disabled={!!busy || followers === 0} onClick={() => send(false)}>
                {busy === 'send' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                {followers === 0 ? 'No followers yet' : `Send to ${followers}`}
              </button>
            </div>
          </>
        )}
        {note && <p className="text-sm text-emerald-400" aria-live="polite">{note}</p>}
        {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
      </section>

      {issues && issues.length > 0 && (
        <ul className="divide-y divide-zinc-800 rounded-2xl border border-zinc-800 bg-zinc-900" aria-label="Sent emails">
          {issues.map((i) => (
            <li key={i.id} className="flex items-center gap-4 px-5 py-3">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-zinc-100">{i.subject}</p>
                <p className="text-xs text-zinc-500">
                  {i.status === 'sent'
                    ? `Sent to ${i.recipient_count}${i.failed_count ? ` · ${i.failed_count} didn’t go` : ''}${i.sent_at ? ` · ${new Date(i.sent_at).toLocaleDateString()}` : ''}`
                    : 'Sending…'}
                </p>
              </div>
              <span className={`${ui.badge} ${i.status === 'sent' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-zinc-800 text-zinc-400'}`}>{i.status}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
