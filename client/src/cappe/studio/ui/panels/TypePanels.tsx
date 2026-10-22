import { AlignCenter, AlignJustify, AlignLeft, AlignRight, Underline } from 'lucide-react'
import { hasItalic, weightsOf } from '../../../magazine/design/fontStack'
import FontField from '../../../magazine/workspace/FontField'
import { WEIGHT_NAMES } from '../../../magazine/workspace/fontPreview'
import { ColorField, IconBtn, NumberField, Row, Section, Seg, Select } from '../../../magazine/workspace/controls'
import type { Align, CharAttrs, Role } from '../../model/types'
import { useStudio } from '../../store/store'
import { useCtx, type StudioCtx } from '../context'
import { LengthField, Labeled } from '../fields'
import { currentType, hasTypeTarget, setChar, setPara } from '../typeTarget'

/** Character attributes, then the faces they need loaded before the text is
 *  set again in them. */
function charSetter(c: StudioCtx) {
  return (attrs: CharAttrs) => {
    setChar(c, attrs)
    void c.fonts.ensureDoc(c.store.get().doc).then(() => c.store.recompose(), () => {})
  }
}

const styleKey = (wt: number, it: boolean) => `${wt}|${it ? 1 : 0}`

/** Face, style, size, leading, tracking, colour, underline: of the text
 *  selected (or what the caret will type), else of every word in the text
 *  frames selected. */
export function CharacterPanel() {
  const c = useCtx()
  const s = useStudio(c.store, (x) => x)
  if (!hasTypeTarget(s)) return <Empty title="Character" />
  const { char, para } = currentType(c, s)
  const set = charSetter(c)
  const styles = weightsOf(char.font).flatMap((w) => [
    { key: styleKey(w, false), label: WEIGHT_NAMES[w] ?? String(w) },
    ...(hasItalic(char.font, w) ? [{ key: styleKey(w, true), label: `${WEIGHT_NAMES[w] ?? w} italic` }] : []),
  ])
  return (
    <Section title="Character">
      <FontField value={char.font} roles={false} onChange={(font) => set({ font })} />
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
        <div className="flex items-center justify-end">
          <IconBtn title="Underline" active={char.u} onClick={() => set({ u: !char.u })}><Underline className="h-3.5 w-3.5" /></IconBtn>
        </div>
      </Row>
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
