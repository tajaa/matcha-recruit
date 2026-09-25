import { describe, expect, it, vi } from 'vitest'
import { api } from '../../../api/client'
import { startPersonalCheckout } from './billing'

vi.mock('../../../api/client', () => ({
  api: { post: vi.fn() },
}))

describe('startPersonalCheckout', () => {
  it('sends the selected personal plan and Espresso return URLs', () => {
    startPersonalCheckout('lite')
    expect(api.post).toHaveBeenCalledWith(
      '/matcha-work/billing/checkout/personal',
      {
        plan: 'lite',
        success_url: `${window.location.origin}/espresso?upgraded=1`,
        cancel_url: `${window.location.origin}/espresso?canceled=1`,
      },
    )
  })
})
