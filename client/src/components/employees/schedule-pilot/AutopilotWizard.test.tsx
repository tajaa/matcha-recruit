import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AutopilotReadiness } from '../../../types/employeeSchedule'
import AutopilotWizard from './AutopilotWizard'

const { fetchProfile, saveProfile } = vi.hoisted(() => ({
  fetchProfile: vi.fn(), saveProfile: vi.fn(),
}))

vi.mock('../../../api/employees/locationProfile', () => ({
  fetchLocationScheduleProfile: fetchProfile,
  saveLocationScheduleProfile: saveProfile,
}))

const profile = {
  weather_sensitivity: 'none', min_floor_staff: 1, target_labor_pct: null,
  autopilot_shift_min_minutes: null, autopilot_shift_max_minutes: null,
}
const ready = {
  ready: true, blockers: [],
  autopilot: { sales_weeks: 9, sales_confidence: 'high', weather_days_available: 6, history_weeks: 4 },
} satisfies AutopilotReadiness

function renderWizard(overrides: Partial<Parameters<typeof AutopilotWizard>[0]> = {}) {
  const callbacks = {
    onClose: vi.fn(), onRefresh: vi.fn().mockResolvedValue(undefined),
    onOpenWeekSetup: vi.fn(), onOpenJobs: vi.fn(), onProfileSaved: vi.fn(),
    onGenerate: vi.fn().mockResolvedValue(true),
  }
  render(<AutopilotWizard
    locationId="loc-1" locationName="Downtown" weekStart="2026-09-21"
    readiness={ready} readinessLoading={false} readinessError={null} running={false}
    {...callbacks} {...overrides}
  />)
  return callbacks
}

beforeEach(() => {
  fetchProfile.mockReset().mockResolvedValue(profile)
  saveProfile.mockReset().mockImplementation(async (_locationId, payload) => ({ ...profile, ...payload }))
})

describe('AutopilotWizard', () => {
  it('shows server warnings on a ready week without blocking the build', async () => {
    const warning = "5 of 5 staff can't be scheduled this week, so their seats will stay open."
    const callbacks = renderWizard({ readiness: { ...ready, warnings: [warning] } })
    expect(screen.getByText('The required setup is ready.')).toBeInTheDocument()
    expect(screen.getByText(warning)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    await screen.findByLabelText('Minimum floor staff')
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    // Repeated where the manager decides to build — and the build still runs.
    expect(screen.getByText(warning)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Build review' }))
    await waitFor(() => expect(callbacks.onGenerate).toHaveBeenCalledOnce())
  })

  it('renders no warning box when the server sends none', () => {
    renderWizard()
    expect(screen.queryByText('Heads up before you build:')).not.toBeInTheDocument()
  })

  it('shows blockers and repair paths instead of hiding the build entry point', async () => {
    const callbacks = renderWizard({
      readiness: {
        ready: false, blockers: ['Save operating hours before building.'],
        autopilot: { sales_weeks: 0, sales_confidence: 'none', weather_days_available: 0, history_weeks: 0 },
      },
    })
    expect(screen.getByText('Save operating hours before building.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Edit week setup' }))
    expect(callbacks.onOpenWeekSetup).toHaveBeenCalledOnce()
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    expect(screen.getByText('0 weeks · none confidence')).toBeInTheDocument()
    await screen.findByLabelText('Minimum floor staff')
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    expect(screen.getByRole('button', { name: 'Build review' })).toBeDisabled()
    expect(callbacks.onGenerate).not.toHaveBeenCalled()
  })

  it('saves planning choices before offering a review-only build', async () => {
    const callbacks = renderWizard()
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    expect(screen.getByText('9 weeks · high confidence')).toBeInTheDocument()
    fireEvent.change(await screen.findByLabelText('Minimum floor staff'), { target: { value: '2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save & continue' }))
    await waitFor(() => expect(saveProfile).toHaveBeenCalledWith('loc-1', expect.objectContaining({ min_floor_staff: 2 })))
    expect(await screen.findByText('Nothing is published by this step.')).toBeInTheDocument()
    expect(screen.getByText(/Coverage floor:/).parentElement).toHaveTextContent('2 staff')
    fireEvent.click(screen.getByRole('button', { name: 'Build review' }))
    await waitFor(() => expect(callbacks.onGenerate).toHaveBeenCalledOnce())
    await waitFor(() => expect(callbacks.onClose).toHaveBeenCalledOnce())
    expect(callbacks.onProfileSaved).toHaveBeenCalledOnce()
  })

  it('keeps the manager on planning choices when shift bounds are invalid', async () => {
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    fireEvent.change(await screen.findByLabelText(/Minimum shift hours/), { target: { value: '10' } })
    fireEvent.change(screen.getByLabelText(/Maximum shift hours/), { target: { value: '4' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save & continue' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Minimum shift hours cannot exceed maximum shift hours')
    expect(screen.getByText('Tune the plan', { selector: 'h2' })).toBeInTheDocument()
    expect(saveProfile).not.toHaveBeenCalled()
  })

  it('checks a single shift override against the other default', async () => {
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    fireEvent.change(await screen.findByLabelText(/Minimum shift hours/), { target: { value: '10' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save & continue' }))
    expect(screen.getByRole('alert')).toHaveTextContent('defaults: 4–9 hours')
    expect(saveProfile).not.toHaveBeenCalled()
  })

  it('can retry a failed profile read without restarting the wizard', async () => {
    fetchProfile.mockReset().mockRejectedValueOnce(new Error('Connection lost')).mockResolvedValueOnce(profile)
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    expect(await screen.findByText('Saved choices could not be loaded.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry loading choices' }))
    expect(await screen.findByLabelText('Minimum floor staff')).toHaveValue(1)
  })

  it('does not advance after a failed policy save', async () => {
    saveProfile.mockRejectedValueOnce(new Error('Save failed'))
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    fireEvent.change(await screen.findByLabelText('Minimum floor staff'), { target: { value: '2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save & continue' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Save failed')
    expect(screen.getByText('Tune the plan', { selector: 'h2' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save & continue' }))
    expect(await screen.findByText('Nothing is published by this step.')).toBeInTheDocument()
  })

  it('asks before discarding unsaved planning choices', async () => {
    const callbacks = renderWizard()
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    fireEvent.change(await screen.findByLabelText('Minimum floor staff'), { target: { value: '3' } })
    fireEvent.click(screen.getByRole('button', { name: 'Close Autopilot wizard' }))
    expect(screen.getByText('Discard planning changes?')).toBeInTheDocument()
    expect(callbacks.onClose).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Keep editing' }))
    expect(screen.getByLabelText('Minimum floor staff')).toHaveValue(3)
    fireEvent.click(screen.getByRole('button', { name: 'Close Autopilot wizard' }))
    fireEvent.click(screen.getByRole('button', { name: 'Discard changes' }))
    expect(callbacks.onClose).toHaveBeenCalledOnce()
  })
})
