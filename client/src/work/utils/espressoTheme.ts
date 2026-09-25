import { useSyncExternalStore } from 'react'

export const ESPRESSO_THEMES = ['platinum', 'dark', 'light', 'cappuchin', 'graphite'] as const
export type EspressoTheme = typeof ESPRESSO_THEMES[number]

const ACCENT: Record<EspressoTheme, string> = {
  platinum: '#B45309', dark: '#D9770F', light: '#B45309',
  cappuchin: '#D9770F', graphite: '#D9770F',
}

export function themeOnAccent(theme: EspressoTheme): string {
  const rgb = ACCENT[theme].slice(1).match(/.{2}/g)!.map((part) => parseInt(part, 16) / 255)
  const linear = rgb.map((part) => part <= 0.04045 ? part / 12.92 : ((part + 0.055) / 1.055) ** 2.4)
  const luminance = 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
  return (1.05 / (luminance + 0.05)) >= ((luminance + 0.05) / 0.05) ? '#FFFFFF' : '#1B1D22'
}

const KEY = 'mw-theme'
const CHANGED = 'mw-theme-changed'

export function getEspressoTheme(): EspressoTheme {
  try {
    const saved = localStorage.getItem(KEY)
    if (ESPRESSO_THEMES.some((theme) => theme === saved)) return saved as EspressoTheme
  } catch { /* Storage may be unavailable. */ }
  return 'platinum'
}

export function setEspressoTheme(theme: EspressoTheme): void {
  try { localStorage.setItem(KEY, theme) } catch { /* Apply this tab's choice anyway. */ }
  window.dispatchEvent(new CustomEvent<EspressoTheme>(CHANGED, { detail: theme }))
}

let current: EspressoTheme | null = null
function snapshot(): EspressoTheme { return current ?? getEspressoTheme() }
function subscribe(listener: () => void) {
  const changed = (event: Event) => { current = (event as CustomEvent<EspressoTheme>).detail; listener() }
  const storage = (event: StorageEvent) => { if (event.key === KEY) { current = getEspressoTheme(); listener() } }
  window.addEventListener(CHANGED, changed)
  window.addEventListener('storage', storage)
  return () => { window.removeEventListener(CHANGED, changed); window.removeEventListener('storage', storage) }
}

export function useEspressoTheme(): EspressoTheme {
  return useSyncExternalStore(subscribe, snapshot, () => 'platinum')
}

export function resetEspressoThemeForTests() { current = null }
