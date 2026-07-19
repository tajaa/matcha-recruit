import { useState } from 'react'
import { ChevronDown, ChevronUp, Wand2 } from 'lucide-react'
import { DCheck, DColor, DNum, DSelect, GradientPicker, PremiumLock, usePremium } from './DesignPrimitives'
import { ImageInput, VideoInput } from './FieldInputs'
import { StylePresetsPanel } from './StylePresets'
import { dHead, dLabel, inputCls } from './styles'
import { isOn, obj, str } from './valueHelpers'

// Grid-based blocks whose column count is user-controllable. Bento (span layout)
// and logos (flex row) are deliberately excluded — see render.py.
const COLUMN_BLOCKS = new Set(['features', 'gallery', 'pricing', 'testimonial', 'stats', 'credentials', 'reviews', 'menu'])
// slugify for the section anchor (server re-validates with a strict slug regex).
const slugify = (v: string) => v.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 63)

export function DesignInspector({ blockType, design, onChange }: { blockType?: string; design: unknown; onChange: (d: Record<string, unknown>) => void }) {
  const premium = usePremium()
  const [open, setOpen] = useState(false)
  const d = obj(design)
  const motion = obj(d.motion), bg = obj(d.bg), layout = obj(d.layout), colors = obj(d.colors)
  const type = obj(d.type), border = obj(d.border), anchor = obj(d.anchor)
  const image = obj(d.image), divider = obj(d.divider)
  const fx = str(motion.effect) || 'none'
  const hover = str(motion.hover) || 'none'
  const loop = str(motion.loop) || 'none'
  const headingFx = str(motion.heading) || 'none'
  const bgType = str(bg.type) || 'none'
  const patch = (group: string, key: string, value: unknown) =>
    onChange({ ...d, [group]: { ...obj(d[group]), [key]: value } })
  const padOpts: [string, string][] = [['default', 'Default'], ['none', 'None'], ['sm', 'Small'], ['lg', 'Large'], ['xl', 'XL']]
  // Numeric per-section overrides: 0/absent → cleared (byte-identical to unset).
  const numPatch = (group: string, key: string, v: number) => patch(group, key, v ? v : undefined)

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/40">
      <button type="button" onClick={() => setOpen((o) => !o)} className="flex w-full items-center justify-between px-3 py-2 text-xs font-semibold text-zinc-300 hover:text-zinc-100">
        <span className="flex items-center gap-1.5"><Wand2 className="h-3.5 w-3.5 text-amber-400" /> Design</span>
        {open ? <ChevronUp className="h-3.5 w-3.5 text-zinc-500" /> : <ChevronDown className="h-3.5 w-3.5 text-zinc-500" />}
      </button>
      {open && (
        <div className="space-y-4 border-t border-zinc-800 p-3">
          {!premium ? (
            <PremiumLock>Upgrade to Pro to unlock motion, backgrounds, and advanced styling.</PremiumLock>
          ) : (
            <>
              <section className="space-y-2">
                <p className={dHead}>Motion</p>
                <DSelect label="Reveal on scroll" value={fx} onChange={(v) => patch('motion', 'effect', v)} options={[['none', 'None'], ['fade', 'Fade'], ['fade-up', 'Fade up'], ['fade-down', 'Fade down'], ['slide-up', 'Slide up'], ['slide-down', 'Slide down'], ['slide-left', 'Slide left'], ['slide-right', 'Slide right'], ['zoom', 'Zoom'], ['scale-up', 'Scale up'], ['blur-in', 'Blur in'], ['blur-up', 'Blur up'], ['flip', 'Flip'], ['rotate', 'Rotate in'], ['mask-up', 'Mask up'], ['bounce', 'Bounce']]} />
                {fx !== 'none' && (
                  <>
                    <div className="grid grid-cols-2 gap-2">
                      <DNum label="Delay (ms)" value={Number(motion.delay) || 0} min={0} max={2000} step={50} onChange={(v) => patch('motion', 'delay', v)} />
                      <DNum label="Duration (ms)" value={Number(motion.duration) || 700} min={100} max={2000} step={50} onChange={(v) => patch('motion', 'duration', v)} />
                    </div>
                    <DSelect label="Easing" value={str(motion.easing) || 'smooth'} onChange={(v) => patch('motion', 'easing', v)} options={[['smooth', 'Smooth (default)'], ['gentle', 'Gentle'], ['spring', 'Spring'], ['snappy', 'Snappy'], ['linear', 'Linear']]} />
                  </>
                )}
                <div className="grid grid-cols-2 gap-2">
                  <DSelect label="Hover effect" value={hover} onChange={(v) => patch('motion', 'hover', v)} options={[['none', 'None'], ['lift', 'Lift'], ['tilt', 'Tilt 3D'], ['glow', 'Glow'], ['grow', 'Grow'], ['sink', 'Sink']]} />
                  <DSelect label="Continuous loop" value={loop} onChange={(v) => patch('motion', 'loop', v)} options={[['none', 'None'], ['float', 'Float'], ['pulse', 'Pulse'], ['sway', 'Sway'], ['breathe', 'Breathe']]} />
                </div>
                <DSelect label="Heading animation" value={headingFx} onChange={(v) => patch('motion', 'heading', v)} options={[['none', 'None'], ['rise', 'Rise in'], ['shimmer', 'Shimmer']]} />
                <div className="flex flex-wrap gap-x-4 gap-y-1.5">
                  <DCheck label="Stagger children" checked={isOn(motion.stagger)} onChange={(v) => patch('motion', 'stagger', v)} />
                  <DCheck label="Parallax" checked={isOn(motion.parallax)} onChange={(v) => patch('motion', 'parallax', v)} />
                  <DCheck label="Ken Burns" checked={isOn(motion.kenburns)} onChange={(v) => patch('motion', 'kenburns', v)} />
                </div>
                {isOn(motion.parallax) && <DNum label="Parallax strength" value={Number(motion.parallaxStrength) || 20} min={0} max={80} step={5} onChange={(v) => patch('motion', 'parallaxStrength', v)} />}
              </section>

              <section className="space-y-2">
                <p className={dHead}>Background</p>
                <DSelect label="Type" value={bgType} onChange={(v) => patch('bg', 'type', v)} options={[['none', 'None'], ['color', 'Solid color'], ['gradient', 'Gradient'], ['image', 'Image'], ['video', 'Video']]} />
                {bgType === 'color' && <DColor label="Color" value={str(bg.color)} onChange={(v) => patch('bg', 'color', v)} />}
                {bgType === 'gradient' && <GradientPicker value={obj(bg.gradient)} onChange={(g) => patch('bg', 'gradient', g)} />}
                {bgType === 'image' && <div><span className={dLabel}>Image</span><ImageInput value={bg.image} onChange={(v) => patch('bg', 'image', v)} /></div>}
                {bgType === 'video' && <div><span className={dLabel}>Video</span><VideoInput value={bg.video} onChange={(v) => patch('bg', 'video', v)} /></div>}
                {(bgType === 'image' || bgType === 'video') && (
                  <div className="grid grid-cols-2 gap-2">
                    <DSelect label="Overlay" value={str(bg.overlay) || 'none'} onChange={(v) => patch('bg', 'overlay', v)} options={[['none', 'None'], ['light', 'Light'], ['medium', 'Medium'], ['dark', 'Dark']]} />
                    <DNum label="Blur (px)" value={Number(bg.blur) || 0} min={0} max={40} onChange={(v) => patch('bg', 'blur', v)} />
                  </div>
                )}
                <div className="grid grid-cols-2 gap-2">
                  <DSelect label="Pattern" value={str(bg.pattern) || 'none'} onChange={(v) => patch('bg', 'pattern', v)} options={[['none', 'None'], ['dots', 'Dots'], ['grid', 'Grid'], ['diagonal', 'Diagonal lines']]} />
                  <DSelect label="Image filter" value={str(image.filter) || 'none'} onChange={(v) => patch('image', 'filter', v)} options={[['none', 'None'], ['mono', 'Mono'], ['warm', 'Warm'], ['cool', 'Cool'], ['soft', 'Soft'], ['punch', 'Punch']]} />
                </div>
                {str(bg.pattern) && str(bg.pattern) !== 'none' && (
                  <DColor label="Pattern color" value={str(bg.patternColor)} onChange={(v) => patch('bg', 'patternColor', v)} />
                )}
              </section>

              <section className="space-y-2">
                <p className={dHead}>Dividers</p>
                <div className="grid grid-cols-2 gap-2">
                  <DSelect label="Top shape" value={str(divider.top) || 'none'} onChange={(v) => patch('divider', 'top', v)} options={[['none', 'None'], ['wave', 'Wave'], ['slant', 'Slant'], ['curve', 'Curve'], ['peaks', 'Peaks']]} />
                  <DSelect label="Bottom shape" value={str(divider.bottom) || 'none'} onChange={(v) => patch('divider', 'bottom', v)} options={[['none', 'None'], ['wave', 'Wave'], ['slant', 'Slant'], ['curve', 'Curve'], ['peaks', 'Peaks']]} />
                </div>
                {((str(divider.top) && str(divider.top) !== 'none') || (str(divider.bottom) && str(divider.bottom) !== 'none')) && (
                  <div className="grid grid-cols-2 gap-2">
                    <DNum label="Height (px)" value={Number(divider.height) || 64} min={20} max={160} step={4} onChange={(v) => patch('divider', 'height', v)} />
                    <DColor label="Fill color" value={str(divider.color)} onChange={(v) => patch('divider', 'color', v)} />
                  </div>
                )}
                <p className="text-[10px] text-zinc-600">Fill defaults to the page background — matches the neighboring section.</p>
              </section>

              <section className="space-y-2">
                <p className={dHead}>Layout</p>
                <div className="grid grid-cols-2 gap-2">
                  <DSelect label="Padding top" value={str(layout.padTop) || 'default'} onChange={(v) => patch('layout', 'padTop', v)} options={padOpts} />
                  <DSelect label="Padding bottom" value={str(layout.padBottom) || 'default'} onChange={(v) => patch('layout', 'padBottom', v)} options={padOpts} />
                  <DSelect label="Content width" value={str(layout.maxWidth) || 'default'} onChange={(v) => patch('layout', 'maxWidth', v)} options={[['default', 'Default'], ['narrow', 'Narrow'], ['wide', 'Wide'], ['full', 'Full bleed']]} />
                  <DSelect label="Min height" value={str(layout.minHeight) || 'default'} onChange={(v) => patch('layout', 'minHeight', v)} options={[['default', 'Default'], ['tall', 'Tall'], ['screen', 'Full screen']]} />
                </div>
                <DSelect label="Align" value={str(layout.align) || 'default'} onChange={(v) => patch('layout', 'align', v)} options={[['default', 'Default'], ['left', 'Left'], ['center', 'Center']]} />
                <div className="grid grid-cols-2 gap-2">
                  <DNum label="Padding top (px)" value={Number(layout.padTopPx) || 0} min={0} max={400} step={4} onChange={(v) => numPatch('layout', 'padTopPx', v)} />
                  <DNum label="Padding bottom (px)" value={Number(layout.padBottomPx) || 0} min={0} max={400} step={4} onChange={(v) => numPatch('layout', 'padBottomPx', v)} />
                  {COLUMN_BLOCKS.has(blockType || '') && (
                    <DNum label="Columns" value={Number(layout.columns) || 0} min={0} max={6} onChange={(v) => numPatch('layout', 'columns', v)} />
                  )}
                  <DNum label="Item gap (px)" value={Number(layout.gap) || 0} min={0} max={80} step={2} onChange={(v) => numPatch('layout', 'gap', v)} />
                </div>
                <p className="text-[10px] text-zinc-600">px overrides win over the presets above; 0 = use default.</p>
                <div className="space-y-2 rounded-md border border-zinc-800/60 p-2">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-zinc-500">Responsive overrides</p>
                  {([['Md', 'Tablet ≤1024'], ['Sm', 'Mobile ≤640']] as const).map(([bp, label]) => (
                    <div key={bp} className="space-y-1.5">
                      <p className="text-[10px] text-zinc-500">{label}</p>
                      <div className="grid grid-cols-2 gap-2">
                        <DSelect label="Padding top" value={str(layout['padTop' + bp]) || 'default'} onChange={(v) => patch('layout', 'padTop' + bp, v)} options={padOpts} />
                        <DSelect label="Padding bottom" value={str(layout['padBottom' + bp]) || 'default'} onChange={(v) => patch('layout', 'padBottom' + bp, v)} options={padOpts} />
                        <DSelect label="Align" value={str(layout['align' + bp]) || 'default'} onChange={(v) => patch('layout', 'align' + bp, v)} options={[['default', 'Default'], ['left', 'Left'], ['center', 'Center']]} />
                        {COLUMN_BLOCKS.has(blockType || '') && (
                          <DNum label="Columns" value={Number(layout['columns' + bp]) || 0} min={0} max={6} onChange={(v) => numPatch('layout', 'columns' + bp, v)} />
                        )}
                      </div>
                    </div>
                  ))}
                  <p className="text-[10px] text-zinc-600">Default = inherit desktop. Mobile wins over tablet.</p>
                </div>
              </section>

              <section className="space-y-2">
                <p className={dHead}>Type (this section)</p>
                <div className="grid grid-cols-2 gap-2">
                  <DNum label="Heading size (px)" value={Number(type.headingSize) || 0} min={0} max={96} step={2} onChange={(v) => numPatch('type', 'headingSize', v)} />
                  <DNum label="Body size (px)" value={Number(type.bodySize) || 0} min={0} max={28} onChange={(v) => numPatch('type', 'bodySize', v)} />
                </div>
              </section>

              <section className="space-y-1.5">
                <p className={dHead}>Border (this section)</p>
                <div className="flex flex-wrap gap-x-4 gap-y-1.5">
                  <DCheck label="Top rule" checked={isOn(border.top)} onChange={(v) => patch('border', 'top', v)} />
                  <DCheck label="Bottom rule" checked={isOn(border.bottom)} onChange={(v) => patch('border', 'bottom', v)} />
                </div>
                {(isOn(border.top) || isOn(border.bottom)) && (
                  <div className="grid grid-cols-2 gap-2">
                    <DNum label="Width (px)" value={Number(border.width) || 1} min={1} max={8} onChange={(v) => patch('border', 'width', v)} />
                    <DColor label="Color" value={str(border.color)} onChange={(v) => patch('border', 'color', v)} />
                  </div>
                )}
              </section>

              <section className="space-y-1">
                <p className={dHead}>Anchor</p>
                <label className="block">
                  <span className={dLabel}>Link id (for in-page #links)</span>
                  <input type="text" value={str(anchor.id)} placeholder="e.g. pricing"
                    onChange={(e) => patch('anchor', 'id', slugify(e.target.value))}
                    className={`${inputCls} py-1.5`} />
                </label>
              </section>

              <section className="space-y-1.5">
                <p className={dHead}>Colors (this section)</p>
                <DColor label="Text" value={str(colors.text)} onChange={(v) => patch('colors', 'text', v)} />
                <DColor label="Headings" value={str(colors.heading)} onChange={(v) => patch('colors', 'heading', v)} />
                <DColor label="Accent" value={str(colors.accent)} onChange={(v) => patch('colors', 'accent', v)} />
              </section>

              <section className="border-t border-zinc-800 pt-3">
                <StylePresetsPanel
                  kind="section"
                  label="Saved section styles"
                  currentData={d}
                  onApply={(data) => { const next = { ...(data as Record<string, unknown>) }; delete next.anchor; onChange(next) }}
                />
              </section>
            </>
          )}
        </div>
      )}
    </div>
  )
}
