import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ScheduleEditorGuide from './ScheduleEditorGuide'

describe('ScheduleEditorGuide', () => {
  it('walks through the actual editor workflow', () => {
    const onClose = vi.fn()
    render(<ScheduleEditorGuide open onClose={onClose} />)

    expect(screen.getByText('Create jobs before you build shifts')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('Set qualifications and credential rules')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('Choose a job on the shift')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('Generate a qualified week')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('Start with the empty grid')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('Place people where they belong')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('Review the week before it goes live')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('Build shifts by talking, not clicking')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('Review break rules and waivers before you publish')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('Food-handler expiry protection runs automatically')).toBeInTheDocument()
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
