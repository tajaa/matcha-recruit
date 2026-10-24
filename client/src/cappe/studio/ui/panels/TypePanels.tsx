import { AlignCenter, AlignJustify, AlignLeft, AlignRight, Underline } from 'lucide-react'
import { hasItalic, weightsOf } from '../../../magazine/design/fontStack'
import FontField from '../../../magazine/workspace/FontField'
import { WEIGHT_NAMES } from '../../../magazine/workspace/fontPreview'
import { ColorField, IconBtn, NumberField, Row, Section, Seg, Select } from '../../../magazine/workspace/controls'
import { CUSTOM_FAMILY, customFamily } from '../../model/doc'
import { LIMITS } from '../../model/limits'
import type { Align, CharAttrs, Role } from '../../model/types'
import { useStudio } from '../../store/store'
import { useCtx, type StudioCtx } from '../context'
import { LengthField, Labeled } from '../fields'
import { currentType, hasTypeTarget, selectedThreads, setChar, setPara } from '../typeTarget'

/** Character attributes, then the faces they need loaded before the text is
 *  set again in them. */
function charSetter(c: StudioCtx) {
  return (attrs: CharAttrs) => {
    setChar(c, attrs)
    void c.fonts.ensureDoc(c.store.get().doc).then(() => c.store.recompose(), () => {})
  }
}

const styleKey = (wt: number, it: boolean) => `${wt}|${it ? 1 : 0}`

/** What each OpenType feature a run may turn on is called (LIMITS.OT_TAGS). */
const OT_NAMES: Record<string, string> = {
  smcp: 'Small caps', c2sc: 'Capitals to small caps', case: 'Case-sensitive forms', titl: 'Titling',
  swsh: 'Swashes', salt: 'Alternates', dlig: 'Rare ligatures', hlig: 'Historical ligatures',
  onum: 'Old-style figures', lnum: 'Lining figures', tnum: 'Tabular figures', pnum: 'Proportional figures',
  frac: 'Fractions', sups: 'Superscript', sinf: 'Inferiors', ordn: 'Ordinals', zero: 'Slashed zero',
  ...Object.fromEntries(Array.from({ length: 20 }, (_, k) => [`ss${String(k + 1).padStart(2, '0')}`, `Set ${k + 1}`])),
}

/** The face's own weights and italics: a catalog font's, or one of the magazine's. */
function stylesOf(font: string): { key: string; label: string }[] {
  const own = CUSTOM_FAMILY.test(font) ? customFamily(font) : undefined
  if (own) {
    return [...own].sort((a, b) => a.weight - b.weight || Number(a.italic) - Number(b.italic))
      .map((f) => ({ key: styleKey(f.weight, f.italic), label: `${WEIGHT_NAMES[f.weight] ?? f.weight}${f.italic ? ' italic' : ''}` }))
  }
  return weightsOf(font).flatMap((w) => [
    { key: styleKey(w, false), label: WEIGHT_NAMES[w] ?? String(w) },
    ...(hasItalic(font, w) ? [{ key: styleKey(w, true), label: `${WEIGHT_NAMES[w] ?? w} italic` }] : []),
  ])
}

/** Face, style, size, leading, tracking, colour, underline: of the text
 *  selected (or what the caret will type), else of every word in the text
 *  frames selected. */
