import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CappeLogin from './CappeLogin'
import CappeSignup from './CappeSignup'
import CappeVerify from './CappeVerify'

function respond(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status < 400, status, statusText: '', json: async () => body,
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function at(path: string, element: React.ReactNode) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/cappe/verify" element={element} />
        <Route path="/cappe/login" element={element} />
        <Route path="/cappe/website-setup" element={element} />
        <Route path="/cappe/sites" element={<p>dashboard</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => { sessionStorage.clear() })
afterEach(() => { vi.restoreAllMocks() })

describe('CappeVerify', () => {
  it('offers a new link when the link has expired', async () => {
    respond(410, { detail: { code: 'verification_expired', message: 'This confirmation link has expired. Request a new one.' } })
    at('/cappe/verify?token=abc', <CappeVerify />)

    expect(await screen.findByRole('heading', { name: 'This link has expired' })).toBeInTheDocument()
    expect(screen.getByLabelText('Email you signed up with')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send a new link' })).toBeInTheDocument()
  })

  it('points a used link at sign-in first, with resend still available', async () => {
    respond(400, { detail: { code: 'verification_invalid', message: 'This confirmation link is invalid or has already been used.' } })
    at('/cappe/verify?token=abc', <CappeVerify />)

    expect(await screen.findByRole('heading', { name: "Link didn't work" })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Go to sign in' })).toHaveAttribute('href', '/cappe/login')
    expect(screen.getByText(/already confirmed your email, just sign in/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send a new link' })).toBeInTheDocument()
  })

  it('says so when the link has no token', async () => {
    at('/cappe/verify', <CappeVerify />)
    expect(await screen.findByText(/missing its token/)).toBeInTheDocument()
  })

  it('stores the session on success', async () => {
    respond(200, { access_token: 'a', refresh_token: 'r', expires_in: 900, account: { account_type: 'business' } })
    at('/cappe/verify?token=abc', <CappeVerify />)
    expect(await screen.findByRole('heading', { name: "You're in" })).toBeInTheDocument()
    expect(sessionStorage.getItem('cappe_access_token')).toBe('a')
  })
})

describe('CappeLogin', () => {
  function submit() {
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'owner@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'correct horse' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  }

  it('offers a resend when the account is unconfirmed, keyed on the error code', async () => {
    // Wording deliberately unlike the old regex target: only the code matters.
    respond(403, { detail: { code: 'email_unverified', message: 'Not yet verified.' } })
    at('/cappe/login', <CappeLogin />)
    submit()

    expect(await screen.findByRole('alert')).toHaveTextContent('Not yet verified.')
    expect(screen.getByRole('button', { name: 'Resend confirmation email' })).toBeInTheDocument()
  })

  it('does not offer a resend for a wrong password', async () => {
    respond(401, { detail: 'Incorrect email or password' })
    at('/cappe/login', <CappeLogin />)
    submit()

    expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect email or password')
    expect(screen.queryByRole('button', { name: 'Resend confirmation email' })).toBeNull()
  })
})

describe('CappeSignup', () => {
  function fill(email: string) {
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: email } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'correct horse' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }))
  }

  it('shows a readable message for a rejected field', async () => {
    respond(422, { detail: [{ loc: ['body', 'email'], msg: 'value is not a valid email address' }] })
    at('/cappe/website-setup', <CappeSignup />)
    fill('owner@example')

    expect(await screen.findByRole('alert')).toHaveTextContent('Email: value is not a valid email address')
  })

  it('lets the person fix a mistyped address from the confirm screen', async () => {
    respond(201, { verification_required: true, email: 'ownr@example.com' })
    at('/cappe/website-setup', <CappeSignup />)
    fill('ownr@example.com')

    expect(await screen.findByRole('heading', { name: 'Confirm your email' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Resend the email' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Wrong address/ }))
    await waitFor(() => expect(screen.getByLabelText('Email')).toHaveValue('ownr@example.com'))
  })
})
