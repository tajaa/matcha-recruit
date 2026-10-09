import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import SchedulePilotToolbar from './SchedulePilotToolbar'
import { weekRangeLabel } from './weekLabel'

describe('weekRangeLabel', () => {
  it('reads as a date range, spanning months and years when the week does', () => {
    expect(weekRangeLabel('2026-10-04')).toBe('Oct 4 – 10, 2026')
    expect(weekRangeLabel('2026-09-28')).toBe('Sep 28 – Oct 4, 2026')
    expect(weekRangeLabel('2026-12-28')).toBe('Dec 28, 2026 – Jan 3, 2027')
    expect(weekRangeLabel('not-a-date')).toBe('Week of not-a-date')
  })
})

describe('SchedulePilotToolbar', () => {
  function renderToolbar(over: Partial<React.ComponentProps<typeof SchedulePilotToolbar>> = {}) {
    const props = {
      weekStart: '2026-10-04', summary: { total_shifts: 56, open_shifts: 1, draft: 28 } as never,
      saveState: 'idle' as never, lastSavedAt: null, editPublished: false, publishing: false,
      locations: [{ id: 'l1', name: 'Downtown', address: '412 Market St', city: 'San Francisco', state: 'CA', zipcode: '94103', is_active: true }] as never,
      locationId: 'l1', onChangeLocation: vi.fn(), onPreviousWeek: vi.fn(), onNextWeek: vi.fn(), onThisWeek: vi.fn(),
      onTogglePublishedEditing: vi.fn(), onPublish: vi.fn(), onExit: vi.fn(), onHelp: vi.fn(),
      centerView: 'board' as const, onSetCenterView: vi.fn(), reviewReady: false, railOpen: false, onToggleRail: vi.fn(),
      threadOpen: true, onToggleThread: vi.fn(), huumeSelectionCount: 2,
      ...over,
    }
    render(<SchedulePilotToolbar {...props} />)
    return props
  }

  it('names the store briefly, keeps the address in the tooltip, and counts the week', () => {
    renderToolbar()
    const picker = screen.getByRole('combobox', { name: 'Location' })
    expect(picker).toHaveAttribute('title', 'Downtown — 412 Market St, San Francisco, CA, 94103')
    expect(screen.getByRole('option', { name: 'Downtown' })).toBeInTheDocument()
    expect(screen.getByText('56 shifts')).toBeInTheDocument()
    expect(screen.getByText('1 unfilled')).toBeInTheDocument()
    expect(screen.getByText('2 selected for Huume')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Publish \(28\)/ })).toBeEnabled()
  })

  it('keeps exit and help reachable as named icon buttons', () => {
    const props = renderToolbar({ huumeSelectionCount: 0 })
    fireEvent.click(screen.getByRole('button', { name: 'Exit' }))
    fireEvent.click(screen.getByRole('button', { name: 'How to use' }))
    expect(props.onExit).toHaveBeenCalled()
    expect(props.onHelp).toHaveBeenCalled()
    expect(screen.queryByText(/selected for Huume/)).not.toBeInTheDocument()
  })
})
