import { beforeEach, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { resetAuthCaches } from '../../../api/authReset'
import RecapLink from './RecapLink'
const mock = vi.hoisted(() => ({ prefs: vi.fn() }))
vi.mock('../../api/matchaWork/recaps', () => ({ getRecapPreferences: mock.prefs }))
vi.mock('../../../hooks/useMe', () => ({ useMe: () => ({ me: { user: { id: 'owner' } }, isPersonal: true }) }))
vi.mock('../../routes/WorkSurfaceContext', () => ({ useWorkBase: () => '/espresso', useWorkSurface: () => 'espresso' }))
beforeEach(() => { vi.clearAllMocks(); resetAuthCaches(); mock.prefs.mockResolvedValue({ available: true, enabled: true, email_enabled: false }) })
it('renders direct recap links without one preferences request per historical message', () => {
  render(<MemoryRouter>{Array.from({ length: 50 }, (_, i) => <RecapLink key={i} recapId={`recap-${i}`} />)}</MemoryRouter>)
  expect(screen.getAllByRole('link')).toHaveLength(50)
  expect(mock.prefs).not.toHaveBeenCalled()
})
it('deduplicates owner-scoped preferences for source links', async () => {
  render(<MemoryRouter><RecapLink sourceId="a" /><RecapLink sourceId="b" /></MemoryRouter>)
  await waitFor(() => expect(screen.getAllByRole('link')).toHaveLength(2))
  expect(mock.prefs).toHaveBeenCalledOnce()
})
