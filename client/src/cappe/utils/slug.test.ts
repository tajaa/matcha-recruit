import { describe, expect, it } from 'vitest'
import { subdomainPreview } from './slug'

describe('subdomainPreview', () => {
  it('hyphenates a business name', () => {
    expect(subdomainPreview("  Mara's Coffee ")).toBe('mara-s-coffee')
  })

  it('never previews more than one DNS label', () => {
    const preview = subdomainPreview(`${'a'.repeat(62)} bakery`)
    expect(preview).toBe('a'.repeat(62))
    expect(preview.length).toBeLessThanOrEqual(63)
  })

  it('falls back when nothing usable is typed', () => {
    expect(subdomainPreview('日本語')).toBe('your-name')
    expect(subdomainPreview('', 'site')).toBe('site')
  })
})
