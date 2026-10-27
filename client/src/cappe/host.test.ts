import { describe, expect, it, vi } from 'vitest'
import { cappePath } from './host'

describe('cappePath', () => {
  it.each([
    ['/gummfit/login', '/login'],
    ['/cappe/login', '/login'],
    ['/gummfit/website-setup?plan=pro', '/website-setup?plan=pro'],
    ['/gummfit/creators/brands/login', '/creators/brands/login'],
    ['/gummfit', '/'],
    ['/gummfit?x=1', '/?x=1'],
  ])('drops the prefix from %s on gummfit.com', (path, expected) => {
    expect(cappePath(path, true)).toBe(expected)
  })

  it.each(['/gummfit/admin', '/gummfit/admin/login', '/gummfitness', '/cappers/login', '/login'])(
    'leaves %s alone on gummfit.com', (path) => {
      expect(cappePath(path, true)).toBe(path)
    })

  it('keeps the prefix off the Gummfit host, where it routes the request', () => {
    expect(cappePath('/gummfit/login', false)).toBe('/gummfit/login')
    expect(cappePath('/cappe/login', false)).toBe('/cappe/login')
  })
})

describe('sign-in links on gummfit.com', () => {
  it('are root URLs, not /gummfit/... or /cappe/...', async () => {
    const original = window.location
    vi.resetModules()
    Object.defineProperty(window, 'location', { configurable: true, value: new URL('https://gummfit.com/') })
    try {
      const { cappeAuthPaths } = await import('./host')
      const { creatorPaths } = await import('./creators/creatorPaths')
      const { writerPaths } = await import('./magazine/writers/writerPaths')
      const { readerPaths } = await import('./magazine/shelf/readerPaths')
      const { SIGNUP_PATH } = await import('./pages/landing/shared')
      expect(cappeAuthPaths).toEqual({ login: '/login', signup: '/website-setup', forgotPassword: '/forgot-password' })
      expect(SIGNUP_PATH).toBe('/website-setup')
      expect([creatorPaths.login, creatorPaths.brandLogin, writerPaths.login, readerPaths.login])
        .toEqual(['/creators/login', '/creators/brands/login', '/magazines/login', '/reader/login'])
    } finally {
      Object.defineProperty(window, 'location', { configurable: true, value: original })
      vi.resetModules()
    }
  })
})
