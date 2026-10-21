import { useState } from 'react'
import { AlertTriangle, CalendarClock, Check, Download, Film, Link2, Loader2, Send, X } from 'lucide-react'
import { cappeApi } from '../../../api'
import type {
  CappeSocialConnection, CappeSocialExportPlatform, CappeSocialPlanCard, CappeSocialPlanConfirmed, CappeSocialPlanPost,
} from '../../../types'
import { CAPTION_LIMIT, normalizeHashtags } from '../../../utils/socialSchedule'

type Mode = 'at' | 'now' | 'draft' | 'export'
type Words = {
  caption: string; hashtags: string; facebook: string; alt: string
  tiktok: string; tiktokTags: string; ytTitle: string; ytDescription: string; ytTags: string
}

const MODES: [Mode, string][] = [['at', 'Schedule'], ['now', 'Post now'], ['draft', 'Save as drafts']]
const EXPORT_PLATFORMS: [CappeSocialExportPlatform, string][] = [['instagram', 'Instagram'], ['tiktok', 'TikTok'], ['youtube', 'YouTube']]
const YT_TITLE_LIMIT = 100

function wordsOf(post: CappeSocialPlanPost): Words {
  return {
    caption: post.instagram.caption, hashtags: post.instagram.hashtags.join(' '), facebook: post.facebook.text,
    alt: post.alt_text ?? '',
    tiktok: post.tiktok?.caption ?? '', tiktokTags: post.tiktok?.hashtags.join(' ') ?? '',
    ytTitle: post.youtube?.title ?? '', ytDescription: post.youtube?.description ?? '', ytTags: post.youtube?.tags.join(', ') ?? '',
  }
}

const field = 'mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 text-sm text-zinc-100'

/** The plan the chat proposed, editable, posted only on Confirm. Videos may
 *  also get files to download for Instagram, TikTok and YouTube ("Files
 *  only" posts nothing). Server side: services/social/chat/confirm.py. Keyed
 *  on the plan id by the parent, so a new plan starts with fresh edits. */
