import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import BroadcastBar from './BroadcastBar'
import type { useLiveKitBroadcast } from '../../hooks/useLiveKitBroadcast'

const inactive = { active: false, max_duration_seconds: 600, weekly_limit: 10,
  weekly_used: 0, weekly_remaining: 10 }

function view(overrides: Partial<React.ComponentProps<typeof BroadcastBar>> = {}) {
  const onUpgrade = vi.fn()
  const broadcast = { status: inactive, connectionState: 'idle', error: null,
    start: vi.fn(), watch: vi.fn(), stop: vi.fn(), leave: vi.fn(), setPublisher: vi.fn(),
    participants: [], isPublishing: false } as unknown as ReturnType<typeof useLiveKitBroadcast>
  render(<BroadcastBar broadcast={broadcast} members={[]} isOwner canGoLive callActive={false}
    onUpgrade={onUpgrade} onClose={vi.fn()} {...overrides} />)
  return { onUpgrade, broadcast }
}

describe('broadcast controls', () => {
  it('offers a free owner the upgrade and still lets a member watch', () => {
    const { onUpgrade } = view({ canGoLive: false })
    fireEvent.click(screen.getByRole('button', { name: /Get Pro to go live/i }))
    expect(onUpgrade).toHaveBeenCalledOnce()
    screen.getByRole('button', { name: /Close broadcast panel/i })
  })

  it('hides owner stop and promotion controls from a member', () => {
    const broadcast = { status: { ...inactive, active: true, broadcast_id: 'bc-1' },
      connectionState: 'idle', error: null, watch: vi.fn(), participants: [] } as unknown as ReturnType<typeof useLiveKitBroadcast>
    view({ broadcast, isOwner: false })
    screen.getByRole('button', { name: 'Watch live' })
    expect(screen.queryByRole('button', { name: /End broadcast/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /Promote/i })).toBeNull()
  })

  it('disables Go Live while a call is active', () => {
    view({ callActive: true })
    expect(screen.getByRole('button', { name: 'Go Live' })).toBeDisabled()
  })
})
