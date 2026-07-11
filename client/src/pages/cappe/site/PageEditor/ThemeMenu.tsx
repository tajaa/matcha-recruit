import { Check, Palette, Sparkles, Wand2 } from 'lucide-react'
import { CAPPE_THEMES, FONT_PAIRINGS, RADII } from '../../../../data/cappeThemes'
import { CappeFontPicker } from './CappeFontPicker'
import { DCheck, DNum, DSelect, GradientPicker, PremiumLock } from './DesignPrimitives'
import { dHead, dLabel, inputCls } from './styles'
import { StylePresetsPanel } from './StylePresets'
import { fontPairId, themeColors, themeFonts, themeObj } from './themeHelpers'
import type { useThemeEditor } from './useThemeEditor'
import { obj, str } from './valueHelpers'

// Global style-system option lists (mirror render.py enum maps; '' = "Default").
const LINEHEIGHT_OPTS: [string, string][] = [['', 'Default'], ['tight', 'Tight'], ['normal', 'Normal'], ['relaxed', 'Relaxed']]
const CONTAINER_OPTS: [string, string][] = [['', 'Default'], ['compact', 'Compact'], ['wide', 'Wide'], ['xwide', 'Extra wide']]
const GUTTER_OPTS: [string, string][] = [['', 'Default'], ['tight', 'Tight'], ['roomy', 'Roomy']]
const SECPAD_OPTS: [string, string][] = [['', 'Default'], ['compact', 'Compact'], ['cozy', 'Cozy'], ['roomy', 'Roomy']]
const GAP_OPTS: [string, string][] = [['', 'Default'], ['tight', 'Tight'], ['roomy', 'Roomy']]
const CARDBD_OPTS: [string, string][] = [['', 'Default'], ['none', 'None'], ['hairline', 'Hairline'], ['bold', 'Bold']]

