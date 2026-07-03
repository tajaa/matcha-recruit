import { useState } from 'react'
import { ChevronDown, ChevronUp, Wand2 } from 'lucide-react'
import { DCheck, DColor, DNum, DSelect, GradientPicker, PremiumLock, usePremium } from './DesignPrimitives'
import { ImageInput, VideoInput } from './FieldInputs'
import { dHead, dLabel } from './styles'
import { isOn, obj, str } from './valueHelpers'

export function DesignInspector({ design, onChange }: { design: unknown; onChange: (d: Record<string, unknown>) => void }) {
  const premium = usePremium()
  const [open, setOpen] = useState(false)
  const d = obj(design)
  const motion = obj(d.motion), bg = obj(d.bg), layout = obj(d.layout), colors = obj(d.colors)
  const fx = str(motion.effect) || 'none'
  const hover = str(motion.hover) || 'none'
  const loop = str(motion.loop) || 'none'
  const headingFx = str(motion.heading) || 'none'
  const bgType = str(bg.type) || 'none'
  const patch = (group: string, key: string, value: unknown) =>
    onChange({ ...d, [group]: { ...obj(d[group]), [key]: value } })
  const padOpts: [string, string][] = [['default', 'Default'], ['none', 'None'], ['sm', 'Small'], ['lg', 'Large'], ['xl', 'XL']]

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
                <DSelect label="Reveal on scroll" value={fx} onChange={(v) => patch('motion', 'effect', v)} options={[['none', 'None'], ['fade', 'Fade'], ['slide-up', 'Slide up'], ['slide-down', 'Slide down'], ['slide-left', 'Slide left'], ['slide-right', 'Slide right'], ['zoom', 'Zoom'], ['blur-in', 'Blur in'], ['flip', 'Flip'], ['rotate', 'Rotate in'], ['mask-up', 'Mask up'], ['bounce', 'Bounce']]} />
                {fx !== 'none' && (
                  <div className="grid grid-cols-2 gap-2">
                    <DNum label="Delay (ms)" value={Number(motion.delay) || 0} min={0} max={2000} step={50} onChange={(v) => patch('motion', 'delay', v)} />
                    <DNum label="Duration (ms)" value={Number(motion.duration) || 700} min={100} max={2000} step={50} onChange={(v) => patch('motion', 'duration', v)} />
                  </div>
                )}
                <div className="grid grid-cols-2 gap-2">
                  <DSelect label="Hover effect" value={hover} onChange={(v) => patch('motion', 'hover', v)} options={[['none', 'None'], ['lift', 'Lift'], ['tilt', 'Tilt 3D'], ['glow', 'Glow']]} />
                  <DSelect label="Continuous loop" value={loop} onChange={(v) => patch('motion', 'loop', v)} options={[['none', 'None'], ['float', 'Float'], ['pulse', 'Pulse']]} />
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
              </section>

              <section className="space-y-1.5">
                <p className={dHead}>Colors (this section)</p>
                <DColor label="Text" value={str(colors.text)} onChange={(v) => patch('colors', 'text', v)} />
                <DColor label="Headings" value={str(colors.heading)} onChange={(v) => patch('colors', 'heading', v)} />
                <DColor label="Accent" value={str(colors.accent)} onChange={(v) => patch('colors', 'accent', v)} />
              </section>
            </>
          )}
        </div>
      )}
    </div>
  )
}
