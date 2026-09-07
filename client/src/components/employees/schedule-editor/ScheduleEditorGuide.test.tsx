import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ScheduleEditorGuide from './ScheduleEditorGuide'

describe('ScheduleEditorGuide', () => {
  it('walks through the Schedule Pilot workflow', () => {
    const onClose = vi.fn()
    render(<ScheduleEditorGuide open onClose={onClose} />)

    expect(screen.getByText('Start from the inputs rail')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('Jobs, credentials and week setup live in the rail')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('The board still works the way you know')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('Huume is always on the right')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('The review pane shows what a change will do')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('Simulate a fill before you commit')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('Publish when the week reads right')).toBeInTheDocument()
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
