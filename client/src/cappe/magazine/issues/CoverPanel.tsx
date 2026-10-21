import { useState, type ReactNode } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { ui } from '../../components/ui'
import type { CappeAsset, CappeMagazineIssueOptions, CoverDesign, CoverElement, CoverLine } from '../../types'
import PictureSlot from '../editor/PictureSlot'
import {
  ALIGNS, BOXES, CASES, CREDIT_CORNERS, FILTERS, FONTS, LABELS, MAX_LINES, MAX_SIZE, MIN_SIZE, MIN_WIDTH, SCRIMS, TONES,
  TRACKINGS, WEIGHTS, ZOOM_MAX, ZOOM_MIN,
} from './coverVocab'
import { applyTemplate, newLine, place, round1 } from './issueDoc'

const small = 'rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-sm text-zinc-100 placeholder:text-zinc-600'
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
  'November', 'December']

type Change = (next: CoverDesign, step?: boolean) => void
export type Selected = 'masthead' | 'issue_line' | number

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="block text-xs text-zinc-400">{label}<div className="mt-1">{children}</div></label>
}

function Slider({ label, value, min, max, step = 0.1, unit = '%', onChange, disabled }: {
  label: string; value: number; min: number; max: number; step?: number; unit?: string
  onChange: (n: number) => void; disabled?: boolean
}) {
  return (
    <label className="block text-xs text-zinc-400">
      <span className="flex justify-between"><span>{label}</span><span className="tabular-nums text-zinc-500">{value}{unit}</span></span>
      <input type="range" min={min} max={max} step={step} value={value} disabled={disabled} aria-label={label}
        onChange={(e) => onChange(round1(Number(e.target.value)))} className="mt-1 w-full accent-emerald-500" />
    </label>
  )
}

function Choice<T extends string>({ label, value, options, names, onChange }: {
  label: string; value: T; options: readonly T[]; names: Record<T, string>; onChange: (v: T) => void
}) {
  return (
    <Field label={label}>
      <select value={value} onChange={(e) => onChange(e.target.value as T)} className={`${small} w-full`} aria-label={label}>
        {options.map((o) => <option key={o} value={o}>{names[o]}</option>)}
      </select>
    </Field>
  )
}

/** A colour, or the magazine's accent colour. */
function Colour({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const accent = value === 'accent'
  return (
    <Field label={label}>
      <div className="flex items-center gap-2">
        <input type="color" value={accent ? '#888888' : value} disabled={accent} aria-label={label}
          onChange={(e) => onChange(e.target.value.toLowerCase())} className="h-8 w-10 rounded border border-zinc-700 bg-zinc-950" />
        <label className="flex items-center gap-1 text-xs text-zinc-400">
          <input type="checkbox" checked={accent} onChange={(e) => onChange(e.target.checked ? 'accent' : '#ffffff')} />
          Magazine accent
        </label>
      </div>
    </Field>
  )
}

/** Where an element sits and how its words look. */
function ElementControls<T extends CoverElement>({ el, onChange }: { el: T; onChange: (next: T) => void }) {
  const set = (change: Partial<CoverElement>) => onChange({ ...el, ...change })
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-3">
        <Slider label="Across" value={el.x} min={0} max={round1(100 - el.w)} onChange={(x) => onChange(place(el, { x }))} />
        <Slider label="Down" value={el.y} min={0} max={100} onChange={(y) => onChange(place(el, { y }))} />
        <Slider label="Width" value={el.w} min={MIN_WIDTH} max={100} onChange={(w) => onChange(place(el, { w }))} />
      </div>
      <Slider label="Size" value={el.size} min={MIN_SIZE} max={MAX_SIZE} unit="" onChange={(size) => set({ size })} />
      <div className="grid gap-3 sm:grid-cols-3">
        <Colour label="Colour" value={el.color} onChange={(color) => set({ color })} />
        <Choice label="Align" value={el.align} options={ALIGNS} names={LABELS.align} onChange={(align) => set({ align })} />
        <Choice label="Weight" value={el.weight} options={WEIGHTS} names={LABELS.weight} onChange={(weight) => set({ weight })} />
        <Choice label="Letters" value={el.case} options={CASES} names={LABELS.case} onChange={(c) => set({ case: c })} />
        <Choice label="Spacing" value={el.tracking} options={TRACKINGS} names={LABELS.tracking} onChange={(tracking) => set({ tracking })} />
        <Choice label="Face" value={el.font} options={FONTS} names={LABELS.font} onChange={(font) => set({ font })} />
      </div>
      <label className="flex items-center gap-2 text-xs text-zinc-400">
        <input type="checkbox" checked={el.italic} onChange={(e) => set({ italic: e.target.checked })} /> Italic
      </label>
    </div>
  )
}

type Common = { cover: CoverDesign; onChange: Change }

