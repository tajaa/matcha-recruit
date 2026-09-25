import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { MeResponse } from '../../types/dashboard'
import WorkSettings, { AccountSettings } from './WorkSettings'

const mock = vi.hoisted(() => ({ upload: vi.fn(), update: vi.fn(), refresh: vi.fn() }))
vi.mock('../api/account', () => ({ uploadWorkAvatar: mock.upload, updateWorkProfile: mock.update }))
vi.mock('../../hooks/useMe', () => ({ useMe: () => ({ me, loading: false, refresh: mock.refresh }) }))
vi.mock('../routes/WorkSurfaceContext', () => ({ useWorkSurface: () => 'espresso' }))

const me = { user: { id: 'user-1', role: 'individual', email: 'user@test.com', avatar_url: null }, profile: { name: 'User', phone: '555-0100' } } as MeResponse

beforeEach(() => { vi.clearAllMocks(); mock.refresh.mockResolvedValue(undefined); mock.upload.mockResolvedValue({ avatar_url: 'https://files.test/avatar' }); mock.update.mockResolvedValue({ status: 'profile_updated' }) })

describe('Espresso settings', () => {
  it('rejects oversized avatars before the upload request', async () => {
    render(<AccountSettings me={me} refresh={mock.refresh} />)
    const file = new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'large.png', { type: 'image/png' })
    fireEvent.change(screen.getByLabelText('Change photo'), { target: { files: [file] } })
    expect(await screen.findByText('Choose an image under 5 MB.')).toBeTruthy()
    expect(mock.upload).not.toHaveBeenCalled()
  })

  it('rejects non-image MIME types before the upload request', async () => {
    render(<AccountSettings me={me} refresh={mock.refresh} />)
    fireEvent.change(screen.getByLabelText('Change photo'), { target: { files: [new File(['x'], 'x.txt', { type: 'text/plain' })] } })
    expect(await screen.findByText('Choose a JPEG, PNG, or WebP image.')).toBeTruthy()
    expect(mock.upload).not.toHaveBeenCalled()
  })

  it('refreshes /auth/me after an avatar upload', async () => {
    render(<AccountSettings me={me} refresh={mock.refresh} />)
    const file = new File(['x'], 'face.png', { type: 'image/png' })
    fireEvent.change(screen.getByLabelText('Change photo'), { target: { files: [file] } })
    await waitFor(() => expect(mock.upload).toHaveBeenCalledWith(file))
    await waitFor(() => expect(mock.refresh).toHaveBeenCalledOnce())
  })

  it('does not show unsupported notification preference toggles', () => {
    render(<WorkSettings />)
    expect(screen.queryByRole('switch')).toBeNull()
    expect(screen.queryByText(/notification preferences/i)).toBeNull()
  })
})
