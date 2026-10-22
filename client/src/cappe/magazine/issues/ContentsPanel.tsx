import { ui } from '../../components/ui'
import type { ContentsDesign } from '../../types'
import { CONTENTS_LAYOUTS, LABELS } from './coverVocab'

const HINTS: Record<ContentsDesign['layout'], string> = {
  list: 'Each story on a line, with a small picture.',
  grid: 'Two stories to a row, picture first.',
  feature: 'The first story large, the rest listed under it.',
}

const SHOW: { key: 'show_numbers' | 'show_pictures' | 'show_deks' | 'show_bylines'; label: string }[] = [
  { key: 'show_numbers', label: 'Page numbers' },
  { key: 'show_pictures', label: 'Pictures' },
  { key: 'show_deks', label: 'Each story’s dek (when it has no contents line)' },
  { key: 'show_bylines', label: 'Bylines' },
]

/** The contents page: how it is laid out and what each entry shows. Sections
 *  and each story's line are set on the stories themselves. */
export default function ContentsPanel({ contents, onChange }: {
  contents: ContentsDesign
  onChange: (next: ContentsDesign, step?: boolean) => void
}) {
  const accent = contents.accent === 'accent'
  return (
    <div className="space-y-5">
      <section className={`${ui.card} space-y-3 p-4`} aria-label="Layout">
        <h3 className="text-sm font-medium text-zinc-100">Layout</h3>
        <div className="grid gap-2 sm:grid-cols-3">
          {CONTENTS_LAYOUTS.map((l) => (
            <button key={l} type="button" aria-pressed={contents.layout === l} onClick={() => onChange({ ...contents, layout: l }, true)}
              className={`rounded-lg border p-3 text-left ${contents.layout === l ? 'border-emerald-500' : 'border-zinc-700 hover:bg-zinc-800'}`}>
              <span className={`block text-sm ${contents.layout === l ? 'text-emerald-300' : 'text-zinc-200'}`}>{LABELS.layout[l]}</span>
              <span className="mt-1 block text-xs text-zinc-500">{HINTS[l]}</span>
            </button>
          ))}
        </div>
      </section>
      <section className={`${ui.card} space-y-3 p-4`} aria-label="What it shows">
        <label className="block">
          <span className={ui.label}>Heading</span>
          <input value={contents.heading} maxLength={60} onChange={(e) => onChange({ ...contents, heading: e.target.value })}
            className={ui.input} placeholder="No heading" />
        </label>
        <div className="space-y-2">
          {SHOW.map((s) => (
            <label key={s.key} className="flex items-center gap-2 text-sm text-zinc-300">
              <input type="checkbox" checked={contents[s.key]} onChange={(e) => onChange({ ...contents, [s.key]: e.target.checked }, true)} />
              {s.label}
            </label>
          ))}
        </div>
        <div className="flex items-center gap-3 text-sm text-zinc-300">
          <span>Colour of numbers and sections</span>
          <input type="color" value={accent ? '#888888' : contents.accent} disabled={accent} aria-label="Contents colour"
            onChange={(e) => onChange({ ...contents, accent: e.target.value.toLowerCase() })}
            className="h-8 w-10 rounded border border-zinc-700 bg-zinc-950" />
          <label className="flex items-center gap-1 text-xs text-zinc-400">
            <input type="checkbox" checked={accent} onChange={(e) => onChange({ ...contents, accent: e.target.checked ? 'accent' : '#b45309' }, true)} />
            Magazine accent
          </label>
        </div>
      </section>
    </div>
  )
}
