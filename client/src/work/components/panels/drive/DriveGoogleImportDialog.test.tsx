import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { DriveFolder } from '../../../types'
import DriveGoogleImportDialog from './DriveGoogleImportDialog'

const api = vi.hoisted(() => ({
  getGoogleDriveStatus: vi.fn(),
  connectGoogleDrive: vi.fn(),
  disconnectGoogleDrive: vi.fn(),
  importFromGoogleDrive: vi.fn(),
}))
vi.mock('../../../api/drive', () => api)

const folder: DriveFolder = {
  id: 'drafts', parent_id: 'discipline', space: 'hr', name: 'Drafts', system_key: 'hr_discipline_drafts',
  is_system: true, caps: ['add'], created_at: '',
}

beforeEach(() => Object.values(api).forEach((fn) => fn.mockReset()))

describe('DriveGoogleImportDialog', () => {
  it('asks to connect when not connected and opens the Google popup', async () => {
    api.getGoogleDriveStatus.mockResolvedValue({ connected: false, email: null })
    api.connectGoogleDrive.mockResolvedValue({ auth_url: 'https://accounts.google.com/o/oauth2/v2/auth?x=1' })
    const open = vi.spyOn(window, 'open').mockReturnValue({} as Window)
    render(<DriveGoogleImportDialog folder={folder} onImported={vi.fn()} onClose={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Connect Google Drive' }))
    await waitFor(() => expect(open).toHaveBeenCalledWith('https://accounts.google.com/o/oauth2/v2/auth?x=1', 'gdrive-oauth', 'width=600,height=700'))
    open.mockRestore()
  })

  it('re-checks status when the popup reports success', async () => {
    api.getGoogleDriveStatus
      .mockResolvedValueOnce({ connected: false, email: null })
      .mockResolvedValueOnce({ connected: true, email: 'gm@example.com' })
    render(<DriveGoogleImportDialog folder={folder} onImported={vi.fn()} onClose={vi.fn()} />)
    await screen.findByRole('button', { name: 'Connect Google Drive' })
    window.dispatchEvent(new MessageEvent('message', { data: 'gdrive-connected', origin: window.location.origin }))
    expect(await screen.findByText(/Connected as gm@example.com/)).toBeTruthy()
  })

  it('notices the connection even when the popup never posts back', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    api.getGoogleDriveStatus
      .mockResolvedValueOnce({ connected: false, email: null })
      .mockResolvedValue({ connected: true, email: 'gm@example.com' })
    api.connectGoogleDrive.mockResolvedValue({ auth_url: 'https://accounts.google.com/x' })
    const popup = { closed: false } as Window
    const open = vi.spyOn(window, 'open').mockReturnValue(popup)
    render(<DriveGoogleImportDialog folder={folder} onImported={vi.fn()} onClose={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Connect Google Drive' }))
    await waitFor(() => expect(open).toHaveBeenCalled())
    await vi.advanceTimersByTimeAsync(1600)
    expect(await screen.findByText(/Connected as gm@example.com/)).toBeTruthy()
    const calls = api.getGoogleDriveStatus.mock.calls.length
    await vi.advanceTimersByTimeAsync(5000)
    expect(api.getGoogleDriveStatus.mock.calls.length).toBe(calls) // stopped once connected
    open.mockRestore()
    vi.useRealTimers()
  })

  it('stops watching when the popup is closed without connecting', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    api.getGoogleDriveStatus.mockResolvedValue({ connected: false, email: null })
    api.connectGoogleDrive.mockResolvedValue({ auth_url: 'https://accounts.google.com/x' })
    const popup = { closed: true } as Window
    const open = vi.spyOn(window, 'open').mockReturnValue(popup)
    render(<DriveGoogleImportDialog folder={folder} onImported={vi.fn()} onClose={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Connect Google Drive' }))
    await waitFor(() => expect(open).toHaveBeenCalled())
    await vi.advanceTimersByTimeAsync(1600)
    const calls = api.getGoogleDriveStatus.mock.calls.length
    await vi.advanceTimersByTimeAsync(5000)
    expect(api.getGoogleDriveStatus.mock.calls.length).toBe(calls)
    open.mockRestore()
    vi.useRealTimers()
  })

  it('keeps showing connected when disconnect fails', async () => {
    api.getGoogleDriveStatus.mockResolvedValue({ connected: true, email: 'gm@example.com' })
    api.disconnectGoogleDrive.mockRejectedValue(new Error('Server error'))
    render(<DriveGoogleImportDialog folder={folder} onImported={vi.fn()} onClose={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Disconnect' }))
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Server error')
    expect(screen.getByText(/Connected as gm@example.com/)).toBeTruthy()
  })

  it('refuses a non-Google link without calling the server', async () => {
    api.getGoogleDriveStatus.mockResolvedValue({ connected: true, email: 'gm@example.com' })
    render(<DriveGoogleImportDialog folder={folder} onImported={vi.fn()} onClose={vi.fn()} />)
    fireEvent.change(await screen.findByLabelText('Google Drive link'), { target: { value: 'https://example.com/doc' } })
    fireEvent.click(screen.getByRole('button', { name: 'Import' }))
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Paste a link to a Google Doc, Sheet, Slides deck or Drive file.')
    expect(api.importFromGoogleDrive).not.toHaveBeenCalled()
  })

  it('imports into the folder and closes', async () => {
    api.getGoogleDriveStatus.mockResolvedValue({ connected: true, email: null })
    const file = { id: 'f1', filename: 'Write-up.docx' }
    api.importFromGoogleDrive.mockResolvedValue(file)
    const onImported = vi.fn()
    const onClose = vi.fn()
    render(<DriveGoogleImportDialog folder={folder} onImported={onImported} onClose={onClose} />)
    const link = 'https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUv/edit'
    fireEvent.change(await screen.findByLabelText('Google Drive link'), { target: { value: link } })
    fireEvent.click(screen.getByRole('button', { name: 'Import' }))
    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(api.importFromGoogleDrive).toHaveBeenCalledWith(link, 'drafts')
    expect(onImported).toHaveBeenCalledWith(file)
  })

  it('shows the server error and stays open', async () => {
    api.getGoogleDriveStatus.mockResolvedValue({ connected: true, email: null })
    api.importFromGoogleDrive.mockRejectedValue(new Error("Google says that file doesn't exist or your account can't open it."))
    const onClose = vi.fn()
    render(<DriveGoogleImportDialog folder={folder} onImported={vi.fn()} onClose={onClose} />)
    fireEvent.change(await screen.findByLabelText('Google Drive link'), { target: { value: 'https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUv/view' } })
    fireEvent.click(screen.getByRole('button', { name: 'Import' }))
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', "Google says that file doesn't exist or your account can't open it.")
    expect(onClose).not.toHaveBeenCalled()
  })
})
