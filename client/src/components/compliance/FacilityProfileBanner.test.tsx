import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { FacilityProfileBanner } from './FacilityProfileBanner'

vi.mock('../../api/compliance', () => ({
  updateFacilityAttributes: vi.fn(),
}))

const prompt = 'Set up facility profile for more accurate healthcare compliance'

describe('FacilityProfileBanner eligibility', () => {
  beforeEach(() => localStorage.clear())

  it('does not prompt an unprofiled hospitality location', () => {
    render(
      <FacilityProfileBanner
        locationId="cafe"
        facilityAttributes={null}
        eligible={false}
        onUpdated={vi.fn()}
      />,
    )

    expect(screen.queryByText(prompt)).not.toBeInTheDocument()
  })

  it('still prompts an eligible healthcare location', () => {
    render(
      <FacilityProfileBanner
        locationId="clinic"
        facilityAttributes={null}
        eligible
        onUpdated={vi.fn()}
      />,
    )

    expect(screen.getByText(prompt)).toBeInTheDocument()
  })

  it('offers apply-to-all only for other eligible locations', async () => {
    const user = userEvent.setup()
    render(
      <FacilityProfileBanner
        locationId="clinic"
        facilityAttributes={null}
        eligible
        onUpdated={vi.fn()}
        allLocations={[
          { id: 'clinic', facility_profile_eligible: true },
          { id: 'hospital', facility_profile_eligible: true },
          { id: 'cafe', facility_profile_eligible: false },
        ]}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Set Up' }))

    expect(screen.getByRole('checkbox', {
      name: 'Apply to all 1 other location without a profile',
    })).toBeInTheDocument()
  })
})
