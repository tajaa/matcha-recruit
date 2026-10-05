import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ResendVerification from './ResendVerification'

function respond(status: number) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status < 400, status, statusText: '', json: async () => (status < 400 ? { status: 'ok' } : { detail: 'Too many requests' }),
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('ResendVerification', () => {
  afterEach(() => { vi.restoreAllMocks() })

  it('sends to the given address and says so only after the request succeeds', async () => {
    const fetchMock = respond(202)
    render(<ResendVerification email="owner@example.com" />)
    expect(screen.getByRole('status')).toBeEmptyDOMElement()

    fireEvent.click(screen.getByRole('button', { name: 'Resend confirmation email' }))

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('owner@example.com'))
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ email: 'owner@example.com' })
    // Still usable: a second try is allowed.
    expect(screen.getByRole('button', { name: 'Send it again' })).toBeEnabled()
  })

  it('reports a rate limit instead of claiming the email went out', async () => {
    respond(429)
    render(<ResendVerification email="owner@example.com" />)
    fireEvent.click(screen.getByRole('button'))
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(/wait a minute/i))
    expect(screen.getByRole('button', { name: 'Resend confirmation email' })).toBeEnabled()
  })

  it('reports a failed request', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    render(<ResendVerification email="owner@example.com" />)
    fireEvent.click(screen.getByRole('button'))
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(/couldn’t send/i))
  })

  it('asks for the address when it does not know it', async () => {
    const fetchMock = respond(202)
    render(<ResendVerification label="Send a new link" />)
    const button = screen.getByRole('button', { name: 'Send a new link' })
    expect(button).toBeDisabled()

    fireEvent.change(screen.getByLabelText('Email you signed up with'), { target: { value: ' owner@example.com ' } })
    fireEvent.click(button)

    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ email: 'owner@example.com' })
  })
})
