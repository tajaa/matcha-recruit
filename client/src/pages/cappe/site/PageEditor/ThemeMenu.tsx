import { useEffect, useRef } from 'react'
import { Check, Palette, Sparkles, Wand2, X } from 'lucide-react'
import { CAPPE_THEMES, FONT_PAIRINGS, RADII } from '../../../../data/cappeThemes'
import { CappeFontPicker } from './CappeFontPicker'
import { DCheck, DNum, DSelect, GradientPicker, PremiumLock } from './DesignPrimitives'
import { dHead, dLabel, inputCls } from './styles'
import { StylePresetsPanel } from './StylePresets'
import { fontPairId, themeColors, themeFonts, themeObj } from './themeHelpers'
import type { ThemeRegion } from './useThemeBridge'
import type { useThemeEditor } from './useThemeEditor'
import { obj, str } from './valueHelpers'

export type ThemeBridgeApi = { highlightRegion: (r: ThemeRegion) => void; clearHighlight: () => void }

/** Wraps a control group so hovering/focusing it highlights the region of the
 *  live preview it governs (see useThemeBridge). Purely presentational — no-op
 *  if no bridge is wired. */
function Hl({ region, bridge, children }: { region: ThemeRegion; bridge?: ThemeBridgeApi; children: React.ReactNode }) {
  if (!bridge) return <>{children}</>
  return (
    <div
      data-theme-region={region}
      className="rounded-lg transition-shadow"
      onMouseEnter={() => bridge.highlightRegion(region)}
      onMouseLeave={() => bridge.clearHighlight()}
      onFocus={() => bridge.highlightRegion(region)}
      onBlur={() => bridge.clearHighlight()}
    >
      {children}
    </div>
  )
}

// Global style-system option lists (mirror render.py enum maps; '' = "Default").
const LINEHEIGHT_OPTS: [string, string][] = [['', 'Default'], ['tight', 'Tight'], ['normal', 'Normal'], ['relaxed', 'Relaxed']]
const CONTAINER_OPTS: [string, string][] = [['', 'Default'], ['compact', 'Compact'], ['wide', 'Wide'], ['xwide', 'Extra wide']]
const GUTTER_OPTS: [string, string][] = [['', 'Default'], ['tight', 'Tight'], ['roomy', 'Roomy']]
const SECPAD_OPTS: [string, string][] = [['', 'Default'], ['compact', 'Compact'], ['cozy', 'Cozy'], ['roomy', 'Roomy']]
const GAP_OPTS: [string, string][] = [['', 'Default'], ['tight', 'Tight'], ['roomy', 'Roomy']]
const CARDBD_OPTS: [string, string][] = [['', 'Default'], ['none', 'None'], ['hairline', 'Hairline'], ['bold', 'Bold']]

/** Toolbar toggle only — the drawer itself is `ThemeDrawer`, rendered by
 *  index.tsx as a flex sibling of the preview (not here) so its width
 *  composes into the layout instead of overlaying it. */
