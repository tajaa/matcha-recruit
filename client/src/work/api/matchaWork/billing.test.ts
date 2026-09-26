import { describe, expect, it, vi } from 'vitest'
import { api } from '../../../api/client'
import { cancelPersonalSubscription, startPersonalCheckout } from './billing'

vi.mock('../../../api/client', () => ({
  api: { post: vi.fn(), delete: vi.fn() },
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

  it('cancels the current personal subscription', () => {
    cancelPersonalSubscription()
    expect(api.delete).toHaveBeenCalledWith('/matcha-work/billing/subscription')
  })
})
