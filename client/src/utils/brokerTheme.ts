// Broker Portal theme (dark default + inverse light). The inversion itself is
// pure CSS in index.css, scoped to html[data-broker-theme="light"]; this module
// just owns the attribute + persisted preference. The attribute lives on <html>
// only while a /broker route is mounted (BrokerRoutes applies on mount, clears on
// unmount) so no other surface is ever lightened.

const KEY = 'broker_theme'

export type BrokerTheme = 'dark' | 'light'

export function getBrokerTheme(): BrokerTheme {
  return localStorage.getItem(KEY) === 'light' ? 'light' : 'dark'
}

export function applyBrokerTheme(theme: BrokerTheme): void {
  if (theme === 'light') {
    document.documentElement.setAttribute('data-broker-theme', 'light')
  } else {
    document.documentElement.removeAttribute('data-broker-theme')
  }
}

export function setBrokerTheme(theme: BrokerTheme): void {
  localStorage.setItem(KEY, theme)
  applyBrokerTheme(theme)
}

/** Remove the scope attribute regardless of stored preference (route unmount). */
export function clearBrokerThemeAttr(): void {
  document.documentElement.removeAttribute('data-broker-theme')
}
