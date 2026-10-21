import { useState } from 'react'
import { X } from 'lucide-react'
import { ui } from '../../components/ui'
import type { StoryInfo } from './IssueStories'

/** Choose stories to add to the issue. A story already in another issue
 *  can't be chosen (a story is in one issue); archived ones aren't offered. */
export default function StoryPicker({ stories, inIssue, taken, room, onAdd, onClose }: {
  stories: StoryInfo[]
  inIssue: Set<string>
  /** Story id → the number of the other issue it is in. */
  taken: Map<string, number>
  /** How many more the issue can hold. */
  room: number
  onAdd: (ids: string[]) => void
  onClose: () => void
}) {
  const [chosen, setChosen] = useState<string[]>([])
  const offered = stories.filter((s) => s.status !== 'archived' && !inIssue.has(s.id))
  const toggle = (id: string) => setChosen((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]))

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/60 p-4 sm:items-center" role="dialog" aria-label="Add stories">
      <div className={`${ui.card} flex max-h-[85vh] w-full max-w-xl flex-col p-5`}>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium text-zinc-100">Add stories</h2>
          <button type="button" onClick={onClose} className="text-zinc-500 hover:text-zinc-300" aria-label="Close"><X className="h-4 w-4" /></button>
        </div>
        {offered.length === 0
          ? <p className="py-6 text-center text-sm text-zinc-500">Every story is in this issue already. Write another, then add it here.</p>
          : (
            <ul className="-mx-1 flex-1 divide-y divide-zinc-800 overflow-y-auto">
              {offered.map((s) => {
                const other = taken.get(s.id)
                const on = chosen.includes(s.id)
                return (
                  <li key={s.id}>
                    <label className={`flex items-center gap-3 px-1 py-2 ${other ? 'opacity-50' : 'cursor-pointer'}`}>
                      <input type="checkbox" checked={on} disabled={!!other || (!on && chosen.length >= room)} onChange={() => toggle(s.id)} />
                      <div className="h-12 w-9 shrink-0 overflow-hidden rounded bg-zinc-950">
                        {s.cover_image_url && <img src={s.cover_image_url} alt="" className="h-full w-full object-cover" />}
                      </div>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm text-zinc-100">{s.title}</span>
                        <span className="block text-xs text-zinc-500">
                          {other ? `In No. ${other}` : s.status === 'draft' ? 'Draft' : 'Published'}
                          {s.access === 'paid' ? ' · subscribers' : ''}
                        </span>
                      </span>
                    </label>
                  </li>
                )
              })}
            </ul>
          )}
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" className={ui.btnGhost} onClick={onClose}>Cancel</button>
          <button type="button" className={ui.btnPrimary} disabled={!chosen.length} onClick={() => onAdd(chosen)}>
            Add {chosen.length || ''} {chosen.length === 1 ? 'story' : 'stories'}
          </button>
        </div>
      </div>
    </div>
  )
}
