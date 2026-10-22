import {
  AlignCenterHorizontal, AlignCenterVertical, AlignEndHorizontal, AlignEndVertical, AlignHorizontalSpaceAround, AlignStartHorizontal,
  AlignStartVertical, AlignVerticalSpaceAround, ArrowDownToLine, ArrowUpToLine, ChevronDown, ChevronUp, Copy, Eye, EyeOff, FlipHorizontal2,
  FlipVertical2, Group, Image as ImageIcon, Italic, Lock, Trash2, Type, Ungroup, Unlock, Square, AlignLeft, AlignCenter, AlignRight,
  AlignJustify, ArrowUpFromLine, ArrowDownFromLine, MoveVertical,
} from 'lucide-react'
import type { FrameKey } from '../canvas/bridge'
import { rtText } from '../canvas/rt'
import { align, boxOf, distribute, patchLayers, setGeometry, topLevel, type AlignHow, type LayerPatch } from '../design/designOps'
import { hasItalic, weightsOf } from '../design/fontStack'
import { BLENDS, MAX_SHADOWS, type Design, type Layer, type PaintedLayer, type Shadow } from '../design/types'
import { AddButton, ColorField, IconBtn, NumberField, PaintField, Row, Section, Seg, Select, Slider } from './controls'
import FontField from './FontField'
import { WEIGHT_NAMES } from './fontPreview'

const BLEND_LABELS: Record<string, string> = {
  normal: 'Normal', multiply: 'Multiply', screen: 'Screen', overlay: 'Overlay', darken: 'Darken', lighten: 'Lighten',
  'color-dodge': 'Colour dodge', 'color-burn': 'Colour burn', 'hard-light': 'Hard light', 'soft-light': 'Soft light',
  difference: 'Difference', exclusion: 'Exclusion', hue: 'Hue', saturation: 'Saturation', color: 'Colour', luminosity: 'Luminosity',
}

const KIND_ICON = { text: Type, image: ImageIcon, shape: Square, group: Group }

/** Everything about the layers selected, in one place: where they sit, their
 *  type, fill, outline, corners, shadows, look, link and order. Several
 *  selected: what they share, plus lining them up. */
