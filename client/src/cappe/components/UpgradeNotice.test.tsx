import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CappeSites from '../pages/CappeSites'
import { PremiumLock } from '../pages/site/PageEditor/DesignPrimitives'
import { setDirtyProbe } from '../utils/unsavedGuard'

const api = vi.hoisted(() => {
  class CappeApiError extends Error {
    code?: string
    constructor(message: string, code?: string) { super(message); this.code = code }
  }
  return { get: vi.fn(), post: vi.fn(), CappeApiError }
})
vi.mock('../api', () => ({ cappeApi: api, CappeApiError: api.CappeApiError }))
vi.mock('../hooks/useCappeMe', () => ({ useCappeMe: () => ({ account: { plan: 'free' } }) }))

const SITE = { id: 's1', name: 'Corner Bakery', slug: 'corner-bakery', subdomain: 'corner-bakery', custom_domain: null, status: 'draft', page_count: 1 }

beforeEach(() => {
  api.get.mockReset().mockResolvedValue([SITE])
  api.post.mockReset()
  setDirtyProbe(null)
})

async function createSecondSite() {
  render(<MemoryRouter><CappeSites /></MemoryRouter>)
  fireEvent.click(await screen.findByRole('button', { name: /Blank site/ }))
  fireEvent.change(screen.getByPlaceholderText(/e\.g\./), { target: { value: 'Second Shop' } })
  fireEvent.click(screen.getByRole('button', { name: /Create site/ }))
}

describe('plan limits lead somewhere', () => {
  it('links to billing when the site limit is hit', async () => {
    api.post.mockRejectedValue(new api.CappeApiError('Your plan includes 1 site. Upgrade to create more.', 'site_limit_reached'))
    await createSecondSite()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Your plan includes 1 site. Upgrade to create more.')
    expect(screen.getByRole('link', { name: 'See plans' })).toHaveAttribute('href', '/cappe/billing')
  })

  it('shows other failures without an upgrade link', async () => {
    api.post.mockRejectedValue(new Error('Server error — try again in a moment.'))
    await createSecondSite()

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Server error'))
    expect(screen.queryByRole('link', { name: 'See plans' })).toBeNull()
  })

  it('gives a locked editor feature a way to the plans, respecting unsaved work', () => {
    render(<MemoryRouter><PremiumLock>Upgrade to unlock motion.</PremiumLock></MemoryRouter>)
    const link = screen.getByRole('link', { name: 'See plans' })
    expect(link).toHaveAttribute('href', '/cappe/billing')

    setDirtyProbe(() => true)
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    expect(fireEvent.click(link)).toBe(false) // navigation cancelled
    expect(confirm).toHaveBeenCalled()
    confirm.mockRestore()
  })
})