export function CharacterPanel() {
  const c = useCtx()
  const s = useStudio(c.store, (x) => x)
  if (!hasTypeTarget(s)) return <Empty title="Character" />
  const { char, para } = currentType(c, s)
  const set = charSetter(c)
  const styles = stylesOf(char.font)
  const custom = CUSTOM_FAMILY.test(char.font)
  const ownFamilies = [...new Map((s.fonts ?? []).map((f) => [f.family, f.name ?? 'Untitled font'])).entries()]
  const face = c.fonts.book.face(char.font, char.wt, char.it)
  const on = new Set(char.ot ? char.ot.split(',') : [])
  const offered = (LIMITS.OT_TAGS as readonly string[]).filter((t) => face?.features.includes(t) || on.has(t))
  const toggle = (tag: string) => { const next = new Set(on); if (next.has(tag)) next.delete(tag); else next.add(tag); set({ ot: [...next].sort().join(',') }) }
  return (
    <Section title="Character">
      {s.doc.identity && <Select label="Character style" value={s.editing ? c.editor.currentChar().style ?? '' : s.doc.threads.find((t) => t.id === selectedThreads(s)[0])?.paras[0]?.runs[0]?.style ?? ''}
        options={[{ key: '', label: 'No character style (reset)' }, ...s.doc.identity.characters.map((r) => ({ key: r.id, label: r.name }))]}
        onChange={(style) => set({ style })} />}
      <FontField value={custom ? `${customFamily(char.font)?.[0]?.name ?? 'Your font'} (yours)` : char.font} roles={false} onChange={(font) => set({ font })} />
      <div className="flex items-center gap-2">
        {ownFamilies.length > 0 && <div className="min-w-0 flex-1"><Select label="Your fonts" value={custom ? char.font : ''}
          options={[{ key: '', label: 'Your fonts…' }, ...ownFamilies.map(([key, name]) => ({ key, label: name }))]}
          onChange={(font) => font && set({ font })} /></div>}
        <button type="button" onClick={() => c.store.set({ dialog: 'fonts' })}
          className="shrink-0 text-[11px] text-zinc-400 underline-offset-2 hover:text-white hover:underline">{ownFamilies.length ? 'Manage' : 'Add your own font'}</button>
      </div>
      <Select label="Style" value={styleKey(char.wt, char.it)} options={styles}
        onChange={(k) => { const [wt, it] = k.split('|'); set({ wt: Number(wt), it: it === '1' }) }} />
      <Row>
        <NumberField label="Size" short="pt" value={char.size} min={1} max={1296} step={0.5} places={2}
          onChange={(size) => set({ size })} />
        <NumberField label="Leading" short="↕" value={para.lead} min={0} max={2000} step={0.5} places={2} blank="Auto"
          onChange={(lead) => setPara(c, { lead })} />
      </Row>
      <Row>
        <NumberField label="Tracking" short="VA" value={char.track} min={-500} max={2000} step={5} places={0}
          onChange={(track) => set({ track })} />
        <NumberField label="Kerning (⌥← ⌥→ at the caret)" short="AV" value={char.kern} min={LIMITS.KERN_MIN} max={LIMITS.KERN_MAX} step={5} places={0}
          onChange={(kern) => set({ kern })} />
      </Row>
      <div className="flex items-center justify-end">
        <IconBtn title="Underline" active={char.u} onClick={() => set({ u: !char.u })}><Underline className="h-3.5 w-3.5" /></IconBtn>
      </div>
      {offered.length > 0 && <div role="group" aria-label="Alternates and figures" className="space-y-1">
        <p className="text-[11px] text-zinc-500">Alternates and figures</p>
        <div className="flex flex-wrap gap-1">
          {offered.map((tag) => <button key={tag} type="button" aria-pressed={on.has(tag)} title={`${OT_NAMES[tag] ?? tag} (${tag})`}
            onClick={() => toggle(tag)}
            className={`rounded border px-1.5 py-0.5 text-[11px] ${on.has(tag) ? 'border-emerald-500 bg-emerald-500/15 text-emerald-200' : 'border-zinc-700 text-zinc-300 hover:border-zinc-500'}`}>
            {OT_NAMES[tag] ?? tag}</button>)}
        </div>
      </div>}
      <ColorField label="Colour" value={char.color} onChange={(color) => color && set({ color })} />
    </Section>
  )
}

const ALIGNS: { key: Align; label: string; icon: React.ReactNode }[] = [
  { key: 'l', label: 'Align left', icon: <AlignLeft className="h-3.5 w-3.5" /> },
  { key: 'c', label: 'Centre', icon: <AlignCenter className="h-3.5 w-3.5" /> },
  { key: 'r', label: 'Align right', icon: <AlignRight className="h-3.5 w-3.5" /> },
  { key: 'j', label: 'Justify, last line left', icon: <AlignJustify className="h-3.5 w-3.5" /> },
  { key: 'ja', label: 'Justify all lines', icon: <span className="text-[10px] font-semibold">JA</span> },
]

const ROLES: { key: Role; label: string }[] = [
  { key: 'p', label: 'Body text' }, { key: 'h1', label: 'Headline' }, { key: 'h2', label: 'Heading' },
  { key: 'h3', label: 'Subheading' }, { key: 'quote', label: 'Pull quote' }, { key: 'caption', label: 'Caption' },
]

