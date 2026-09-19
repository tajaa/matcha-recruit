// Unsaved-work guard shared by the Cappe chrome and the page editor.
//
// react-router is mounted with <BrowserRouter> (client/src/main.tsx), NOT a
// data router, so `useBlocker` throws here — there is no navigation-blocking
// hook available. Instead the editor registers a "am I dirty?" probe on this
// module, and every navigation control that can leave it (the sidebar links,
// sign-out, the editor's own back button) asks `confirmLeave()` first and
// cancels its own navigation when the user says no.
//
// One probe at a time: only one editor is ever mounted, and the hook clears
// the slot on unmount.

let _probe: (() => boolean) | null = null

/** Register (or, with `null`, clear) the probe `confirmLeave` consults. */
export function setDirtyProbe(fn: (() => boolean) | null) {
  _probe = fn
}

/** `true` when navigation may proceed: nothing is dirty, or the user chose to
 *  discard. `false` means the caller must cancel its navigation. Safe to call
 *  from anywhere — with no probe registered it is a no-op that returns true. */
export function confirmLeave(): boolean {
  if (!_probe) return true
  let dirty = false
  try {
    dirty = _probe()
  } catch {
    // A probe that throws must not trap the user in the editor.
    dirty = false
  }
  if (!dirty) return true
  return window.confirm('You have unsaved changes. Leave without saving?')
}
