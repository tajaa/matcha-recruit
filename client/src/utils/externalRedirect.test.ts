import { describe, it, expect } from 'vitest'
import { isAllowedRedirect } from './externalRedirect'

// jsdom origin is http://localhost:3000 by default.
describe('isAllowedRedirect', () => {
  it('allows same-origin absolute + relative URLs', () => {
    expect(isAllowedRedirect(`${window.location.origin}/ir/onboarding`)).toBe(true)
    expect(isAllowedRedirect('/compliance/onboarding?compliance=1')).toBe(true)
  })

  it('allows allow-listed https hosts (exact + subdomain)', () => {
    expect(isAllowedRedirect('https://checkout.stripe.com/c/pay/cs_test_123')).toBe(true)
    expect(isAllowedRedirect('https://stripe.com/x')).toBe(true)
    expect(isAllowedRedirect('https://accounts.google.com/o/oauth2/v2/auth')).toBe(true)
    expect(isAllowedRedirect('https://connect.tryfinch.com/authorize')).toBe(true)
  })

  it('blocks foreign https hosts', () => {
    expect(isAllowedRedirect('https://evil.com/phish')).toBe(false)
    // a look-alike that merely contains the allowed host as a substring must NOT pass
    expect(isAllowedRedirect('https://stripe.com.evil.com/x')).toBe(false)
    expect(isAllowedRedirect('https://notstripe.com/x')).toBe(false)
  })

  it('blocks non-https schemes and downgrades', () => {
    expect(isAllowedRedirect('javascript:alert(1)')).toBe(false)
    expect(isAllowedRedirect('data:text/html,<script>alert(1)</script>')).toBe(false)
    expect(isAllowedRedirect('http://checkout.stripe.com/x')).toBe(false) // http downgrade
  })

  it('treats bare/garbage strings as same-origin relative paths (harmless)', () => {
    // `new URL(x, origin)` resolves these against our own origin, so they navigate
    // in-app at worst — the guard exists to block FOREIGN hosts + bad schemes, both
    // covered above, not to validate that a path is meaningful.
    expect(isAllowedRedirect('not-a-url')).toBe(true)
    expect(isAllowedRedirect('')).toBe(true)
  })
})
