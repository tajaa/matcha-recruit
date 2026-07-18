import { useState } from 'react'
import { CAPPE_THEMES, FONT_PAIRINGS, contrastText } from '../../../data/cappeThemes'
import { themeColors, themeFonts, themeObj } from './themeHelpers'

/** Live theme switching — edited locally, previewed instantly, saved on demand.
 *  Bundles theme state + all mutators so consumers (the toolbar's theme menu)
 *  take one prop instead of ~13. */
export function useThemeEditor() {
  const [theme, setTheme] = useState<Record<string, unknown>>({})
  const [themeDirty, setThemeDirty] = useState(false)
  const [themeOpen, setThemeOpen] = useState(false)

  const applyPreset = (id: string) => {
    const preset = CAPPE_THEMES.find((p) => p.id === id)
    if (!preset) return
    setTheme({ ...preset.config, preset: preset.id })
    setThemeDirty(true)
  }
  const setBrand = (hex: string) => {
    setTheme((t) => ({ ...t, colors: { ...themeColors(t), brand: hex, accent: hex, brandText: contrastText(hex) } }))
    setThemeDirty(true)
  }
  const setPairing = (id: string) => {
    const p = FONT_PAIRINGS.find((x) => x.id === id)
    if (!p) return
    setTheme((t) => ({ ...t, fonts: { heading: p.heading, body: p.body } }))
    setThemeDirty(true)
  }
  const setRadius = (v: string) => { setTheme((t) => ({ ...t, radius: v })); setThemeDirty(true) }
  const setMode = (m: 'light' | 'dark') => { setTheme((t) => ({ ...t, mode: m })); setThemeDirty(true) }
  const setPremium = (on: boolean) => { setTheme((t) => ({ ...t, premium: on })); setThemeDirty(true) }
  // ── premium designer: independent fonts, typography, brand gradient ────────
  const setHeadingFont = (name: string) => { setTheme((t) => ({ ...t, fonts: { ...themeFonts(t), heading: name } })); setThemeDirty(true) }
  const setBodyFont = (name: string) => { setTheme((t) => ({ ...t, fonts: { ...themeFonts(t), body: name } })); setThemeDirty(true) }
  const setTypeKey = (key: string, value: unknown) => {
    setTheme((t) => { const type = { ...themeObj(t.type) }; if (value === '' || value == null) delete type[key]; else type[key] = value; return { ...t, type } })
    setThemeDirty(true)
  }
  // ── global style system (theme_config.style): spacing / type scale / layout ──
  const setStyleKey = (key: string, value: unknown) => {
    setTheme((t) => { const style = { ...themeObj(t.style) }; if (value === '' || value == null) delete style[key]; else style[key] = value; return { ...t, style } })
    setThemeDirty(true)
  }
  const setBrandGradient = (g: Record<string, unknown> | null) => {
    setTheme((t) => {
      const colors = { ...(t.colors && typeof t.colors === 'object' && !Array.isArray(t.colors) ? (t.colors as Record<string, unknown>) : {}) }
      if (g) colors.brandGradient = g; else delete colors.brandGradient
      return { ...t, colors }
    })
    setThemeDirty(true)
  }

  return {
    theme, themeDirty, themeOpen, setThemeOpen,
    loadTheme: (t: Record<string, unknown>) => setTheme(t),
    markClean: () => setThemeDirty(false),
    markDirty: () => setThemeDirty(true),
    applyPreset, setBrand, setPairing, setRadius, setMode, setPremium,
    setHeadingFont, setBodyFont, setTypeKey, setStyleKey, setBrandGradient,
  }
}