export default function PlanCard({ siteId, conversationId, card, connections, onDone }: {
  siteId: string
  conversationId: string
  card: CappeSocialPlanCard
  connections: CappeSocialConnection[]
  onDone: (card: CappeSocialPlanCard, message: string | null, where?: 'queue' | 'exports') => void
}) {
  const { plan } = card
  const exports = plan.exports ?? null
  const live = connections.filter((c) => c.status === 'connected')
  const [mode, setMode] = useState<Mode>(exports?.files_only ? 'export' : plan.when.mode === 'now' ? 'now' : 'at')
  const [whenLocal, setWhenLocal] = useState(plan.when.local ?? '')
  const [picked, setPicked] = useState<Set<string>>(() => new Set(plan.accounts.map((a) => a.connection_id)))
  const [keepLink, setKeepLink] = useState(true)
  const [words, setWords] = useState<Words[]>(() => plan.posts.map(wordsOf))
  const [files, setFiles] = useState<Set<CappeSocialExportPlatform>>(() => new Set(exports?.platforms ?? []))
  const [captions, setCaptions] = useState(!!exports?.captions)
  const [busy, setBusy] = useState<'confirm' | 'dismiss' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const open = card.status === 'proposed'
  const filesOnly = mode === 'export'
  // Only accounts still connected count: one that expired since the plan
  // was made has no checkbox, so it must not ride along to the server.
  const chosen = filesOnly ? [] : live.filter((c) => picked.has(c.id)).map((c) => c.id)
  const platforms = new Set(filesOnly ? [] : live.filter((c) => picked.has(c.id)).map((c) => c.platform))
  const n = plan.posts.length
  const videos = exports?.items.length ?? 0
  const modes: [Mode, string][] = exports ? [...MODES, ['export', 'Files only']] : MODES

  function setWord(i: number, patch: Partial<Words>) {
    setWords((ws) => ws.map((w, j) => (j === i ? { ...w, ...patch } : w)))
  }

  function toggle<T>(set: (fn: (s: Set<T>) => Set<T>) => void, id: T) {
    set((s) => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function confirm() {
    if (mode === 'at' && !whenLocal) { setError('Pick a time'); return }
    if (!filesOnly && mode !== 'draft' && !chosen.length) { setError('Pick at least one account to post to'); return }
    if (filesOnly && !files.size) { setError('Pick at least one platform to make files for'); return }
    setBusy('confirm')
    setError(null)
    try {
      const res = await cappeApi.post<CappeSocialPlanConfirmed>(
        `/sites/${siteId}/social/chat/conversations/${conversationId}/plans/${card.id}/confirm`, {
          revision: card.revision,
          mode,
          when_local: mode === 'at' ? whenLocal : null,
          connection_ids: chosen,
          keep_link: keepLink,
          posts: words.map((w, i) => ({
            instagram: { caption: w.caption, hashtags: normalizeHashtags(w.hashtags) },
            facebook: { text: w.facebook },
            alt_text: w.alt.trim() || null,
            tiktok: plan.posts[i].tiktok ? { caption: w.tiktok, hashtags: normalizeHashtags(w.tiktokTags) } : null,
            youtube: plan.posts[i].youtube ? {
              title: w.ytTitle, description: w.ytDescription,
              tags: w.ytTags.split(',').map((t) => t.trim()).filter(Boolean),
            } : null,
          })),
          exports: exports ? { platforms: EXPORT_PLATFORMS.map(([p]) => p).filter((p) => files.has(p)), captions } : null,
        })
      const made = res.exports?.length ?? 0
      const prepared = made ? `${made === 1 ? 'Files' : `Files for ${made} videos`} being prepared in Exports.` : ''
      if (filesOnly) { onDone(res.plan, prepared || 'Nothing to prepare.', 'exports'); return }
      const label = n === 1 ? 'Post' : `${n} posts`
      const posted = mode === 'now' ? `${label} going out now.` : mode === 'at' ? `${label} scheduled.`
        : `${n === 1 ? 'Draft' : `${n} drafts`} saved.`
      onDone(res.plan, [posted, prepared].filter(Boolean).join(' '), 'queue')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Couldn’t post that')
    } finally {
      setBusy(null)
    }
  }

  async function dismiss() {
    setBusy('dismiss')
    try {
      const res = await cappeApi.post<CappeSocialPlanCard>(
        `/sites/${siteId}/social/chat/conversations/${conversationId}/plans/${card.id}/dismiss`)
      onDone(res, null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Couldn’t dismiss that')
    } finally {
      setBusy(null)
    }
  }

  if (!open) {
    const posts = card.post_ids.length
    const made = card.export_ids?.length ?? 0
    const parts = [
      posts ? `${posts === 1 ? 'the post is' : `${posts} posts are`} in the Queue` : '',
      made ? `${made === 1 ? 'the files are' : `files for ${made} videos are`} in Exports` : '',
    ].filter(Boolean)
    return (
      <div className="rounded-2xl border border-zinc-800 bg-zinc-900/60 px-4 py-3 text-sm text-zinc-400">
        {card.status === 'executed'
          ? <span className="inline-flex items-center gap-1.5 text-emerald-300"><Check className="h-4 w-4" />
            Done{parts.length ? ` — ${parts.join(', and ')}.` : '.'}</span>
          : 'This plan was set aside.'}
      </div>
    )
  }

  const confirmLabel = filesOnly ? (videos > 1 ? `Prepare files for ${videos} videos` : 'Prepare files')
    : (mode === 'at' ? (n > 1 ? `Schedule ${n} posts` : 'Schedule post')
      : mode === 'now' ? (n > 1 ? `Post ${n} now` : 'Post it now') : 'Save drafts')
    + (exports && files.size ? ' + prepare files' : '')

  return (
    <div className="space-y-4 rounded-2xl border border-lime-400/30 bg-zinc-900 p-5" aria-label="Plan">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-zinc-100">
          {filesOnly ? (videos === 1 ? 'Files for your video' : `Files for ${videos} videos`) : n === 1 ? 'The post' : `${n} posts`}
        </h3>
        <span className="text-xs text-zinc-500">{filesOnly ? 'Nothing is posted.' : 'Nothing goes out until you confirm.'}</span>
      </div>

      {plan.warnings.length > 0 && (
        <ul className="space-y-1">
          {plan.warnings.map((w) => (
            <li key={w} className="flex gap-1.5 text-xs text-amber-300"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />{w}</li>
          ))}
        </ul>
      )}

      {exports && (
        <div className="space-y-2 rounded-xl border border-zinc-800 bg-zinc-950 p-3" aria-label="Files to download">
          <p className="flex gap-1.5 text-xs text-zinc-300"><Download className="mt-0.5 h-3.5 w-3.5 shrink-0 text-lime-400" />{exports.note}</p>
          <div className="flex flex-wrap items-center gap-2">
            {EXPORT_PLATFORMS.map(([p, label]) => (
              <button key={p} type="button" onClick={() => toggle(setFiles, p)} aria-pressed={files.has(p)}
                className={`rounded-full px-3 py-1 text-xs font-medium ${files.has(p)
                  ? 'bg-lime-400 text-zinc-950' : 'border border-zinc-700 text-zinc-400 hover:text-zinc-200'}`}>{label} file</button>
            ))}
            <label className="ml-1 inline-flex items-center gap-1.5 text-xs text-zinc-300">
              <input type="checkbox" checked={captions} onChange={(e) => setCaptions(e.target.checked)} className="accent-lime-400" />
              Word-for-word captions
            </label>
          </div>
        </div>
      )}

      {plan.posts.map((post, i) => {
        const showIg = platforms.has('instagram') || (filesOnly && files.has('instagram') && !!post.tiktok)
        if (filesOnly && !post.tiktok && !post.youtube) return null
        return (
          <div key={i} className="space-y-2 rounded-xl border border-zinc-800 bg-zinc-950 p-3">
            <div className="flex items-center gap-2">
              {post.media.map((m, j) => (
                <div key={j} className="relative h-14 w-14 overflow-hidden rounded-md border border-zinc-700 bg-zinc-900">
                  {(m.url ?? m.poster)
                    ? <img src={(m.url ?? m.poster) as string} alt={m.name ?? ''} className="h-full w-full object-cover" />
                    : <Film className="m-auto mt-4 h-5 w-5 text-zinc-500" aria-hidden />}
                  {m.kind === 'video' && <Film className="absolute left-0.5 top-0.5 h-3 w-3 text-white drop-shadow" aria-label="Video" />}
                </div>
              ))}
              <span className="text-xs text-zinc-500">
                {n > 1 ? `Post ${i + 1}` : ''}{!filesOnly && post.offset_days ? ` · ${post.offset_days} day${post.offset_days > 1 ? 's' : ''} after the first` : ''}
              </span>
            </div>
            {showIg && (
              <>
                <label className="block text-xs font-medium text-zinc-400">Instagram caption
                  <textarea value={words[i].caption} rows={3} onChange={(e) => setWord(i, { caption: e.target.value })} className={`${field} py-2`} />
                </label>
                <label className="block text-xs font-medium text-zinc-400">Hashtags
                  <input value={words[i].hashtags} onChange={(e) => setWord(i, { hashtags: e.target.value })} className={`${field} py-1.5 text-lime-300`} />
                </label>
                {words[i].caption.length + words[i].hashtags.length > CAPTION_LIMIT && (
                  <p className="text-xs text-red-400">Instagram takes {CAPTION_LIMIT} characters, hashtags included.</p>
                )}
              </>
            )}
            {platforms.has('facebook') && (
              <label className="block text-xs font-medium text-zinc-400">Facebook text
                <textarea value={words[i].facebook} rows={3} onChange={(e) => setWord(i, { facebook: e.target.value })} className={`${field} py-2`} />
              </label>
            )}
            {post.tiktok && files.has('tiktok') && (
              <>
                <label className="block text-xs font-medium text-zinc-400">TikTok caption
                  <textarea value={words[i].tiktok} rows={2} onChange={(e) => setWord(i, { tiktok: e.target.value })} className={`${field} py-2`} />
                </label>
                <label className="block text-xs font-medium text-zinc-400">TikTok hashtags
                  <input value={words[i].tiktokTags} onChange={(e) => setWord(i, { tiktokTags: e.target.value })} className={`${field} py-1.5 text-lime-300`} />
                </label>
              </>
            )}
            {post.youtube && files.has('youtube') && (
              <>
                <label className="block text-xs font-medium text-zinc-400">YouTube title
                  <input value={words[i].ytTitle} maxLength={YT_TITLE_LIMIT} onChange={(e) => setWord(i, { ytTitle: e.target.value })} className={`${field} py-1.5`} />
                </label>
                <label className="block text-xs font-medium text-zinc-400">YouTube description
                  <textarea value={words[i].ytDescription} rows={3} onChange={(e) => setWord(i, { ytDescription: e.target.value })} className={`${field} py-2`} />
                </label>
                <label className="block text-xs font-medium text-zinc-400">YouTube tags <span className="font-normal text-zinc-500">(comma-separated)</span>
                  <input value={words[i].ytTags} onChange={(e) => setWord(i, { ytTags: e.target.value })} className={`${field} py-1.5`} />
                </label>
              </>
            )}
            {post.media.length > 0 && !filesOnly && (
              <label className="block text-xs text-zinc-500">Description for screen readers
                <input value={words[i].alt} onChange={(e) => setWord(i, { alt: e.target.value })} maxLength={500} className={`${field} py-1.5`} />
              </label>
            )}
          </div>
        )
      })}

      <div className="grid gap-4 sm:grid-cols-2">
        {!filesOnly && (
          <div>
            <div className="mb-1.5 text-xs font-medium text-zinc-400">Post to</div>
            {live.length === 0 ? (
              <p className="text-xs text-zinc-500">No accounts connected — you can save these as drafts.</p>
            ) : live.map((c) => (
              <label key={c.id} className="flex items-center gap-2 text-sm text-zinc-200">
                <input type="checkbox" checked={picked.has(c.id)} onChange={() => toggle(setPicked, c.id)} className="accent-lime-400" />
                <span className="capitalize">{c.platform}</span>
                <span className="text-zinc-500">{c.handle ? `@${c.handle}` : c.display_name}</span>
              </label>
            ))}
          </div>
        )}
        <div>
          <div className="mb-1.5 text-xs font-medium text-zinc-400">Link</div>
          {plan.link.url ? (
            <label className="flex items-start gap-2 text-sm text-zinc-200">
              <input type="checkbox" checked={keepLink} onChange={(e) => setKeepLink(e.target.checked)} className="mt-1 accent-lime-400" />
              <span className="min-w-0">
                <span className="inline-flex items-center gap-1"><Link2 className="h-3.5 w-3.5" />
                  {plan.link.product_name ?? 'Your store'}</span>
                <span className="block truncate text-xs text-zinc-500">{plan.link.url}</span>
              </span>
            </label>
          ) : <p className="text-xs text-zinc-500">No link.</p>}
        </div>
      </div>

      <div>
        <div className="flex flex-wrap gap-2">
          {modes.map(([m, label]) => (
            <button key={m} type="button" onClick={() => setMode(m)} aria-pressed={mode === m}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${mode === m
                ? 'bg-lime-400 text-zinc-950' : 'border border-zinc-700 text-zinc-300 hover:bg-zinc-800'}`}>{label}</button>
          ))}
        </div>
        {mode === 'at' && (
          <label className="mt-3 block text-sm text-zinc-300">{n > 1 ? 'First post' : 'When'} <span className="text-xs text-zinc-500">(your store’s time)</span>
            <input type="datetime-local" value={whenLocal} onChange={(e) => setWhenLocal(e.target.value)} aria-label="When"
              className="mt-1 block rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100" />
            {plan.when.label && whenLocal === plan.when.local && <span className="mt-1 block text-xs text-zinc-500">{plan.when.label}</span>}
          </label>
        )}
      </div>

      {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={confirm} disabled={busy !== null}
          className="inline-flex items-center gap-2 rounded-lg bg-lime-400 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-lime-300 disabled:opacity-60">
          {busy === 'confirm' ? <Loader2 className="h-4 w-4 animate-spin" />
            : filesOnly ? <Download className="h-4 w-4" /> : mode === 'at' ? <CalendarClock className="h-4 w-4" /> : <Send className="h-4 w-4" />}
          {confirmLabel}
        </button>
        <button type="button" onClick={dismiss} disabled={busy !== null}
          className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-300 hover:bg-zinc-800 disabled:opacity-60">
          <X className="h-4 w-4" /> Not this
        </button>
      </div>
    </div>
  )
}
