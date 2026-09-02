import { describe, expect, it } from 'vitest'
import { normalizeSensitivePath, safeSameOriginPath } from './urlSecurity'

describe('normalizeSensitivePath', () => {
  it('redacts route-defined bearer tokens even when they are not token-shaped', () => {
    expect(normalizeSensitivePath('/offer/abcdefghijk')).toBe('/offer/:token')
    expect(normalizeSensitivePath('/intake/external/letters-only')).toBe('/intake/external/:token')
    expect(normalizeSensitivePath('/register/invite/short-secret')).toBe('/register/invite/:token')
  })

  it('redacts generic UUID and long generated identifiers', () => {
    expect(normalizeSensitivePath('/employees/65d9edbe-5625-4e33-9ab6-92cae5199a10')).toBe('/employees/:id')
    expect(normalizeSensitivePath('/download/abcDEF_01234567890123456789')).toBe('/download/:token')
  })
})

describe('safeSameOriginPath', () => {
  it('accepts same-origin relative routes', () => {
    expect(safeSameOriginPath('/app?tab=people#active')).toBe('/app?tab=people#active')
  })

  it.each([
    'https://evil.example',
    '//evil.example',
    '/\\evil.example',
    '/app\nhttps://evil.example',
  ])('rejects unsafe redirect %s', (value) => {
    expect(safeSameOriginPath(value)).toBeNull()
  })
})