/** Start from a template: the photo and the words stay. */
export function TemplateSection({ cover, templates, name, onChange }: Common & {
  templates: CappeMagazineIssueOptions['templates']
  name: string
}) {
  return (
    <section className={`${ui.card} space-y-3 p-4`} aria-label="Template">
      <h3 className="text-sm font-medium text-zinc-100">Start from a template</h3>
      <p className="text-xs text-zinc-500">Your photo and words stay; they move into the template’s places.</p>
      <div className="flex flex-wrap gap-2">
        {templates.map((t) => (
          <button key={t.key} type="button" aria-pressed={cover.template === t.key}
            onClick={() => onChange(applyTemplate(cover, t, name), true)}
            className={`rounded-lg border px-3 py-1.5 text-sm ${cover.template === t.key ? 'border-emerald-500 text-emerald-300' : 'border-zinc-700 text-zinc-300 hover:bg-zinc-800'}`}>
            {t.label}
          </button>
        ))}
      </div>
    </section>
  )
}

/** The photo, the darkening behind the words and the background. */
export function PhotoSection({ cover, assets, onChange, onPickPhoto, focusHint = false }: Common & {
  assets: Map<string, CappeAsset>
  onPickPhoto: () => void
  /** On the page, the focus is dragged: say so. */
  focusHint?: boolean
}) {
  const photo = cover.photo
  const setPhoto = (change: Partial<CoverDesign['photo']>) => onChange({ ...cover, photo: { ...photo, ...change } })
  return (
    <section className={`${ui.card} space-y-3 p-4`} aria-label="Photo">
      <h3 className="text-sm font-medium text-zinc-100">Photo</h3>
      <PictureSlot assetId={photo.asset_id} assets={assets} label="Cover photo" onPick={onPickPhoto}
        onClear={() => setPhoto({ asset_id: null })} />
      {focusHint && <p className="text-xs text-zinc-500">Drag the dot on the cover to choose what the photo keeps in view.</p>}
      <div className="grid gap-3 sm:grid-cols-2">
        <Slider label="Focus across" value={photo.focal.x} min={0} max={100} step={1}
          onChange={(x) => setPhoto({ focal: { ...photo.focal, x: Math.round(x) } })} disabled={!photo.asset_id} />
        <Slider label="Focus down" value={photo.focal.y} min={0} max={100} step={1}
          onChange={(y) => setPhoto({ focal: { ...photo.focal, y: Math.round(y) } })} disabled={!photo.asset_id} />
        <Slider label="Zoom" value={photo.zoom} min={ZOOM_MIN} max={ZOOM_MAX} step={1}
          onChange={(zoom) => setPhoto({ zoom: Math.round(zoom) })} disabled={!photo.asset_id} />
        <Choice label="Colour" value={photo.filter} options={FILTERS} names={LABELS.filter} onChange={(filter) => setPhoto({ filter })} />
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <Choice label="Darken behind the words" value={cover.scrim.kind} options={SCRIMS} names={LABELS.scrim}
          onChange={(kind) => onChange({ ...cover, scrim: { ...cover.scrim, kind } })} />
        <Slider label="How dark" value={cover.scrim.strength} min={0} max={90} step={1} disabled={cover.scrim.kind === 'none'}
          onChange={(strength) => onChange({ ...cover, scrim: { ...cover.scrim, strength: Math.round(strength) } })} />
        <Colour label="Background" value={cover.background} onChange={(background) => onChange({ ...cover, background })} />
      </div>
    </section>
  )
}

/** One of the cover's words: the masthead, the issue line or a cover line,
 *  its words (unless typed on the page), place and look. */
