import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import PrivateAttachment from './PrivateAttachment'
import * as assistantApi from '../../api/matchaWork/assistant'

const link = { url: 'https://signed.example.com/cv.pdf?sig=1', filename: 'cv.pdf', content_type: 'application/pdf', expires_in: 300 }

describe('PrivateAttachment', () => {
  afterEach(() => vi.restoreAllMocks())

  it('names private files by their attachment URL', () => {
    expect(assistantApi.privateInputId('espresso-input:abc')).toBe('abc')
    expect(assistantApi.privateInputId('https://cdn.example.com/a.png')).toBeNull()
    expect(assistantApi.privateInputId('espresso-input:')).toBeNull()
    expect(assistantApi.privateInputId(undefined)).toBeNull()
  })

  it('fetches a fresh link when a document is opened', async () => {
    const get = vi.spyOn(assistantApi, 'getAssistantInputLink').mockResolvedValue(link)
    const opened = vi.spyOn(window, 'open').mockReturnValue(null)
    render(<PrivateAttachment inputId="abc" att={{ url: 'espresso-input:abc', filename: 'cv.pdf', content_type: 'application/pdf', size: 2_500_000 }} />)
    expect(screen.getByText('2.5MB')).toBeTruthy()
    expect(get).not.toHaveBeenCalled()
    fireEvent.click(screen.getByTitle('Only you can open this file'))
    await waitFor(() => expect(opened).toHaveBeenCalledWith(link.url, '_blank', 'noopener,noreferrer'))
    expect(get).toHaveBeenCalledWith('abc')
  })

  it('loads a photo through its link, and says so when it is gone', async () => {
    vi.spyOn(assistantApi, 'getAssistantInputLink').mockResolvedValueOnce({ ...link, url: 'https://signed.example.com/me.jpg' })
    const { unmount } = render(<PrivateAttachment inputId="p1" att={{ url: 'espresso-input:p1', filename: 'me.jpg', content_type: 'image/jpeg', size: 90_000 }} />)
    await waitFor(() => expect(screen.getByAltText('me.jpg').getAttribute('src')).toBe('https://signed.example.com/me.jpg'))
    unmount()
    vi.spyOn(assistantApi, 'getAssistantInputLink').mockRejectedValue(new Error('404'))
    render(<PrivateAttachment inputId="p2" att={{ url: 'espresso-input:p2', filename: 'gone.jpg', content_type: 'image/jpeg', size: 90_000 }} />)
    await waitFor(() => expect(screen.getByText('unavailable')).toBeTruthy())
  })
})
