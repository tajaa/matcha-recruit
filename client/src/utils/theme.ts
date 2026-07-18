// App-wide light/dark theme. The inversion is pure CSS in index.css, scoped
// to html[data-theme="light"]; this module just owns the attribute + the
// persisted preference. Applied once at app boot (main.tsx) — every sidebar
// shares the same toggle (components/shared/ThemeToggle.tsx) and preference.

const KEY = 'matcha_theme'

export type AppTheme = 'dark' | 'light'

export function getTheme(): AppTheme {
  return localStorage.getItem(KEY) === 'dark' ? 'dark' : 'light'
}

export function applyTheme(theme: AppTheme): void {
  if (theme === 'light') {
    document.documentElement.setAttribute('data-theme', 'light')
  } else {
    document.documentElement.removeAttribute('data-theme')
  }
}

export function setTheme(theme: AppTheme): void {
  localStorage.setItem(KEY, theme)
  applyTheme(theme)
}