export function ThemeMenu({ themeEditor }: { themeEditor: ReturnType<typeof useThemeEditor> }) {
  const { themeOpen, setThemeOpen, themeDirty } = themeEditor
  return (
    <button
      onClick={() => setThemeOpen((o) => !o)}
      className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium ${themeOpen ? 'border-emerald-500 text-emerald-400' : 'border-zinc-700 text-zinc-300 hover:bg-zinc-800'}`}
    >
      <Palette className="h-4 w-4" /> Theme{themeDirty && <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />}
    </button>
  )
}

export function ThemeDrawer({ themeEditor, designerUnlocked, bridge, probe }: {
  themeEditor: ReturnType<typeof useThemeEditor>
  designerUnlocked: boolean
  bridge?: ThemeBridgeApi
  /** Last page-click probe from the preview (n makes repeat clicks re-fire). */
  probe?: { region: ThemeRegion; n: number } | null
}) {
  const {
    theme, themeOpen, setThemeOpen, loadTheme, markDirty,
    applyPreset, setBrand, setPairing, setRadius, setMode, setPremium,
    setHeadingFont, setBodyFont, setTypeKey, setStyleKey, setBrandGradient,
  } = themeEditor
  const style = themeObj(theme.style)
  // Number fields show the real CSS default when unset; typing that same default
  // back clears the key so the render stays byte-identical to "no override".
  const numOr = (k: string, def: number) => Number(style[k]) || def
  const setNum = (k: string, v: number, def: number) => setStyleKey(k, v === def ? '' : v)

  // Close the drawer on Escape.
  useEffect(() => {
    if (!themeOpen) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setThemeOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [themeOpen, setThemeOpen])

  // Reverse sync: a page click probed a region → scroll its control into view,
  // flash it, and light up the full region in the preview so the mapping reads
  // both ways.
  const drawerRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!probe) return
    const el = drawerRef.current?.querySelector(`[data-theme-region="${probe.region}"]`)
    el?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    el?.classList.add('ring-2', 'ring-emerald-500')
    bridge?.highlightRegion(probe.region)
    const t = setTimeout(() => { el?.classList.remove('ring-2', 'ring-emerald-500'); bridge?.clearHighlight() }, 1400)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [probe])

  if (!themeOpen) return null

  return (
    <div ref={drawerRef} className="flex w-72 shrink-0 flex-col overflow-y-auto border-l border-zinc-800 bg-zinc-900 p-3">
      <div className="mb-1 flex items-center justify-between">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Theme</p>
        <button onClick={() => setThemeOpen(false)} className="rounded p-0.5 text-zinc-500 hover:text-zinc-200" title="Close (Esc)"><X className="h-4 w-4" /></button>
      </div>
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

      {/* Reset to the currently-applied preset's stock values — a quick escape
          hatch while experimenting (⌘Z still walks the full undo history). */}
      {theme.preset && (
        <button onClick={() => applyPreset(theme.preset as string)} className="mt-2 self-start text-[11px] text-zinc-500 underline decoration-dotted hover:text-zinc-300">
          Reset to preset defaults
        </button>
      )}

      {/* Your saved looks — sit right under the built-in presets since both
          apply a whole-site look in one click. */}
      {designerUnlocked && (
        <div className="mt-3 border-t border-zinc-800 pt-3">
          <StylePresetsPanel
            kind="theme"
            label="Your saved looks"
            currentData={theme}
            // Replace (not merge): a saved look is a full theme, so switching
            // between them must reset keys the target look doesn't set —
            // otherwise the current theme's values bleed through.
            onApply={(data) => { loadTheme(data); markDirty() }}
          />
        </div>
      )}

      <div className="mt-3 space-y-2.5 border-t border-zinc-800 pt-3">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Tweak</p>

        <Hl region="brand" bridge={bridge}>
          <div className="flex items-center justify-between">
            <span className="text-xs text-zinc-400">Brand color</span>
            <input
              type="color"
              value={themeColors(theme).brand || ((theme.mode as string) === 'dark' ? '#a3e635' : '#10b981')}
              onChange={(e) => setBrand(e.target.value)}
              className="h-7 w-12 cursor-pointer rounded border border-zinc-700 bg-transparent"
            />
          </div>
        </Hl>

        <Hl region="headingFont" bridge={bridge}>
          <div className="flex items-center justify-between gap-2">
            <span className="shrink-0 text-xs text-zinc-400">Fonts</span>
            <select value={fontPairId(theme)} onChange={(e) => setPairing(e.target.value)} className={`${inputCls} py-1.5`}>
              {FONT_PAIRINGS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
            </select>
          </div>
        </Hl>

        <Hl region="radius" bridge={bridge}>
          <div className="flex items-center justify-between gap-2">
            <span className="shrink-0 text-xs text-zinc-400">Corners</span>
            <select value={(theme.radius as string) || 'lg'} onChange={(e) => setRadius(e.target.value)} className={`${inputCls} py-1.5`}>
              {RADII.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
            </select>
          </div>
        </Hl>

        <Hl region="mode" bridge={bridge}>
          <div className="flex items-center justify-between">
            <span className="text-xs text-zinc-400">Mode</span>
            <div className="flex rounded-lg border border-zinc-700 p-0.5">
              {(['light', 'dark'] as const).map((m) => (
                <button key={m} onClick={() => setMode(m)} className={`rounded-md px-2.5 py-0.5 text-xs font-medium capitalize ${((theme.mode as string) || 'light') === m ? 'bg-emerald-500 text-zinc-950' : 'text-zinc-400 hover:text-zinc-200'}`}>{m}</button>
              ))}
            </div>
          </div>
        </Hl>
      </div>

      {/* premium designer studio — custom fonts, type, brand gradient */}
      <div className="mt-3 space-y-2.5 border-t border-zinc-800 pt-3">
        <p className={`${dHead} flex items-center gap-1`}><Wand2 className="h-3 w-3 text-amber-400" /> Designer</p>
        {!designerUnlocked ? (
          <PremiumLock>Upgrade to Pro for custom fonts, gradients &amp; motion.</PremiumLock>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-2">
              <Hl region="headingFont" bridge={bridge}><CappeFontPicker label="Heading font" value={themeFonts(theme).heading || 'Inter'} onChange={setHeadingFont} /></Hl>
              <Hl region="bodyFont" bridge={bridge}><CappeFontPicker label="Body font" value={themeFonts(theme).body || 'Inter'} onChange={setBodyFont} bodyOnly /></Hl>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Hl region="headingFont" bridge={bridge}>
                <label className="block"><span className={dLabel}>Heading weight</span>
                  <select value={String(themeObj(theme.type).headingWeight ?? '')} onChange={(e) => setTypeKey('headingWeight', e.target.value ? Number(e.target.value) : '')} className={`${inputCls} py-1.5`}>
                    <option value="">Default</option>
                    {([['400', 'Regular'], ['500', 'Medium'], ['600', 'Semibold'], ['700', 'Bold'], ['800', 'Extrabold'], ['900', 'Black']] as [string, string][]).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select></label>
              </Hl>
              <Hl region="headingFont" bridge={bridge}>
                <label className="block"><span className={dLabel}>Letter spacing</span>
                  <select value={String(themeObj(theme.type).headingSpacing ?? '')} onChange={(e) => setTypeKey('headingSpacing', e.target.value)} className={`${inputCls} py-1.5`}>
                    <option value="">Default</option>
                    {([['-0.03em', 'Tight'], ['-0.015em', 'Snug'], ['0em', 'Normal'], ['0.04em', 'Wide']] as [string, string][]).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select></label>
              </Hl>
            </div>
            <label className="block"><span className={dLabel}>Animated headline</span>
              <select value={String(themeObj(theme.type).heroAnim ?? 'none')} onChange={(e) => setTypeKey('heroAnim', e.target.value)} className={`${inputCls} py-1.5`}>
                {([['none', 'None'], ['rise', 'Rise in'], ['shimmer', 'Shimmer']] as [string, string][]).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select></label>
            <Hl region="brand" bridge={bridge}>
              <DCheck
                label="Brand gradient buttons"
                checked={!!obj(obj(theme.colors).brandGradient).stops}
                onChange={(on) => setBrandGradient(on ? { angle: 135, stops: [themeColors(theme).brand || '#10b981', '#a3e635'] } : null)}
              />
              {!!obj(obj(theme.colors).brandGradient).stops && (
                <GradientPicker value={obj(obj(theme.colors).brandGradient)} onChange={(g) => setBrandGradient(g)} />
              )}
            </Hl>

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
          <div className="grid grid-cols-2 gap-2">
            <Hl region="bodyFont" bridge={bridge}><DNum label="Base font (px)" value={numOr('baseFont', 17)} min={14} max={20} onChange={(v) => setNum('baseFont', v, 17)} /></Hl>
            <Hl region="bodyFont" bridge={bridge}><DSelect label="Line height" value={str(style.lineHeight)} options={LINEHEIGHT_OPTS} onChange={(v) => setStyleKey('lineHeight', v)} /></Hl>
            <Hl region="container" bridge={bridge}><DSelect label="Container width" value={str(style.container)} options={CONTAINER_OPTS} onChange={(v) => setStyleKey('container', v)} /></Hl>
            <Hl region="gutter" bridge={bridge}><DSelect label="Page gutter" value={str(style.gutter)} options={GUTTER_OPTS} onChange={(v) => setStyleKey('gutter', v)} /></Hl>
            <Hl region="sectionPad" bridge={bridge}><DSelect label="Section spacing" value={str(style.sectionPad)} options={SECPAD_OPTS} onChange={(v) => setStyleKey('sectionPad', v)} /></Hl>
            <Hl region="gap" bridge={bridge}><DSelect label="Grid gap" value={str(style.gap)} options={GAP_OPTS} onChange={(v) => setStyleKey('gap', v)} /></Hl>
            <Hl region="cardPad" bridge={bridge}><DNum label="Card padding (px)" value={numOr('cardPad', 24)} min={8} max={48} step={2} onChange={(v) => setNum('cardPad', v, 24)} /></Hl>
            <Hl region="cardBorder" bridge={bridge}><DSelect label="Card border" value={str(style.cardBorder)} options={CARDBD_OPTS} onChange={(v) => setStyleKey('cardBorder', v)} /></Hl>
            <Hl region="headerPad" bridge={bridge}><DNum label="Header padding (px)" value={numOr('headerPad', 17)} min={8} max={28} onChange={(v) => setNum('headerPad', v, 17)} /></Hl>
            <Hl region="brandSize" bridge={bridge}><DNum label="Brand size (px)" value={numOr('brandSize', 19)} min={14} max={32} onChange={(v) => setNum('brandSize', v, 19)} /></Hl>
            <Hl region="footerPad" bridge={bridge}><DNum label="Footer padding (px)" value={numOr('footerPad', 40)} min={16} max={80} step={2} onChange={(v) => setNum('footerPad', v, 40)} /></Hl>
          </div>
        )}
      </div>
      <p className="mt-3 text-[11px] text-zinc-500">Preview updates live. <span className="text-zinc-300">Save</span> to publish the look.</p>
    </div>
  )
}
