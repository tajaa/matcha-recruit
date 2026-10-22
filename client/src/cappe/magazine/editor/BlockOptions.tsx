import { AlignCenter, AlignJustify, AlignLeft, AlignRight, ImagePlus, Trash2 } from 'lucide-react'
import type { CappeAsset, StoryBlock } from '../../types'
import { ColorField, IconBtn, NumberField, Row, Section, Seg, Select, Slider } from '../workspace/controls'
import FontField from '../workspace/FontField'
import PictureSlot from './PictureSlot'
import CropTool from './CropTool'

type Text = Extract<StoryBlock, { type: 'text' }>

const hint = 'text-[11px] leading-relaxed text-zinc-500'

/** A text block's type: its face, size, colour and line spacing (each
 *  following the magazine until set), its style, alignment and drop cap. */
function TextOptions({ block, accent, onChange }: { block: Text; accent?: string; onChange: (b: StoryBlock) => void }) {
  const set = (patch: Partial<Text>) => onChange({ ...block, ...patch })
  return (
    <>
      <Section title="Type">
        <FontField value={block.font || 'body'} onChange={(font) => set({ font })} />
        <Row>
          <NumberField label="Size, times the story's" short="×" value={block.size ?? 1} min={0.6} max={3} step={0.05} places={2}
            onChange={(size) => set({ size })} />
          <NumberField label="Line spacing" short="↕" value={block.leading || 1.6} blank={block.leading ? undefined : 'Auto'}
            min={0.9} max={3} step={0.05} places={2} onChange={(leading) => set({ leading })} />
        </Row>
        <ColorField label="Colour" value={block.color || ''} auto="Page ink" accent={accent} onChange={(color) => set({ color })} />
        <Seg label="Align" value={block.align || 'left'} onChange={(align) => set({ align })} options={[
          { key: 'left', label: 'Left', icon: <AlignLeft className="h-3.5 w-3.5" /> },
          { key: 'center', label: 'Centred', icon: <AlignCenter className="h-3.5 w-3.5" /> },
          { key: 'right', label: 'Right', icon: <AlignRight className="h-3.5 w-3.5" /> },
          { key: 'justify', label: 'Justified', icon: <AlignJustify className="h-3.5 w-3.5" /> },
        ]} />
        {block.leading ? (
          <button type="button" className="text-[11px] text-zinc-400 hover:text-zinc-100" onClick={() => set({ leading: 0 })}>Line spacing back to automatic</button>
        ) : null}
      </Section>
      <Section title="Paragraphs">
        <Select label="Style" value={block.variant || 'body'} onChange={(variant) => set({ variant })} options={[
          { key: 'body', label: 'Paragraphs' }, { key: 'lede', label: 'Lede (larger opening)' },
          { key: 'statement', label: 'Statement (big, in the headline type)' }, { key: 'small', label: 'Small print' },
        ]} />
        <label className="flex items-center gap-2 text-xs text-zinc-300">
          <input type="checkbox" checked={block.dropcap} onChange={(e) => set({ dropcap: e.target.checked })} /> Drop cap
        </label>
      </Section>
    </>
  )
}

/** A block's settings beside the page: its pictures, its type and how it
 *  looks (its words are typed on the page itself). */