export default function LayerInspector({ design, ids, accent, onChange, onCommand, onReplacePicture }: {
  design: Design
  ids: string[]
  accent: string
  /** A change to the design (merged into one undo step while it runs on). */
  onChange: (fn: (d: Design) => Design) => void
  onCommand: (key: FrameKey) => void
  onReplacePicture: (layerId: string) => void
}) {
  const picked = topLevel(design, ids)
  if (!picked.length) return null
  const first = picked[0]
  const single = picked.length === 1
  const paintedOnes = picked.filter((l): l is PaintedLayer => l.kind !== 'group')
  const texts = paintedOnes.filter((l): l is Extract<Layer, { kind: 'text' }> => l.kind === 'text')
  const p0 = paintedOnes[0]
  const patch = (pt: LayerPatch) => onChange((d) => patchLayers(d, ids, pt))
  const geo = (g: Partial<{ x: number; y: number; w: number; h: number; rot: number }>) =>
    onChange((d) => setGeometry(d, [{ id: first.id, ...g }]))
  const box = boxOf(first)
  const Icon = KIND_ICON[first.kind]
  const fixedText = first.kind === 'text' && first.autosize === 'none'

  return (
    <div>
      <div className="flex items-center gap-1.5 border-b border-zinc-800 px-4 py-2.5">
        <Icon className="h-4 w-4 shrink-0 text-zinc-500" />
        {single ? (
          <input aria-label="Layer name" value={first.name} placeholder={first.kind === 'text' ? rtText(first.rt).replace(/\s+/g, ' ').trim().slice(0, 40) || 'Words' : first.kind === 'image' ? 'Picture' : first.kind === 'group' ? 'Group' : 'Shape'}
            onChange={(e) => onChange((d) => patchLayers(d, [first.id], { name: e.target.value.slice(0, 60) } as LayerPatch))}
            className="h-7 min-w-0 flex-1 rounded border border-transparent bg-transparent px-1 text-sm font-medium text-zinc-100 outline-none hover:border-zinc-800 focus:border-emerald-500" />
        ) : <span className="flex-1 text-sm font-medium text-zinc-100">{picked.length} layers</span>}
        <IconBtn title={first.locked ? 'Unlock' : 'Lock'} active={first.locked} onClick={() => patch({ locked: !first.locked })}>
          {first.locked ? <Lock className="h-3.5 w-3.5" /> : <Unlock className="h-3.5 w-3.5" />}
        </IconBtn>
        <IconBtn title={first.hidden ? 'Show' : 'Hide'} active={first.hidden} onClick={() => patch({ hidden: !first.hidden })}>
          {first.hidden ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
        </IconBtn>
        <IconBtn title="Delete (Delete)" onClick={() => onCommand('delete')}><Trash2 className="h-3.5 w-3.5" /></IconBtn>
      </div>

      <Section title={single ? 'Align to the picture' : 'Align'}>
        <div className="flex flex-wrap gap-0.5">
          {([['left', AlignStartVertical, 'Left'], ['center', AlignCenterVertical, 'Centre'], ['right', AlignEndVertical, 'Right'],
            ['top', AlignStartHorizontal, 'Top'], ['middle', AlignCenterHorizontal, 'Middle'], ['bottom', AlignEndHorizontal, 'Bottom']] as const)
            .map(([how, I, label]) => (
              <IconBtn key={how} title={`Align ${label.toLowerCase()}`} onClick={() => onChange((d) => align(d, ids, how as AlignHow))}><I className="h-4 w-4" /></IconBtn>
            ))}
          {picked.length >= 3 && (
            <>
              <IconBtn title="Space evenly across" onClick={() => onChange((d) => distribute(d, ids, 'x'))}><AlignHorizontalSpaceAround className="h-4 w-4" /></IconBtn>
              <IconBtn title="Space evenly down" onClick={() => onChange((d) => distribute(d, ids, 'y'))}><AlignVerticalSpaceAround className="h-4 w-4" /></IconBtn>
            </>
          )}
        </div>
      </Section>

      {single && (
        <Section title="Position">
          <Row>
            <NumberField label="X, percent of the picture's width" short="X" unit="%" value={box.x} min={-100} max={200} step={0.5} onChange={(x) => geo({ x })} />
            <NumberField label="Y, percent of the picture's height" short="Y" unit="%" value={box.y} min={-100} max={200} step={0.5} onChange={(y) => geo({ y })} />
            <NumberField label="Width" short="W" unit="%" value={box.w} min={0.5} max={400} step={0.5} onChange={(w) => geo({ w })} />
            {first.kind === 'text' && !fixedText
              ? <button type="button" onClick={() => patch({ autosize: 'none', h: Math.max(5, box.h) })} title="Give the words a box of fixed height"
                  className="h-7 rounded-md border border-dashed border-zinc-700 text-[11px] text-zinc-400 hover:text-zinc-100">H: grows</button>
              : <NumberField label="Height" short="H" unit="%" value={box.h} min={0.5} max={400} step={0.5} onChange={(h) => geo({ h })} />}
          </Row>
          {first.kind !== 'group' && (
            <div className="flex items-center gap-2">
              <div className="w-28"><NumberField label="Turn" short="⟳" unit="°" value={first.rot} min={-180} max={180} onChange={(rot) => geo({ rot })} /></div>
              <IconBtn title="Flip across" active={first.flip_x} onClick={() => patch({ flip_x: !first.flip_x })}><FlipHorizontal2 className="h-4 w-4" /></IconBtn>
              <IconBtn title="Flip up and down" active={first.flip_y} onClick={() => patch({ flip_y: !first.flip_y })}><FlipVertical2 className="h-4 w-4" /></IconBtn>
              {fixedText && (
                <IconBtn title="Let the box grow with the words" onClick={() => patch({ autosize: 'height' })}><MoveVertical className="h-4 w-4" /></IconBtn>
              )}
            </div>
          )}
        </Section>
      )}

      {texts.length > 0 && texts.length === paintedOnes.length && (() => {
        const t = texts[0]
        return (
          <Section title="Type">
            <FontField value={t.font} onChange={(font) => patch({ font })} />
            <Row>
              <Select label="Weight" value={String(t.weight)} onChange={(w) => patch({ weight: Number(w), italic: t.italic && hasItalic(t.font, Number(w)) })}
                options={weightsOf(t.font).map((w) => ({ key: String(w), label: WEIGHT_NAMES[w] ?? String(w) }))} />
              <div className="flex gap-1">
                <div className="min-w-0 flex-1">
                  <NumberField label="Size, percent of the picture's width" short="Aa" value={t.size} min={0.5} max={60} step={0.1} onChange={(size) => patch({ size })} />
                </div>
                <IconBtn title="Italic" active={t.italic} disabled={!hasItalic(t.font, t.weight)} onClick={() => patch({ italic: !t.italic })}><Italic className="h-3.5 w-3.5" /></IconBtn>
              </div>
            </Row>
            <ColorField label="Text colour" value={t.color} onChange={(color) => patch({ color })} accent={accent} />
            <Row>
              <NumberField label="Line spacing" short="↕" value={t.leading} min={0.6} max={3} step={0.05} places={2} onChange={(leading) => patch({ leading })} />
              <NumberField label="Letter spacing, in ems" short="↔" value={t.tracking} min={-0.2} max={1} step={0.01} places={2} unit="em" onChange={(tracking) => patch({ tracking })} />
            </Row>
            <Seg label="Alignment" value={t.align} onChange={(a) => patch({ align: a })} options={[
              { key: 'left', label: 'Left', icon: <AlignLeft className="h-3.5 w-3.5" /> }, { key: 'center', label: 'Centre', icon: <AlignCenter className="h-3.5 w-3.5" /> },
              { key: 'right', label: 'Right', icon: <AlignRight className="h-3.5 w-3.5" /> }, { key: 'justify', label: 'Justify', icon: <AlignJustify className="h-3.5 w-3.5" /> },
            ]} />
            <Seg label="Capitals" value={t.case} onChange={(c) => patch({ case: c })} options={[
              { key: 'none', label: 'As typed' }, { key: 'upper', label: 'AA' }, { key: 'lower', label: 'aa' }, { key: 'title', label: 'Aa' },
            ]} />
            {t.autosize === 'none' && (
              <Seg label="Where the words sit in the box" value={t.valign} onChange={(v) => patch({ valign: v })} options={[
                { key: 'top', label: 'Top', icon: <ArrowUpFromLine className="h-3.5 w-3.5" /> }, { key: 'middle', label: 'Middle', icon: <MoveVertical className="h-3.5 w-3.5" /> },
                { key: 'bottom', label: 'Bottom', icon: <ArrowDownFromLine className="h-3.5 w-3.5" /> },
              ]} />
            )}
            <NumberField label="Space around the words, inside their fill" short="▢" value={t.pad} min={0} max={20} step={0.1} onChange={(pad) => patch({ pad })} />
            <p className="text-[11px] text-zinc-500">Double-click the words on the page to type. Select words there for bold, italic and links.</p>
          </Section>
        )
      })()}

      {single && first.kind === 'image' && (
        <Section title="Picture">
          <button type="button" onClick={() => onReplacePicture(first.id)}
            className="h-7 w-full rounded-md border border-zinc-800 text-xs text-zinc-200 hover:bg-zinc-800">Replace picture…</button>
          <Row>
            <Select label="Fit" value={first.fit} onChange={(fit) => patch({ fit })} options={[{ key: 'cover', label: 'Fill the box' }, { key: 'contain', label: 'Whole picture' }]} />
            <Select label="Colour" value={first.filter} onChange={(filter) => patch({ filter })} options={[{ key: 'none', label: 'Colour' }, { key: 'bw', label: 'Black & white' }, { key: 'sepia', label: 'Sepia' }]} />
          </Row>
          <Slider label="Zoom" value={first.zoom} min={100} max={400} unit="%" onChange={(zoom) => patch({ zoom })} />
          <Slider label="Focus ←→" value={first.focal.x} min={0} max={100} unit="%" onChange={(x) => patch({ focal: { ...first.focal, x } })} />
          <Slider label="Focus ↑↓" value={first.focal.y} min={0} max={100} unit="%" onChange={(y) => patch({ focal: { ...first.focal, y } })} />
        </Section>
      )}

      {single && first.kind === 'shape' && (
        <Section title="Shape">
          <Seg label="Shape" value={first.shape} onChange={(shape) => patch({ shape })} options={[
            { key: 'rect', label: 'Rectangle' }, { key: 'ellipse', label: 'Ellipse' }, { key: 'line', label: 'Line' },
          ]} />
        </Section>
      )}

      {p0 && p0.kind !== 'image' && !(p0.kind === 'shape' && p0.shape === 'line') && (
        <Section title={p0.kind === 'text' ? 'Fill behind the words' : 'Fill'}>
          <PaintField value={p0.fill} onChange={(fill) => patch({ fill })} accent={accent} />
        </Section>
      )}

      {p0 && (
        <Section title={p0.kind === 'shape' && p0.shape === 'line' ? 'Line' : 'Outline'}>
          <Row>
            <ColorField label="Outline colour" value={p0.stroke.color} onChange={(color) => patch({ stroke: { ...p0.stroke, color } })} accent={accent} />
            <NumberField label="Outline width" short="W" value={p0.stroke.width} min={0} max={10} step={0.1} onChange={(width) => patch({ stroke: { ...p0.stroke, width } })} />
          </Row>
          <Seg label="Outline style" value={p0.stroke.style} onChange={(style) => patch({ stroke: { ...p0.stroke, style } })} options={[
            { key: 'solid', label: 'Solid' }, { key: 'dashed', label: 'Dashed' }, { key: 'dotted', label: 'Dotted' },
          ]} />
        </Section>
      )}

      {p0 && !(p0.kind === 'shape' && p0.shape !== 'rect') && (
        <Section title="Corners">
          <NumberField label="Corner radius" short="◜" value={p0.radius[0]} min={0} max={50} step={0.1}
            onChange={(r) => patch({ radius: [r, r, r, r] })} />
          <Row cols={4}>
            {(['Top left', 'Top right', 'Bottom right', 'Bottom left'] as const).map((label, i) => (
              <NumberField key={label} label={`${label} corner`} short={['◜', '◝', '◞', '◟'][i]} value={p0.radius[i]} min={0} max={50} step={0.1} places={1}
                onChange={(r) => patch({ radius: p0.radius.map((x, j) => (j === i ? r : x)) as [number, number, number, number] })} />
            ))}
          </Row>
        </Section>
      )}

      {p0 && (
        <Section title="Shadows" right={<AddButton label="Add a shadow" disabled={p0.shadows.length >= MAX_SHADOWS}
          onClick={() => patch({ shadows: [...p0.shadows, { inner: false, x: 0, y: 0.4, blur: 1.5, spread: 0, color: '#00000066' }] })} />}>
          {!p0.shadows.length && <p className="text-[11px] text-zinc-500">None. Add a drop shadow{p0.kind === 'shape' ? ' or an inner one' : ''}.</p>}
          {p0.shadows.map((s, i) => {
            const set = (pt: Partial<Shadow>) => patch({ shadows: p0.shadows.map((x, j) => (j === i ? { ...x, ...pt } : x)) })
            return (
              <div key={i} className="space-y-1.5 rounded-md border border-zinc-800 p-2">
                <div className="flex items-center gap-1">
                  {(p0.kind === 'shape' || (p0.kind === 'text' && p0.fill.kind !== 'none'))
                    ? <div className="flex-1"><Seg label="Kind of shadow" value={s.inner ? 'inner' : 'drop'} onChange={(k) => set({ inner: k === 'inner' })}
                        options={[{ key: 'drop', label: 'Drop' }, { key: 'inner', label: 'Inner' }]} /></div>
                    : <span className="flex-1 text-[11px] text-zinc-400">Drop shadow</span>}
                  <IconBtn title="Remove this shadow" onClick={() => patch({ shadows: p0.shadows.filter((_, j) => j !== i) })}><Trash2 className="h-3.5 w-3.5" /></IconBtn>
                </div>
                <Row cols={4}>
                  <NumberField label="Shadow across" short="X" value={s.x} min={-20} max={20} step={0.1} onChange={(x) => set({ x })} />
                  <NumberField label="Shadow down" short="Y" value={s.y} min={-20} max={20} step={0.1} onChange={(y) => set({ y })} />
                  <NumberField label="Shadow blur" short="B" value={s.blur} min={0} max={30} step={0.1} onChange={(blur) => set({ blur })} />
                  <NumberField label="Shadow spread" short="S" value={s.spread} min={-10} max={10} step={0.1} onChange={(spread) => set({ spread })} />
                </Row>
                <ColorField label="Shadow colour" value={s.color} onChange={(color) => set({ color })} accent={accent} />
              </div>
            )
          })}
        </Section>
      )}

      <Section title="Look">
        <Slider label="Opacity" value={first.opacity} min={0} max={100} unit="%" onChange={(opacity) => patch({ opacity })} />
        <Select label="Blend" value={first.blend} onChange={(blend) => patch({ blend })} options={BLENDS.map((b) => ({ key: b, label: `Blend: ${BLEND_LABELS[b]}` }))} />
        {p0 && <Slider label="Blur" value={p0.blur} min={0} max={20} step={0.1} onChange={(blur) => patch({ blur })} />}
      </Section>

      {single && first.kind !== 'group' && (
        <Section title="Link">
          <input aria-label="Where a reader goes when they tap this" value={first.link} placeholder="https://…"
            onChange={(e) => patch({ link: e.target.value.trim().slice(0, 500) })}
            className="h-7 w-full rounded-md border border-zinc-800 bg-zinc-900 px-2 text-xs text-zinc-100 outline-none focus:border-emerald-500" />
          {first.link && !/^(https?:\/\/|mailto:)/i.test(first.link) && <p className="text-[11px] text-amber-400">A link starts with https:// or mailto:</p>}
        </Section>
      )}

      <Section title="Arrange">
        <div className="flex flex-wrap gap-0.5">
          <IconBtn title="Bring to front (⌥⌘])" onClick={() => onCommand('front')}><ArrowUpToLine className="h-4 w-4" /></IconBtn>
          <IconBtn title="Bring forward (⌘])" onClick={() => onCommand('forward')}><ChevronUp className="h-4 w-4" /></IconBtn>
          <IconBtn title="Send backward (⌘[)" onClick={() => onCommand('backward')}><ChevronDown className="h-4 w-4" /></IconBtn>
          <IconBtn title="Send to back (⌥⌘[)" onClick={() => onCommand('back')}><ArrowDownToLine className="h-4 w-4" /></IconBtn>
          <IconBtn title="Duplicate (⌘D)" onClick={() => onCommand('duplicate')}><Copy className="h-4 w-4" /></IconBtn>
          {picked.length > 1 && <IconBtn title="Group (⌘G)" onClick={() => onCommand('group')}><Group className="h-4 w-4" /></IconBtn>}
          {single && first.kind === 'group' && <IconBtn title="Ungroup (⇧⌘G)" onClick={() => onCommand('ungroup')}><Ungroup className="h-4 w-4" /></IconBtn>}
        </div>
      </Section>
    </div>
  )
}
