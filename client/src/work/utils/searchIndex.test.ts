import { describe, expect, it } from 'vitest'
import { rankSearch, type SearchItem } from './searchIndex'

describe('Find ranking', () => {
  it('matches a substring across threads, channels, projects, journals, and files', () => {
    const kinds: SearchItem['kind'][] = ['thread', 'channel', 'project', 'journal', 'file']
    const items = kinds.map((kind, index): SearchItem => ({ kind, id: String(index), title: `${kind} alpha item`, updatedAt: '2026-01-01T00:00:00Z' }))
    expect(new Set(rankSearch(items, 'ALPHA').map((item) => item.kind))).toEqual(new Set(kinds))
  })

  it('ranks earlier matches first, then newer matches', () => {
    const items: SearchItem[] = [
      { kind: 'thread', id: 'old', title: 'alpha old', updatedAt: '2025-01-01T00:00:00Z' },
      { kind: 'project', id: 'late', title: 'a alpha', updatedAt: '2026-01-01T00:00:00Z' },
      { kind: 'journal', id: 'new', title: 'alpha new', updatedAt: '2026-01-01T00:00:00Z' },
    ]
    expect(rankSearch(items, 'alpha').map((item) => item.id)).toEqual(['new', 'old', 'late'])
  })
})
