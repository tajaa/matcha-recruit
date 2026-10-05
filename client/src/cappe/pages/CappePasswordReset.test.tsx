import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { setCappeTokens } from '../api'
import CappeForgotPassword from './CappeForgotPassword'
import CappeLogin from './CappeLogin'
import CappeResetPassword from './CappeResetPassword'

function respond(status: number, body: unknown = null) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status < 400, status, statusText: '', json: async () => body,
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function at(entry: string) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/cappe/login" element={<CappeLogin />} />
        <Route path="/cappe/forgot-password" element={<CappeForgotPassword />} />
        <Route path="/cappe/reset-password" element={<CappeResetPassword />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  sessionStorage.clear()
  // Some Node versions ship a `localStorage` global that is undefined under
  // jsdom; clearCappeTokens touches it before sessionStorage.
  if (typeof localStorage === 'undefined') {
    vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => {}, removeItem: () => {}, clear: () => {} })
  }
})
afterEach(() => { vi.restoreAllMocks() })

describe('forgot password', () => {
  it('is reachable from the sign-in page', () => {
    at('/cappe/login')
    fireEvent.click(screen.getByRole('link', { name: 'Forgot password?' }))
    expect(screen.getByRole('heading', { name: 'Reset your password' })).toBeInTheDocument()
  })

  it('confirms without saying whether the address has an account', async () => {
    const fetchMock = respond(202, { status: 'ok' })
    at('/cappe/forgot-password')
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: ' owner@example.com ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send reset link' }))

    expect(await screen.findByRole('heading', { name: 'Check your email' })).toBeInTheDocument()
    expect(screen.getByText(/If/)).toHaveTextContent('If owner@example.com has a Gummfit account')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ email: 'owner@example.com' })
  })

  it('explains a rate limit', async () => {
    respond(429, { detail: 'Too many requests' })
    at('/cappe/forgot-password')
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'owner@example.com' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send reset link' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/wait a minute/i)
  })
})

describe('reset password', () => {
  function fill(password: string, confirm = password) {
    fireEvent.change(screen.getByLabelText('New password'), { target: { value: password } })
    fireEvent.change(screen.getByLabelText('Type it again'), { target: { value: confirm } })
    fireEvent.click(screen.getByRole('button', { name: 'Update password' }))
  }

  it('sends the token from the URL fragment and signs this tab out', async () => {
    const fetchMock = respond(204)
    setCappeTokens('stale-access', 'stale-refresh')
    at('/cappe/reset-password#token=tok-1')
    fill('a new password')

    expect(await screen.findByRole('heading', { name: 'Password updated' })).toBeInTheDocument()
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ token: 'tok-1', password: 'a new password' })
    expect(sessionStorage.getItem('cappe_access_token')).toBeNull()
    expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/cappe/login')
  })

  it('catches a mismatch before calling the server', () => {
    const fetchMock = respond(204)
    at('/cappe/reset-password#token=tok-1')
    fill('a new password', 'a new passwrod')
    expect(screen.getByRole('alert')).toHaveTextContent('don’t match')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('offers a new link when this one has expired', async () => {
    respond(410, { detail: { code: 'reset_expired', message: 'This reset link has expired. Request a new one.' } })
    at('/cappe/reset-password#token=tok-1')
    fill('a new password')

    expect(await screen.findByText('This reset link has expired. Request a new one.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Get a new link' })).toHaveAttribute('href', '/cappe/forgot-password')
  })

  it('does not show a form for a link with no token', () => {
    at('/cappe/reset-password')
    expect(screen.queryByLabelText('New password')).toBeNull()
    expect(screen.getByRole('link', { name: 'Get a new link' })).toBeInTheDocument()
  })

  it('keeps the form on an unrelated failure so the person can retry', async () => {
    respond(500, null)
    at('/cappe/reset-password#token=tok-1')
    fill('a new password')
    expect(await screen.findByRole('alert')).toHaveTextContent(/try again/i)
    expect(screen.getByLabelText('New password')).toBeInTheDocument()
  })
})