export function ThemeMenu({ themeEditor, designerUnlocked }: {
  themeEditor: ReturnType<typeof useThemeEditor>
  designerUnlocked: boolean
}) {
  const {
    theme, themeDirty, themeOpen, setThemeOpen, loadTheme, markDirty,
    applyPreset, setBrand, setPairing, setRadius, setMode, setPremium,
    setHeadingFont, setBodyFont, setTypeKey, setStyleKey, setBrandGradient,
  } = themeEditor
  const style = themeObj(theme.style)
  // Number fields show the real CSS default when unset; typing that same default
  // back clears the key so the render stays byte-identical to "no override".
  const numOr = (k: string, def: number) => Number(style[k]) || def
  const setNum = (k: string, v: number, def: number) => setStyleKey(k, v === def ? '' : v)

  return (
    <div className="relative">
      <button
        onClick={() => setThemeOpen((o) => !o)}
        className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium ${themeOpen ? 'border-emerald-500 text-emerald-400' : 'border-zinc-700 text-zinc-300 hover:bg-zinc-800'}`}
      >
        <Palette className="h-4 w-4" /> Theme{themeDirty && <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />}
      </button>
      {themeOpen && (
        <>
          <div className="fixed inset-0 z-20" onClick={() => setThemeOpen(false)} />
          <div className="absolute right-0 z-30 mt-1 max-h-[80vh] w-80 overflow-y-auto rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-2xl shadow-black/50">
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Theme</p>
            <div className="grid grid-cols-3 gap-1.5">
              {CAPPE_THEMES.map((preset) => {
                const active = theme.preset === preset.id
                return (
                  <button
                    key={preset.id}
                    onClick={() => applyPreset(preset.id)}
                    className={`relative overflow-hidden rounded-lg border text-left ${active ? 'border-emerald-500 ring-1 ring-emerald-500' : 'border-zinc-700 hover:border-zinc-500'}`}
                    title={preset.name}
                  >
                    <div className="flex h-9 items-center gap-1 px-1.5" style={{ background: preset.swatch.bg }}>
                      <span className="h-4 w-4 rounded" style={{ background: preset.swatch.brand }} />
                      <span className="h-1.5 flex-1 rounded" style={{ background: preset.swatch.text, opacity: 0.7 }} />
                    </div>
                    <div className="flex items-center justify-between gap-0.5 bg-zinc-950 px-1.5 py-1">
                      <span className="truncate text-[10px] text-zinc-300">{preset.name.split(' ')[0]}</span>
                      {preset.premium ? <Sparkles className="h-2.5 w-2.5 text-amber-400" /> : active ? <Check className="h-2.5 w-2.5 text-emerald-400" /> : null}
                    </div>
                  </button>
                )
              })}
            </div>

            <div className="mt-3 space-y-2.5 border-t border-zinc-800 pt-3">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Tweak</p>

              <div className="flex items-center justify-between">
                <span className="text-xs text-zinc-400">Brand color</span>
                <input
                  type="color"
                  value={themeColors(theme).brand || ((theme.mode as string) === 'dark' ? '#a3e635' : '#10b981')}
                  onChange={(e) => setBrand(e.target.value)}
                  className="h-7 w-12 cursor-pointer rounded border border-zinc-700 bg-transparent"
                />
              </div>

              <div className="flex items-center justify-between gap-2">
                <span className="shrink-0 text-xs text-zinc-400">Fonts</span>
                <select value={fontPairId(theme)} onChange={(e) => setPairing(e.target.value)} className={`${inputCls} py-1.5`}>
                  {FONT_PAIRINGS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                </select>
              </div>

              <div className="flex items-center justify-between gap-2">
                <span className="shrink-0 text-xs text-zinc-400">Corners</span>
                <select value={(theme.radius as string) || 'lg'} onChange={(e) => setRadius(e.target.value)} className={`${inputCls} py-1.5`}>
                  {RADII.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                </select>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-xs text-zinc-400">Mode</span>
                <div className="flex rounded-lg border border-zinc-700 p-0.5">
                  {(['light', 'dark'] as const).map((m) => (
                    <button key={m} onClick={() => setMode(m)} className={`rounded-md px-2.5 py-0.5 text-xs font-medium capitalize ${((theme.mode as string) || 'light') === m ? 'bg-emerald-500 text-zinc-950' : 'text-zinc-400 hover:text-zinc-200'}`}>{m}</button>
                  ))}
                </div>
              </div>
            </div>

            {/* premium designer studio — custom fonts, type, brand gradient */}
            <div className="mt-3 space-y-2.5 border-t border-zinc-800 pt-3">
              <p className={`${dHead} flex items-center gap-1`}><Wand2 className="h-3 w-3 text-amber-400" /> Designer</p>
              {!designerUnlocked ? (
                <PremiumLock>Upgrade to Pro for custom fonts, gradients &amp; motion.</PremiumLock>
              ) : (
                <>
                  <div className="grid grid-cols-2 gap-2">
                    <CappeFontPicker label="Heading font" value={themeFonts(theme).heading || 'Inter'} onChange={setHeadingFont} />
                    <CappeFontPicker label="Body font" value={themeFonts(theme).body || 'Inter'} onChange={setBodyFont} bodyOnly />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <label className="block"><span className={dLabel}>Heading weight</span>
                      <select value={String(themeObj(theme.type).headingWeight ?? '')} onChange={(e) => setTypeKey('headingWeight', e.target.value ? Number(e.target.value) : '')} className={`${inputCls} py-1.5`}>
                        <option value="">Default</option>
                        {([['400', 'Regular'], ['500', 'Medium'], ['600', 'Semibold'], ['700', 'Bold'], ['800', 'Extrabold'], ['900', 'Black']] as [string, string][]).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                      </select></label>
                    <label className="block"><span className={dLabel}>Letter spacing</span>
                      <select value={String(themeObj(theme.type).headingSpacing ?? '')} onChange={(e) => setTypeKey('headingSpacing', e.target.value)} className={`${inputCls} py-1.5`}>
                        <option value="">Default</option>
                        {([['-0.03em', 'Tight'], ['-0.015em', 'Snug'], ['0em', 'Normal'], ['0.04em', 'Wide']] as [string, string][]).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                      </select></label>
                  </div>
                  <label className="block"><span className={dLabel}>Animated headline</span>
                    <select value={String(themeObj(theme.type).heroAnim ?? 'none')} onChange={(e) => setTypeKey('heroAnim', e.target.value)} className={`${inputCls} py-1.5`}>
                      {([['none', 'None'], ['rise', 'Rise in'], ['shimmer', 'Shimmer']] as [string, string][]).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                    </select></label>
                  <DCheck
                    label="Brand gradient buttons"
                    checked={!!obj(obj(theme.colors).brandGradient).stops}
                    onChange={(on) => setBrandGradient(on ? { angle: 135, stops: [themeColors(theme).brand || '#10b981', '#a3e635'] } : null)}
                  />
                  {!!obj(obj(theme.colors).brandGradient).stops && (
                    <GradientPicker value={obj(obj(theme.colors).brandGradient)} onChange={(g) => setBrandGradient(g)} />
                  )}

                  <div className="flex items-center justify-between pt-1">
                    <span className="flex items-center gap-1 text-xs text-zinc-400"><Sparkles className="h-3 w-3 text-amber-400" /> Premium effects</span>
                    <div className="flex rounded-lg border border-zinc-700 p-0.5">
                      {([['On', true], ['Off', false]] as const).map(([label, on]) => (
                        <button key={label} onClick={() => setPremium(on)} className={`rounded-md px-2.5 py-0.5 text-xs font-medium ${!!theme.premium === on ? 'bg-emerald-500 text-zinc-950' : 'text-zinc-400 hover:text-zinc-200'}`}>{label}</button>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </div>

            {/* global style system — spacing / type scale / layout (premium) */}
            <div className="mt-3 space-y-2.5 border-t border-zinc-800 pt-3">
              <p className={`${dHead} flex items-center gap-1`}><Palette className="h-3 w-3 text-amber-400" /> Layout &amp; spacing</p>
              {!designerUnlocked ? (
                <PremiumLock>Upgrade to Pro to tune type scale, spacing rhythm, container width &amp; card styling.</PremiumLock>
              ) : (
                <>
                  <div className="grid grid-cols-2 gap-2">
                    <DNum label="Base font (px)" value={numOr('baseFont', 17)} min={14} max={20} onChange={(v) => setNum('baseFont', v, 17)} />
                    <DSelect label="Line height" value={str(style.lineHeight)} options={LINEHEIGHT_OPTS} onChange={(v) => setStyleKey('lineHeight', v)} />
                    <DSelect label="Container width" value={str(style.container)} options={CONTAINER_OPTS} onChange={(v) => setStyleKey('container', v)} />
                    <DSelect label="Page gutter" value={str(style.gutter)} options={GUTTER_OPTS} onChange={(v) => setStyleKey('gutter', v)} />
                    <DSelect label="Section spacing" value={str(style.sectionPad)} options={SECPAD_OPTS} onChange={(v) => setStyleKey('sectionPad', v)} />
                    <DSelect label="Grid gap" value={str(style.gap)} options={GAP_OPTS} onChange={(v) => setStyleKey('gap', v)} />
                    <DNum label="Card padding (px)" value={numOr('cardPad', 24)} min={8} max={48} step={2} onChange={(v) => setNum('cardPad', v, 24)} />
                    <DSelect label="Card border" value={str(style.cardBorder)} options={CARDBD_OPTS} onChange={(v) => setStyleKey('cardBorder', v)} />
                    <DNum label="Header padding (px)" value={numOr('headerPad', 17)} min={8} max={28} onChange={(v) => setNum('headerPad', v, 17)} />
                    <DNum label="Brand size (px)" value={numOr('brandSize', 19)} min={14} max={32} onChange={(v) => setNum('brandSize', v, 19)} />
                    <DNum label="Footer padding (px)" value={numOr('footerPad', 40)} min={16} max={80} step={2} onChange={(v) => setNum('footerPad', v, 40)} />
                  </div>

                  <div className="border-t border-zinc-800 pt-2.5">
                    <StylePresetsPanel
                      kind="theme"
                      label="Saved themes"
                      currentData={theme}
                      onApply={(data) => { loadTheme({ ...theme, ...data }); markDirty() }}
                    />
                  </div>
                </>
              )}
            </div>
            <p className="mt-3 text-[11px] text-zinc-500">Preview updates live. <span className="text-zinc-300">Save</span> to publish the look.</p>
          </div>
        </>
      )}
    </div>
  )
}
