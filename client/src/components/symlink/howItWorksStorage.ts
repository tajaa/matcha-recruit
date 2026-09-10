// Per-viewer "I've seen the explainer" flag. Its own module so the wizard file
// stays components-only (react-refresh/only-export-components).
//
// localStorage is the right home for this: it is a per-browser convenience, it
// never needs to reach the server, and losing it just shows the explainer once
// more. Every access is wrapped because private mode and blocked site data make
// the accessor itself throw, not merely return null.

const DISMISS_KEY = 'symlink:how-it-works:dismissed'

export function readHowItWorksDismissed(): boolean {
  try {
    return localStorage.getItem(DISMISS_KEY) === '1'
  } catch {
    return false
  }
}

export function writeHowItWorksDismissed(value: boolean) {
  try {
    if (value) localStorage.setItem(DISMISS_KEY, '1')
    else localStorage.removeItem(DISMISS_KEY)
  } catch {
    /* nothing to do — the panel just reappears next visit */
  }
}
