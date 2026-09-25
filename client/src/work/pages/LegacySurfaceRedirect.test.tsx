import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { LegacySurfacePrefixRedirect } from './LegacySurfaceRedirect'

function LocationMarker() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}{location.search}{location.hash}</output>
}

describe('LegacySurfacePrefixRedirect', () => {
  it('preserves the old query and hash after adding a target query', () => {
    render(
      <MemoryRouter initialEntries={['/app/schedule-intelligence?week=2026-08-09#overview']}>
        <Routes>
          <Route
            path="/app/schedule-intelligence"
            element={<LegacySurfacePrefixRedirect fromPrefix="/app/schedule-intelligence" toPrefix="/ops/schedule?tab=intelligence" />}
          />
          <Route path="/ops/schedule" element={<LocationMarker />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('location')).toHaveTextContent(
      '/ops/schedule?tab=intelligence&week=2026-08-09#overview',
    )
  })

  it('preserves a legacy /werk path, query, and hash', () => {
    render(
      <MemoryRouter initialEntries={['/werk/projects/abc?tab=chat#messages']}>
        <Routes>
          <Route path="/werk/*" element={<LegacySurfacePrefixRedirect fromPrefix="/werk" toPrefix="/espresso" />} />
          <Route path="/espresso/*" element={<LocationMarker />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('location')).toHaveTextContent('/espresso/projects/abc?tab=chat#messages')
  })
})