export default function BlockOptions({ block, assets, accent, onChange, onPickAsset }: {
  block: StoryBlock
  assets: Map<string, CappeAsset>
  accent?: string
  onChange: (block: StoryBlock) => void
  /** Open the picker; `done(asset)` is called with the choice. */
  onPickAsset: (done: (asset: CappeAsset) => void) => void
}) {
  switch (block.type) {
    case 'cover':
      return (
        <Section title="Picture and headline">
          <PictureSlot assetId={block.asset_id} assets={assets} label="Cover picture"
            onPick={() => onPickAsset((a) => onChange({ ...block, asset_id: a.id }))}
            onClear={() => onChange({ ...block, asset_id: null })} />
          <Select label="Style" value={block.style} onChange={(style) => onChange({ ...block, style })} options={[
            { key: 'overlay', label: 'Headline over the picture' }, { key: 'stacked', label: 'Headline, then the picture' },
            { key: 'split', label: 'Side by side' },
          ]} />
          {block.style === 'overlay' && (
            <Select label="Headline colour" value={block.tone} onChange={(tone) => onChange({ ...block, tone })}
              options={[{ key: 'light', label: 'White on dark' }, { key: 'dark', label: 'Dark on light' }]} />
          )}
          {block.style !== 'stacked' && (
            <>
              <Slider label="Focus →" value={block.focal.x} min={0} max={100} unit="%" onChange={(x) => onChange({ ...block, focal: { ...block.focal, x } })} />
              <Slider label="Focus ↓" value={block.focal.y} min={0} max={100} unit="%" onChange={(y) => onChange({ ...block, focal: { ...block.focal, y } })} />
            </>
          )}
          <p className={hint}>Type the kicker, headline, dek and byline on the page. Drag the dot on the picture to choose what it keeps in view.</p>
        </Section>
      )
    case 'text':
      return <TextOptions block={block} accent={accent} onChange={onChange} />
    case 'photo':
      return (
        <Section title="Picture">
          <PictureSlot assetId={block.asset_id} assets={assets}
            onPick={() => onPickAsset((a) => onChange({ ...block, asset_id: a.id }))}
            onClear={() => onChange({ ...block, asset_id: null })} />
          <Select label="Size" value={block.size} onChange={(size) => onChange({ ...block, size })} options={[
            { key: 'column', label: 'Column width' }, { key: 'wide', label: 'Wide' }, { key: 'full', label: 'Edge to edge' },
          ]} />
          {block.asset_id && assets.get(block.asset_id) && <CropTool block={block} asset={assets.get(block.asset_id)!} onChange={onChange} />}
          <p className={hint}>Type the caption under the picture on the page. The credit comes from the library.</p>
        </Section>
      )
    case 'photos':
      return (
        <Section title="Pictures">
          <Select label="Arrangement" value={block.layout} onChange={(layout) => onChange({ ...block, layout })} options={[
            { key: 'pair', label: 'Pair' }, { key: 'trio', label: 'Trio' }, { key: 'grid', label: 'Grid' }, { key: 'mosaic', label: 'Mosaic' },
          ]} />
          {block.items.map((item, i) => (
            <div key={i} className="flex items-center gap-2">
              <div className="min-w-0 flex-1">
                <PictureSlot assetId={item.asset_id} assets={assets} label={`Picture ${i + 1}`}
                  onPick={() => onPickAsset((a) => onChange({ ...block, items: block.items.map((x, j) => (j === i ? { ...x, asset_id: a.id } : x)) }))}
                  onClear={() => onChange({ ...block, items: block.items.map((x, j) => (j === i ? { ...x, asset_id: null } : x)) })} />
              </div>
              <IconBtn title={`Remove picture ${i + 1}`} onClick={() => onChange({ ...block, items: block.items.filter((_, j) => j !== i) })}>
                <Trash2 className="h-3.5 w-3.5" />
              </IconBtn>
            </div>
          ))}
          {block.items.length < 12 && (
            <button type="button" className="inline-flex items-center gap-1.5 text-xs text-zinc-300 hover:text-zinc-50"
              onClick={() => onChange({ ...block, items: [...block.items, { asset_id: null, caption: '' }] })}>
              <ImagePlus className="h-3.5 w-3.5" /> Add a picture
            </button>
          )}
        </Section>
      )
    case 'quote':
      return (
        <Section title="Look">
          <Select label="Quote style" value={block.style} onChange={(style) => onChange({ ...block, style })}
            options={[{ key: 'big', label: 'Big, centred' }, { key: 'side', label: 'Ruled, in the column' }]} />
          <p className={hint}>Type the words and who said them on the page.</p>
        </Section>
      )
    case 'sidebar':
      return <Section title="About"><p className={hint}>A box beside the story. Type its title and words on the page.</p></Section>
    case 'qa':
      return (
        <Section title="Questions">
          {block.items.map((item, i) => (
            <div key={i} className="flex items-center gap-2 text-xs text-zinc-300">
              <span className="min-w-0 flex-1 truncate">{item.q || `Question ${i + 1}`}</span>
              <IconBtn title={`Remove question ${i + 1}`} onClick={() => onChange({ ...block, items: block.items.filter((_, j) => j !== i) })}>
                <Trash2 className="h-3.5 w-3.5" />
              </IconBtn>
            </div>
          ))}
          {block.items.length < 40 && (
            <button type="button" className="text-xs text-zinc-300 hover:text-zinc-50" onClick={() => onChange({ ...block, items: [...block.items, { q: '', a_md: '' }] })}>
              Add a question
            </button>
          )}
        </Section>
      )
    case 'divider':
      return <Section title="About"><p className={hint}>A short rule between parts of the story.</p></Section>
    case 'paywall':
      return <Section title="About"><p className={hint}>Everything below this line is for subscribers, when the story is set to “Subscribers”. Readers see what’s above it free.</p></Section>
    case 'page':
      // Its shape and background are the art inspector's (workspace/ArtInspector).
      return null
  }
}
