import { describe, expect, it } from 'vitest'
import { normalizeElementLink } from './elementLink'

describe('element link input', () => {
  it('prefixes HTTPS and rejects unsafe schemes and credentials', () => {
    expect(normalizeElementLink('example.com/docs')).toBe('https://example.com/docs')
    expect(normalizeElementLink('javascript:alert(1)')).toBeNull()
    expect(normalizeElementLink('https://user:pass@example.com')).toBeNull()
  })
})
