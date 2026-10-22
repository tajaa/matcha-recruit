import { ArrowDown, ArrowUp, Newspaper, Plus, X } from 'lucide-react'
import { ui } from '../../components/ui'
import type { CappePost, IssueStoryRef } from '../../types'
import { MAX_STORIES } from './coverVocab'
import { move } from './issueDoc'

const small = 'rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-sm text-zinc-100 placeholder:text-zinc-600'

/** What the list shows of a story: from the site's stories (`/posts`). */
export type StoryInfo = Pick<CappePost, 'id' | 'title' | 'status' | 'access' | 'hidden' | 'excerpt' | 'cover_image_url'>

/** The issue's stories in reading order: each with the section it sits under
 *  in the contents and its contents line (the dek when blank). */
export default function IssueStories({ stories, info, released, onChange, onRemove, onAdd }: {
  stories: IssueStoryRef[]
  info: Map<string, StoryInfo>
  released: boolean
  /** `step`: a move (its own undo step), not typing. */
  onChange: (next: IssueStoryRef[], step?: boolean) => void
  onRemove: (postId: string) => void
  onAdd: () => void
}) {
  const sections = Array.from(new Set(stories.map((s) => s.section?.trim()).filter((s): s is string => !!s)))
  const update = (i: number, change: Partial<IssueStoryRef>) => onChange(stories.map((s, j) => (j === i ? { ...s, ...change } : s)))
  const drafts = stories.filter((s) => info.get(s.post_id)?.status === 'draft').length

  return (
    <section className="space-y-3" aria-label="Stories in this issue">
      {stories.length === 0 && (
        <div className="rounded-2xl border border-dashed border-zinc-700 py-10 text-center text-sm text-zinc-500">
          <Newspaper className="mx-auto mb-2 h-7 w-7 text-zinc-300" />
          No stories yet. Add the stories this issue holds, in the order they’re read.
        </div>
      )}
      {drafts > 0 && (
        <p className="text-xs text-amber-300">
          {drafts === 1 ? 'One story is a draft' : `${drafts} stories are drafts`}:{' '}
          {released ? 'saving publishes it with the issue.' : 'it is published when you release the issue.'}
        </p>
      )}
      <datalist id="issue-sections">{sections.map((s) => <option key={s} value={s} />)}</datalist>
      <ol className="space-y-2">
        {stories.map((s, i) => {
          const story = info.get(s.post_id)
          return (
            <li key={s.post_id} className={`${ui.card} flex gap-3 p-3`}>
              <div className="h-16 w-12 shrink-0 overflow-hidden rounded bg-zinc-950">
                {story?.cover_image_url && <img src={story.cover_image_url} alt="" className="h-full w-full object-cover" />}
              </div>
              <div className="min-w-0 flex-1 space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs tabular-nums text-zinc-500">{i + 1}.</span>
                  <p className="min-w-0 flex-1 truncate text-sm font-medium text-zinc-100">{story?.title || 'A story'}</p>
                  {story?.status === 'draft' && <span className={`${ui.badge} bg-amber-500/15 text-amber-400`}>draft</span>}
                  {story?.status === 'archived' && <span className={`${ui.badge} bg-zinc-800 text-zinc-500`}>archived — not shown</span>}
                  {story?.access === 'paid' && <span className={`${ui.badge} bg-sky-500/15 text-sky-400`}>subscribers</span>}
                  {story?.hidden && <span className={`${ui.badge} bg-red-500/15 text-red-400`}>hidden by Gummfit</span>}
                </div>
                <div className="grid gap-2 sm:grid-cols-[10rem_1fr]">
                  <input value={s.section || ''} onChange={(e) => update(i, { section: e.target.value })} maxLength={40}
                    list="issue-sections" placeholder="Section" aria-label={`Section for ${story?.title || 'this story'}`} className={small} />
                  <input value={s.contents_line || ''} onChange={(e) => update(i, { contents_line: e.target.value })} maxLength={200}
                    placeholder={story?.excerpt || 'Its line in the contents'} aria-label={`Contents line for ${story?.title || 'this story'}`}
                    className={small} />
                </div>
              </div>
              <div className="flex shrink-0 flex-col gap-1">
                <button type="button" disabled={i === 0} onClick={() => onChange(move(stories, i, i - 1), true)}
                  className="rounded p-1 text-zinc-400 hover:bg-zinc-800 disabled:opacity-30" aria-label={`Move ${story?.title || 'story'} up`}>
                  <ArrowUp className="h-4 w-4" />
                </button>
                <button type="button" disabled={i === stories.length - 1} onClick={() => onChange(move(stories, i, i + 1), true)}
                  className="rounded p-1 text-zinc-400 hover:bg-zinc-800 disabled:opacity-30" aria-label={`Move ${story?.title || 'story'} down`}>
                  <ArrowDown className="h-4 w-4" />
                </button>
                <button type="button" onClick={() => onRemove(s.post_id)}
                  className="rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200" aria-label={`Take ${story?.title || 'story'} out`}>
                  <X className="h-4 w-4" />
                </button>
              </div>
            </li>
          )
        })}
      </ol>
      <button type="button" className={ui.btnGhost} onClick={onAdd} disabled={stories.length >= MAX_STORIES}>
        <Plus className="h-4 w-4" /> Add stories
      </button>
    </section>
  )
}
