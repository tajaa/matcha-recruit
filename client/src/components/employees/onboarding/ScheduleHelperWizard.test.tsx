import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ScheduleHelperWizard from './ScheduleHelperWizard'

describe('ScheduleHelperWizard', () => {
  it('walks through the scheduling feature workflow', () => {
    const onClose = vi.fn()
    render(<ScheduleHelperWizard open onClose={onClose} />)

    expect(screen.getByText('Start with the weekly schedule')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('Use Templates for recurring coverage')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('Review employee requests in one place')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('Use Intelligence before you publish')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('Resolve training and credential warnings')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('Check the law, then publish')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Start scheduling' }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('can be skipped', () => {
    const onClose = vi.fn()
    render(<ScheduleHelperWizard open onClose={onClose} />)
    fireEvent.click(screen.getByRole('button', { name: 'Skip' }))
    expect(onClose).toHaveBeenCalledOnce()
  })
})
