import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ScheduleEditorGuide from './ScheduleEditorGuide'

describe('ScheduleEditorGuide', () => {
  it('walks through the actual editor workflow', () => {
    const onClose = vi.fn()
    render(<ScheduleEditorGuide open onClose={onClose} />)

    expect(screen.getByText('Start with the empty grid')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('Place people where they belong')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('Review the week before it goes live')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Start scheduling' }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('can be skipped', () => {
    const onClose = vi.fn()
    render(<ScheduleEditorGuide open onClose={onClose} />)
    fireEvent.click(screen.getByRole('button', { name: 'Skip' }))
    expect(onClose).toHaveBeenCalledOnce()
  })
})
