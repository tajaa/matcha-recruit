import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CappeLogin from './CappeLogin'
import CappeSignup from './CappeSignup'
import { postAuthHome } from '../utils/postAuthHome'
import { creatorPaths } from '../creators/creatorPaths'
import { writerPaths } from '../magazine/writers/writerPaths'

function respond(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue({ ok: status < 400, status, statusText: '', json: async () => body })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function at(path: string, element: React.ReactNode) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/cappe/magazines/signup" element={element} />
        <Route path="/cappe/magazines/login" element={element} />
        <Route path="/cappe/writer" element={<p>writer home</p>} />
        <Route path="/cappe/billing" element={<p>billing</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => { sessionStorage.clear() })
afterEach(() => { vi.restoreAllMocks() })

describe('postAuthHome', () => {
  it('sends each kind of account home', () => {
    expect(postAuthHome('writer')).toBe(writerPaths.home)
    expect(postAuthHome('creator')).toBe(creatorPaths.home)
    expect(postAuthHome('business')).toBe('/cappe/sites')
    expect(postAuthHome(undefined)).toBe('/cappe/sites')
  })
})

describe('writer sign-up', () => {
  it('creates a writer account without asking what kind, and ignores a plan in the link', async () => {
    const fetchMock = respond(200, {
      verification_required: false, email: 'ana@example.com', access_token: 'a', refresh_token: 'r',
      account: { account_type: 'writer' }, intended_plan: null,
    })
    at('/cappe/magazines/signup?plan=writer', <CappeSignup writerOnly />)
    expect(screen.getByRole('heading', { name: /Gummfit Magazines/ })).toBeInTheDocument()
    expect(screen.queryByText("I'm building a site for…")).not.toBeInTheDocument()
    expect(screen.queryByText(/You picked the/)).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'ana@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'harbour-123' } })
    fireEvent.click(screen.getByRole('button', { name: /Create account/ }))
    expect(await screen.findByText('writer home')).toBeInTheDocument()
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string)
    expect(body.account_type).toBe('writer')
    expect(body.intended_plan).toBeUndefined()
  })
})

describe('writer sign-in', () => {
  it('takes a writer to their magazine', async () => {
    respond(200, { access_token: 'a', refresh_token: 'r', expires_in: 900, account: { account_type: 'writer' } })
    at('/cappe/magazines/login', <CappeLogin writerOnly />)
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'ana@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'harbour-123' } })
    fireEvent.click(screen.getByRole('button', { name: /Sign in/ }))
    expect(await screen.findByText('writer home')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Start your magazine' })).not.toBeInTheDocument()
  })

  it('turns away an account that isn’t a writer', async () => {
    respond(200, { access_token: 'a', refresh_token: 'r', expires_in: 900, account: { account_type: 'business' } })
    at('/cappe/magazines/login', <CappeLogin writerOnly />)
    expect(screen.getByRole('link', { name: 'Start your magazine' })).toHaveAttribute('href', writerPaths.signup)
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'shop@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'harbour-123' } })
    fireEvent.click(screen.getByRole('button', { name: /Sign in/ }))
    await waitFor(() => expect(screen.getByText(/for Gummfit Magazines writers/)).toBeInTheDocument())
    expect(sessionStorage.getItem('cappe_access_token')).toBeNull()
  })
})
