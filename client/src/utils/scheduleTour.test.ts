import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { shouldAutoOpenScheduleTour } from './scheduleTour'

function memoryStorage(): Storage {
  const values = new Map<string, string>()
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => { values.set(key, value) },
    removeItem: (key) => { values.delete(key) },
    clear: () => values.clear(),
    key: () => null,
    get length() { return values.size },
  }
}

describe('shouldAutoOpenScheduleTour', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', memoryStorage())
    vi.stubGlobal('sessionStorage', memoryStorage())
  })
  afterEach(() => vi.unstubAllGlobals())

  it('opens one tour per session, not the schedule tour and then the editor tour', () => {
    expect(shouldAutoOpenScheduleTour('schedule')).toBe(true)
    // The editor is usually the very next page; its tour waits for Help.
    expect(shouldAutoOpenScheduleTour('editor')).toBe(false)
    // A remount of the first page is the same tour re-asking.
    expect(shouldAutoOpenScheduleTour('schedule')).toBe(true)
  })

  it('never reopens a tour the manager already dismissed', () => {
    window.localStorage.setItem('schedule', 'seen')
    expect(shouldAutoOpenScheduleTour('schedule')).toBe(false)
    // Nothing auto-opened, so the other tour is still free to.
    expect(shouldAutoOpenScheduleTour('editor')).toBe(true)
  })

  it('falls back to opening when storage is unavailable', () => {
    vi.stubGlobal('localStorage', { getItem: () => { throw new Error('blocked') } })
    expect(shouldAutoOpenScheduleTour('schedule')).toBe(true)
  })
})
