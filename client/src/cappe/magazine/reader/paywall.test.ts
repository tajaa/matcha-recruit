import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

/** The paywall script the server puts on paid stories and issues
 *  (render/assets/paywall.js), run on a page of walls against a fake API:
 *  how many requests it spends, since every paid part fetched counts against
 *  the reader's hourly allowance (300). */

type Reply = { status: number; body: unknown }
const calls: string[] = []

function page(stories: number, { back = false } = {}) {
  document.body.innerHTML = Array.from({ length: stories }, (_, i) => `
    <section data-mz-paywall data-mz-story="s-${i}" data-mz-open="1" data-mz-price="$5">
      <div data-mz-actions></div><p data-mz-msg></p></section>
    <div data-mz-paid="s-${i}" hidden></div>`).join('')
  window.history.replaceState({}, '', back ? '/issues/3?subscribed=1' : '/issues/3')
  ;(window as unknown as { __CAPPE_RT__: unknown }).__CAPPE_RT__ = { api: '/api', slug: 'mag', esc: (s: string) => s, preview: false }
}

function serve(answer: (path: string) => Reply) {
  globalThis.fetch = (async (url: string) => {
    const path = String(url).replace('/api', '')
    calls.push(path)
    const r = answer(path)
    return { ok: r.status < 400, status: r.status, json: async () => r.body } as Response
  }) as typeof fetch
}

// Read from the server's assets as served (Vite won't import text from
// outside the client); `node:fs` by a computed name keeps Node's types out
// of the app's.
let script = ''
beforeAll(async () => {
  const fs = (await import(/* @vite-ignore */ ['node', 'fs'].join(':'))) as { readFileSync: (p: string, enc: string) => string }
  script = fs.readFileSync(new URL('../../../../../server/app/cappe/services/render/assets/paywall.js', import.meta.url).pathname.replace(/^\/@fs/, ''), 'utf-8')
})

const run = () => new Function(script)()
const paidCalls = () => calls.filter((c) => c.endsWith('/paid')).length
const shown = () => Array.from(document.querySelectorAll<HTMLElement>('[data-mz-paid]')).filter((p) => !p.hidden).length

afterEach(() => { calls.length = 0; vi.useRealTimers() })

describe('the paywall script', () => {
  it('back from checkout, waits on one question, then fetches each paid part once', async () => {
    vi.useFakeTimers()
    page(40, { back: true })
    let asked = 0
    serve((path) => {
      if (path === '/shopper/web/refresh') return { status: 200, body: { access_token: 't' } }
      if (path === '/magazine/me') return { status: 200, body: { has_access: ++asked >= 7 } }  // the webhook lands late
      return { status: 200, body: { html: '<p>The rest.</p>' } }
    })
    run()
    await vi.advanceTimersByTimeAsync(20_000)
    expect(calls.filter((c) => c === '/magazine/me')).toHaveLength(7)
    expect(paidCalls()).toBe(40)  // not 40 for every wait
    expect(shown()).toBe(40)
  })

  it('without access, spends nothing of the allowance and offers to subscribe', async () => {
    page(40)
    serve((path) => (path === '/shopper/web/refresh' ? { status: 200, body: { access_token: 't' } }
      : path === '/magazine/me' ? { status: 200, body: { has_access: false } } : { status: 403, body: {} }))
    run()
    await vi.waitFor(() => expect(document.querySelector('[data-mz-actions] button')?.textContent).toBe('Subscribe for $5 a month'))
    expect(paidCalls()).toBe(0)
  })

  it('signed out, asks nothing but offers to sign in', async () => {
    page(2)
    serve((path) => (path === '/shopper/web/refresh' ? { status: 401, body: {} } : { status: 500, body: {} }))
    run()
    await vi.waitFor(() => expect(document.querySelector('[data-signin]')).not.toBeNull())
    expect(calls).toEqual(['/shopper/web/refresh'])
  })

  it('says what went wrong when a part cannot be fetched', async () => {
    page(2)
    serve((path) => (path === '/shopper/web/refresh' ? { status: 200, body: { access_token: 't' } }
      : path === '/magazine/me' ? { status: 200, body: { has_access: true } }
        : { status: 429, body: { detail: 'Too many requests. Try again in a while.' } }))
    run()
    await vi.waitFor(() => expect(document.querySelector('[data-mz-msg]')?.textContent).toBe('Too many requests. Try again in a while.'))
    expect(shown()).toBe(0)
  })
})
