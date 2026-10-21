import { Link } from 'react-router-dom'
import { Lock } from 'lucide-react'
import type { CappeReaderStoryCard } from '../../types'
import { readerStoryPath } from './readerPaths'

/** A story on the dashboard: its cover, kicker, headline and dek. */
export default function StoryCard({ slug, story, locked = false }: {
  slug: string
  story: CappeReaderStoryCard
  /** A paid story this reader can't read past the paywall yet. */
  locked?: boolean
}) {
  return (
    <Link to={readerStoryPath(slug, story.slug)} className="group block overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900 transition hover:border-zinc-600">
      <div className="aspect-[3/2] bg-zinc-800">
        {story.cover && (
          <img src={story.cover.url} alt={story.cover.alt} loading="lazy" className="h-full w-full object-cover" />
        )}
      </div>
      <div className="p-4">
        <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
          {story.kicker || story.topic}
          {story.access === 'paid' && (
            <span className="inline-flex items-center gap-1 rounded bg-lime-300/10 px-1.5 py-0.5 text-lime-300">
              {locked && <Lock className="h-3 w-3" aria-hidden="true" />}Subscribers
            </span>
          )}
        </p>
        <h3 className="mt-1 font-serif text-lg leading-snug text-zinc-50 group-hover:underline">{story.title}</h3>
        {story.excerpt && <p className="mt-1 line-clamp-2 text-sm text-zinc-400">{story.excerpt}</p>}
        {story.reading_minutes ? <p className="mt-2 text-xs text-zinc-500">{story.reading_minutes} min read</p> : null}
      </div>
    </Link>
  )
}
