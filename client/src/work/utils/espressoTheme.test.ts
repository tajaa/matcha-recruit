import { beforeEach, describe, expect, it } from 'vitest'
import { ESPRESSO_THEMES, getEspressoTheme, resetEspressoThemeForTests, setEspressoTheme, themeOnAccent } from './espressoTheme'

beforeEach(() => { localStorage.clear(); resetEspressoThemeForTests() })

describe('Espresso themes', () => {
  it('persists each theme and computes accent-label contrast', () => {
    for (const theme of ESPRESSO_THEMES) {
      setEspressoTheme(theme)
      resetEspressoThemeForTests()
      expect(getEspressoTheme()).toBe(theme)
      expect(themeOnAccent(theme)).toMatch(/^#[0-9A-F]{6}$/)
    }
  })

  it('falls back to Dark for an unknown stored value', () => {
    localStorage.setItem('mw-theme', 'unknown')
    expect(getEspressoTheme()).toBe('dark')
  })

  it('defaults to Dark when nothing is stored so existing users keep their look', () => {
    localStorage.removeItem('mw-theme')
    expect(getEspressoTheme()).toBe('dark')
  })

  it('chooses light or dark label ink from the accent contrast', () => {
    expect(themeOnAccent('platinum')).toBe('#FFFFFF')
    expect(themeOnAccent('dark')).toBe('#1B1D22')
  })
})
