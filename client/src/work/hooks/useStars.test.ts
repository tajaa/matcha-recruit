import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { clearStarCache, getStarIds, toggleStar } from './useStars'

beforeEach(() => { localStorage.clear(); clearStarCache() })
afterEach(() => vi.restoreAllMocks())

describe('local stars', () => {
  it('survives a cache reset and stays scoped to the user id', () => {
    expect(toggleStar('user-a', 'journals', 'journal-1')).toBe(true)
    expect(localStorage.getItem('mw-starred-journals:user-a')).toBe('["journal-1"]')
    clearStarCache()
    expect(getStarIds('user-a', 'journals')).toEqual(['journal-1'])
    expect(getStarIds('user-b', 'journals')).toEqual([])
  })

  it('degrades to no stars when localStorage throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    clearStarCache()
    expect(getStarIds('user-a', 'channels')).toEqual([])
    expect(toggleStar('user-a', 'channels', 'channel-1')).toBe(false)
    expect(getStarIds('user-a', 'channels')).toEqual([])
  })
})
