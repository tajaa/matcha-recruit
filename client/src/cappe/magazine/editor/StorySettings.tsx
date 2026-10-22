import { Link } from 'react-router-dom'
import { ui } from '../../components/ui'
import type { CappePost, CappeStoryOptions, StoryLayout } from '../../types'
import type { StoryFields } from '../canvas/storyDoc'

/** A story's topic, layout, status and who can read it. */
export default function StorySettings({ fields, options, isStory, paidOn, siteId, onField, onLayout, narrow = false }: {
  fields: StoryFields
  options: CappeStoryOptions
  isStory: boolean
  /** The magazine takes paid subscribers: a story can only become paid then. */
  paidOn: boolean
  siteId: string
  onField: <K extends keyof StoryFields>(key: K, value: StoryFields[K]) => void
  /** A layout chosen: it may also bring its starter blocks. */
  onLayout: (layout: StoryLayout) => void
  /** One column (the panel beside the page). */
  narrow?: boolean
}) {
  return (
    <>
      <div className={`grid gap-3 ${narrow ? '' : 'sm:grid-cols-3'}`}>
        <label className="text-sm text-zinc-300">Topic
          <select value={fields.topic} onChange={(e) => onField('topic', e.target.value)} className={`${ui.input} mt-1`}>
            <option value="">None</option>
            {options.topics.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
          </select>
        </label>
        <label className="text-sm text-zinc-300">Layout
          <select value={fields.layout} onChange={(e) => onLayout(e.target.value as StoryLayout)} className={`${ui.input} mt-1`} disabled={!isStory}>
            {options.layouts.map((l) => <option key={l.key} value={l.key}>{l.label}</option>)}
          </select>
        </label>
        <label className="text-sm text-zinc-300">Status
          <select value={fields.status} onChange={(e) => onField('status', e.target.value as CappePost['status'])} className={`${ui.input} mt-1`}>
            <option value="draft">Draft</option>
            <option value="published">Published</option>
            <option value="archived">Archived</option>
          </select>
        </label>
      </div>
      {isStory && (
        <label className="block text-sm text-zinc-300">Who can read it
          <select value={fields.access} onChange={(e) => onField('access', e.target.value as CappePost['access'])}
            className={`${ui.input} mt-1 ${narrow ? '' : 'sm:max-w-xs'}`} aria-label="Who can read it">
            <option value="free">Everyone</option>
            <option value="paid" disabled={!paidOn && fields.access !== 'paid'}>Subscribers (after the paywall)</option>
          </select>
          <span className="mt-1 block text-xs text-zinc-500">
            {paidOn
              ? 'Readers see everything above the paywall block (or the first few blocks), then are asked to subscribe.'
              : <>To charge readers, turn on paid subscriptions in <Link to={`/cappe/sites/${siteId}/magazine`} className="underline">Magazine settings</Link>.</>}
          </span>
        </label>
      )}
    </>
  )
}
