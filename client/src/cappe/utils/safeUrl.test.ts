// These two guards are the last thing between a URL another tenant typed and
// an `href` / CSS `url()` sink on a page someone else is reading.
// Run:  npx vitest run src/cappe/utils/safeUrl
import { describe, expect, it } from 'vitest'
import { safeCssUrl, safeHttpUrl } from './safeUrl'

describe('safeHttpUrl', () => {
  it('passes through an absolute https URL', () => {
    expect(safeHttpUrl('https://example.com/a?b=c#d')).toBe('https://example.com/a?b=c#d')
  })

  it('passes through an absolute http URL', () => {
    expect(safeHttpUrl('http://example.com/')).toBe('http://example.com/')
  })

  it('trims surrounding whitespace', () => {
    expect(safeHttpUrl('  https://example.com/x  ')).toBe('https://example.com/x')
  })

  it('refuses javascript:', () => {
    expect(safeHttpUrl('javascript:alert(1)')).toBeUndefined()
  })

  it('refuses javascript: hidden behind whitespace the HTML parser strips', () => {
    // The browser strips the newline before deciding the scheme, so a naive
    // startsWith('http') check would let this through and it would execute.
    expect(safeHttpUrl('java\nscript:alert(1)')).toBeUndefined()
    expect(safeHttpUrl('  JaVaScRiPt:alert(1)')).toBeUndefined()
  })

  it('refuses data: and vbscript:', () => {
    expect(safeHttpUrl('data:text/html,<script>alert(1)</script>')).toBeUndefined()
    expect(safeHttpUrl('vbscript:msgbox(1)')).toBeUndefined()
  })

  it('refuses a relative or protocol-relative URL', () => {
    expect(safeHttpUrl('/cappe/sites')).toBeUndefined()
    expect(safeHttpUrl('//evil.example.com')).toBeUndefined()
  })

  it('refuses empty, null and non-string input', () => {
    expect(safeHttpUrl('')).toBeUndefined()
    expect(safeHttpUrl('   ')).toBeUndefined()
    expect(safeHttpUrl(null)).toBeUndefined()
    expect(safeHttpUrl(undefined)).toBeUndefined()
    expect(safeHttpUrl(42 as unknown as string)).toBeUndefined()
  })
})

describe('safeCssUrl', () => {
  it('passes through an https URL', () => {
    expect(safeCssUrl('https://cdn.example.com/cover.jpg')).toBe('https://cdn.example.com/cover.jpg')
  })

  it('is https-only — matches the server-side _https validator', () => {
    expect(safeCssUrl('http://cdn.example.com/cover.jpg')).toBeUndefined()
  })

  it('refuses javascript: and relative values', () => {
    expect(safeCssUrl('javascript:alert(1)')).toBeUndefined()
    expect(safeCssUrl('/local.png')).toBeUndefined()
  })

  it('encodes the characters that would close the url() token early', () => {
    const out = safeCssUrl('https://x.example.com/a")%3Bcolor:red%3B("b\'c')
    expect(out).toBeDefined()
    expect(out).not.toMatch(/["'()]/)
  })

  it('encodes spaces so the declaration cannot be split', () => {
    expect(safeCssUrl('https://x.example.com/a b.png')).toBe('https://x.example.com/a%20b.png')
  })
})
