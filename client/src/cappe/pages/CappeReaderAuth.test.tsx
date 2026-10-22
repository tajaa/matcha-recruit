import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CappeLogin from './CappeLogin'
import CappeSignup from './CappeSignup'
import { postAuthHome } from '../utils/postAuthHome'
import { readerPaths } from '../magazine/shelf/readerPaths'

function respond(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue({ ok: status < 400, status, statusText: '', json: async () => body })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function Where() {
  const loc = useLocation()
  return <p>at {loc.pathname}{loc.search}</p>
}

function at(path: string, element: React.ReactNode) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/cappe/reader/signup" element={element} />
        <Route path="/cappe/reader/login" element={element} />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  )
}

function fill() {
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'rae@example.com' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'harbour-123' } })
}

beforeEach(() => { sessionStorage.clear() })
afterEach(() => { vi.restoreAllMocks() })

describe('reader accounts', () => {
  it('land on their magazines', () => {
    expect(postAuthHome('reader')).toBe(readerPaths.home)
  })

  it('sign up as a reader with no plan, and go back to the magazine they came from', async () => {
    const fetchMock = respond(200, {
      verification_required: false, email: 'rae@example.com', access_token: 'a', refresh_token: 'r',
      account: { account_type: 'reader' }, intended_plan: null,
    })
    at('/cappe/reader/signup?plan=business&next=%2Fcappe%2Freader%2Fm%2Fsalt', <CappeSignup readerOnly />)
    expect(screen.getByRole('heading', { name: /Gummfit reader account/ })).toBeInTheDocument()
    expect(screen.queryByText("I'm building a site for…")).not.toBeInTheDocument()
    expect(screen.queryByText(/You picked the/)).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute(
      'href', '/cappe/reader/login?next=%2Fcappe%2Freader%2Fm%2Fsalt')
    fill()
    fireEvent.click(screen.getByRole('button', { name: /Create account/ }))
    expect(await screen.findByText('at /cappe/reader/m/salt')).toBeInTheDocument()
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string)
    expect(body.account_type).toBe('reader')
    expect(body.intended_plan).toBeUndefined()
  })

  it('sign in back to where they were going, but only on the dashboard', async () => {
    respond(200, { access_token: 'a', refresh_token: 'r', expires_in: 900, account: { account_type: 'writer' } })
    at('/cappe/reader/login?next=%2Fcappe%2Freader%2Fm%2Fsalt%2Flow-tide', <CappeLogin readerOnly />)
    expect(screen.getByRole('heading', { name: 'Sign in to your magazines' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Create one' })).toHaveAttribute(
      'href', '/cappe/reader/signup?next=%2Fcappe%2Freader%2Fm%2Fsalt%2Flow-tide')
    fill()
    fireEvent.click(screen.getByRole('button', { name: /Sign in/ }))
    expect(await screen.findByText('at /cappe/reader/m/salt/low-tide')).toBeInTheDocument()
  })

  it('ignore a next that leaves the dashboard', async () => {
    respond(200, { access_token: 'a', refresh_token: 'r', expires_in: 900, account: { account_type: 'reader' } })
    at('/cappe/reader/login?next=%2Fcappe%2Fsites', <CappeLogin readerOnly />)
    fill()
    fireEvent.click(screen.getByRole('button', { name: /Sign in/ }))
    expect(await screen.findByText('at /cappe/reader')).toBeInTheDocument()
  })
})