/** Alignment, indents, spacing, and what the paragraph is in the Text view. */
export function ParagraphPanel() {
  const c = useCtx()
  const s = useStudio(c.store, (x) => x)
  if (!hasTypeTarget(s)) return <Empty title="Paragraph" />
  const { para } = currentType(c, s)
  const units = s.doc.units
  return (
    <Section title="Paragraph">
      {s.doc.identity && <Select label="Paragraph style" value={s.editing ? c.editor.currentPara().style ?? '' : s.doc.threads.find((t) => t.id === selectedThreads(s)[0])?.paras[0]?.style ?? ''}
        options={[{ key: '', label: 'No paragraph style (reset)' }, ...s.doc.identity.paragraphs.map((r) => ({ key: r.id, label: r.name }))]}
        onChange={(style) => { setPara(c, { style }); void c.fonts.ensureDoc(c.store.get().doc).then(() => c.store.recompose(), () => {}) }} />}
      <Seg label="Alignment" value={para.align} options={ALIGNS} onChange={(align) => setPara(c, { align })} />
      <Row>
        <Labeled label="Left indent"><LengthField label="Left indent" short="→" units={units} value={para.li} min={0} max={1000}
          onChange={(li) => setPara(c, { li })} /></Labeled>
        <Labeled label="Right indent"><LengthField label="Right indent" short="←" units={units} value={para.ri} min={0} max={1000}
          onChange={(ri) => setPara(c, { ri })} /></Labeled>
      </Row>
      <Row>
        <Labeled label="First line"><LengthField label="First line indent" short="¶" units={units} value={para.fi} min={-1000} max={1000}
          onChange={(fi) => setPara(c, { fi })} /></Labeled>
        <span />
      </Row>
      <Row>
        <Labeled label="Space before"><LengthField label="Space before" short="↑" units={units} value={para.sb} min={0} max={1000}
          onChange={(sb) => setPara(c, { sb })} /></Labeled>
        <Labeled label="Space after"><LengthField label="Space after" short="↓" units={units} value={para.sa} min={0} max={1000}
          onChange={(sa) => setPara(c, { sa })} /></Labeled>
      </Row>
      <Row>
        <Labeled label="Drop cap lines"><Select label="Drop cap" value={String(para.dc)}
          options={[{ key: '0', label: 'No drop cap' }, ...[2, 3, 4, 5, 6].map((n) => ({ key: String(n), label: `${n} lines deep` }))]}
          onChange={(v) => setPara(c, { dc: Number(v) })} /></Labeled>
        <Labeled label="Drop cap letters"><Select label="Drop cap letters" value={String(para.dcn)}
          options={[1, 2, 3].map((n) => ({ key: String(n), label: n === 1 ? '1 letter' : `${n} letters` }))}
          onChange={(v) => setPara(c, { dcn: Number(v) })} /></Labeled>
      </Row>
      <Row cols={3}>
        <Labeled label="Keep last lines"><Select label="Widows: lines kept together at the top of a column" value={String(para.kw)}
          options={[{ key: '1', label: 'Any' }, { key: '2', label: '2' }, { key: '3', label: '3' }]}
          onChange={(v) => setPara(c, { kw: Number(v) })} /></Labeled>
        <Labeled label="Keep first lines"><Select label="Orphans: lines kept together at the foot of a column" value={String(para.ko)}
          options={[{ key: '1', label: 'Any' }, { key: '2', label: '2' }, { key: '3', label: '3' }]}
          onChange={(v) => setPara(c, { ko: Number(v) })} /></Labeled>
        <Labeled label="Last line words"><Select label="Runts: the fewest words on the last line" value={String(para.runt)}
          options={[{ key: '1', label: 'Any' }, { key: '2', label: '2+' }, { key: '3', label: '3+' }]}
          onChange={(v) => setPara(c, { runt: Number(v) })} /></Labeled>
      </Row>
      <Labeled label="In the Text view, this is">
        <Select label="In the Text view" value={para.role} options={ROLES} onChange={(role) => setPara(c, { role })} />
      </Labeled>
    </Section>
  )
}

function Empty({ title }: { title: string }) {
  return (
    <Section title={title}>
      <p className="text-xs leading-relaxed text-zinc-500">Select a text frame, or type in one, to set its type.</p>
    </Section>
  )
}