export function CoverElementSection({ cover, which, stories, name, number, onChange, onRemoveLine, words = true }: Common & {
  which: Selected
  stories: { id: string; title: string }[]
  name: string
  number: number
  onRemoveLine: (i: number) => void
  /** The boxes its words are typed in (not on the page, where they're typed on it). */
  words?: boolean
}) {
  const setLine = (i: number, next: CoverLine) => onChange({ ...cover, lines: cover.lines.map((ln, j) => (j === i ? next : ln)) })
  const now = new Date()
  const issueLine = `No. ${number} · ${MONTHS[now.getMonth()]} ${now.getFullYear()}`
  if (which === 'masthead') {
    return (
      <>
        <p className="text-xs text-zinc-500">The magazine’s name, “{name}”. Change it in Magazine settings.</p>
        <ElementControls el={cover.masthead} onChange={(masthead) => onChange({ ...cover, masthead })} />
      </>
    )
  }
  if (which === 'issue_line') {
    return (
      <>
        <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
          {words && (
            <Field label="Words">
              <input value={cover.issue_line.text} maxLength={80} placeholder={issueLine} className={`${small} w-full`}
                aria-label="Issue line words"
                onChange={(e) => onChange({ ...cover, issue_line: { ...cover.issue_line, text: e.target.value } })} />
            </Field>
          )}
          <label className="flex items-center gap-2 pb-2 text-xs text-zinc-400">
            <input type="checkbox" checked={cover.issue_line.hidden}
              onChange={(e) => onChange({ ...cover, issue_line: { ...cover.issue_line, hidden: e.target.checked } })} /> Hide it
          </label>
        </div>
        <ElementControls el={cover.issue_line} onChange={(issue_line) => onChange({ ...cover, issue_line })} />
      </>
    )
  }
  const line = cover.lines[which]
  if (!line) return null
  return (
    <>
      {words && (
        <Field label="Words">
          <input value={line.text} maxLength={140} className={`${small} w-full`} aria-label="Cover line words"
            onChange={(e) => setLine(which, { ...line, text: e.target.value })} />
        </Field>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        {words && (
          <Field label="A smaller line under it">
            <input value={line.sub} maxLength={200} className={`${small} w-full`} aria-label="Smaller line"
              onChange={(e) => setLine(which, { ...line, sub: e.target.value })} />
          </Field>
        )}
        <Field label="Opens the story">
          <select value={line.post_id || ''} className={`${small} w-full`} aria-label="Opens the story"
            onChange={(e) => setLine(which, { ...line, post_id: e.target.value || null })}>
            <option value="">None</option>
            {stories.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
          </select>
        </Field>
      </div>
      <ElementControls el={line} onChange={(next) => setLine(which, next)} />
      <div className="grid gap-3 sm:grid-cols-3">
        <Choice label="Box behind it" value={line.box} options={BOXES} names={{ none: 'None', solid: 'Solid' }}
          onChange={(box) => setLine(which, { ...line, box })} />
        {line.box === 'solid' && <Colour label="Box colour" value={line.box_color} onChange={(box_color) => setLine(which, { ...line, box_color })} />}
      </div>
      <button type="button" onClick={() => onRemoveLine(which)} className={`inline-flex items-center gap-2 text-xs ${ui.danger}`}>
        <Trash2 className="h-3.5 w-3.5" /> Remove this line
      </button>
    </>
  )
}

/** Where the photo credit goes and its tone. */
export function CreditSection({ cover, onChange }: Common) {
  return (
    <section className={`${ui.card} space-y-3 p-4`} aria-label="Photo credit">
      <h3 className="text-sm font-medium text-zinc-100">Photo credit</h3>
      <p className="text-xs text-zinc-500">Always printed on the cover, from the picture’s library entry.</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Choice label="Corner" value={cover.credit.corner} options={CREDIT_CORNERS} names={LABELS.corner}
          onChange={(corner) => onChange({ ...cover, credit: { ...cover.credit, corner } })} />
        <Choice label="Tone" value={cover.credit.tone} options={TONES} names={LABELS.tone}
          onChange={(tone) => onChange({ ...cover, credit: { ...cover.credit, tone } })} />
      </div>
    </section>
  )
}

/** The cover: start from a template, then the photo, the darkening behind
 *  the words, and each element's words, place and look. The preview shows
 *  it as readers will. */
export default function CoverPanel({ cover, templates, assets, stories, name, number, onChange, onPickPhoto }: {
  cover: CoverDesign
  templates: CappeMagazineIssueOptions['templates']
  assets: Map<string, CappeAsset>
  /** The issue's stories, for a cover line to link to. */
  stories: { id: string; title: string }[]
  /** The magazine's name: the masthead. */
  name: string
  number: number
  onChange: Change
  onPickPhoto: () => void
}) {
  const [selected, setSelected] = useState<Selected>('masthead')
  const pick = typeof selected === 'number' && !cover.lines[selected] ? 'masthead' : selected

  const addLine = () => {
    const line = newLine(cover)
    if (!line) return
    onChange({ ...cover, lines: [...cover.lines, line] }, true)
    setSelected(cover.lines.length)
  }
  const removeLine = (i: number) => {
    onChange({ ...cover, lines: cover.lines.filter((_, j) => j !== i) }, true)
    setSelected('masthead')
  }

  return (
    <div className="space-y-5">
      <TemplateSection cover={cover} templates={templates} name={name} onChange={onChange} />
      <PhotoSection cover={cover} assets={assets} onChange={onChange} onPickPhoto={onPickPhoto} />

      <section className={`${ui.card} space-y-4 p-4`} aria-label="Words">
        <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Cover words">
          {(['masthead', 'issue_line', ...cover.lines.map((_, i) => i)] as Selected[]).map((key) => {
            const label = key === 'masthead' ? 'Masthead' : key === 'issue_line' ? 'Issue line'
              : cover.lines[key as number].text || `Line ${(key as number) + 1}`
            return (
              <button key={String(key)} type="button" role="tab" aria-selected={pick === key} onClick={() => setSelected(key)}
                className={`max-w-[11rem] truncate rounded-lg px-2.5 py-1 text-xs ${pick === key ? 'bg-emerald-500/15 text-emerald-300' : 'text-zinc-400 hover:bg-zinc-800'}`}>
                {label}
              </button>
            )
          })}
          <button type="button" onClick={addLine} disabled={cover.lines.length >= MAX_LINES}
            className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs text-zinc-400 hover:bg-zinc-800 disabled:opacity-40">
            <Plus className="h-3.5 w-3.5" /> Cover line
          </button>
        </div>
        <CoverElementSection cover={cover} which={pick} stories={stories} name={name} number={number} onChange={onChange}
          onRemoveLine={removeLine} />
      </section>

      <CreditSection cover={cover} onChange={onChange} />
    </div>
  )
}
