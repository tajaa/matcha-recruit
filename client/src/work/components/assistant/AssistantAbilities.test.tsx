import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import AssistantAbilities from './AssistantAbilities'
import { ApiError } from '../../../api/client'
import { apiErrorText } from '../../utils/apiErrorText'
import type { AssistantAbilities as Abilities, AssistantAbility } from '../../api/matchaWork/assistant'

const mock = vi.hoisted(() => ({
  list: vi.fn(), enable: vi.fn(), disable: vi.fn(), connect: vi.fn(),
}))
vi.mock('../../api/matchaWork/assistant', () => ({
  listAssistantAbilities: mock.list,
  enableAssistantAbility: mock.enable,
  disableAssistantAbility: mock.disable,
  connectGoogleFor: mock.connect,
}))

function ability(over: Partial<AssistantAbility>): AssistantAbility {
  return {
    key: 'email', label: 'Email', always_on: false, enabled: false, available: false, reason: null,
    needs_consent: true, needs_connection: false, missing_scopes: [], private_only: true, acts: true,
    disclosure: { version: 'email-openai-1', title: 'Let Espresso work with your email', body: ['Messages it reads are sent to OpenAI.'] },
    consent_outdated: false, settings: {}, ...over,
  }
}

function payload(abilities: AssistantAbility[], over: Partial<Abilities> = {}): Abilities {
  return { abilities, google: { connected: true, scopes: [] }, commit_mode: 'dry_run', ...over }
}

const web = ability({ key: 'web', label: 'Web research', always_on: true, enabled: true, available: true, acts: false, private_only: false, disclosure: null, needs_consent: false })

beforeEach(() => {
  Object.values(mock).forEach((fn) => fn.mockReset())
})

describe('AssistantAbilities', () => {
  it('lists what is always on and what must be switched on, and says it is a dry run', async () => {
    mock.list.mockResolvedValue(payload([web, ability({})]))
    render(<AssistantAbilities onClose={() => {}} />)
    expect(await screen.findByText('Web research')).toBeTruthy()
    expect(screen.getByText('Always on')).toBeTruthy()
    expect(screen.getByText('Looks things up')).toBeTruthy()
    expect(screen.getByText(/Acts for you, only in this private conversation/)).toBeTruthy()
    expect(screen.getByText(/nothing leaves yet/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Switch on' })).toBeTruthy()
  })

  it('switches an ability on only after the disclosure is accepted, at its version', async () => {
    mock.list.mockResolvedValue(payload([ability({})], { commit_mode: 'live' }))
    mock.enable.mockResolvedValue({ key: 'email', enabled: true })
    render(<AssistantAbilities onClose={() => {}} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Switch on' }))
    expect(screen.getByText('Messages it reads are sent to OpenAI.')).toBeTruthy()
    expect(mock.enable).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'I understand, switch it on' }))
    await waitFor(() => expect(mock.enable).toHaveBeenCalledWith('email', { consent_version: 'email-openai-1', settings: {} }))
    await waitFor(() => expect(mock.list).toHaveBeenCalledTimes(2))
    expect(screen.queryByText(/nothing leaves yet/)).toBeNull()
  })

  it('closing the disclosure switches nothing on', async () => {
    mock.list.mockResolvedValue(payload([ability({ consent_outdated: true })]))
    render(<AssistantAbilities onClose={() => {}} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Review and switch on' }))
    fireEvent.click(screen.getByRole('button', { name: 'Not now' }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(mock.enable).not.toHaveBeenCalled()
  })

  it('a booking needs a name and a way to be reached', async () => {
    const booking = ability({
      key: 'reservations', label: 'Reservations',
      disclosure: { version: 'reservations-1', title: 'Let Espresso book for you', body: ['It never enters payment details.'] },
    })
    mock.list.mockResolvedValue(payload([booking]))
    mock.enable.mockRejectedValueOnce(new ApiError('bad', 422, { detail: "That phone number doesn't look right." }))
    mock.enable.mockResolvedValue({ key: 'reservations', enabled: true })
    render(<AssistantAbilities onClose={() => {}} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Switch on' }))
    const accept = screen.getByRole('button', { name: 'I understand, switch it on' }) as HTMLButtonElement
    expect(accept.disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'Ana Lee' } })
    expect(accept.disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('Phone'), { target: { value: 'call me' } })
    expect(accept.disabled).toBe(false)
    fireEvent.click(accept)
    expect((await screen.findByRole('alert')).textContent).toBe("That phone number doesn't look right.")
    fireEvent.change(screen.getByLabelText('Phone'), { target: { value: '+1 555 010 0100' } })
    fireEvent.click(accept)
    await waitFor(() => expect(mock.enable).toHaveBeenLastCalledWith('reservations', {
      consent_version: 'reservations-1',
      settings: { contact: { name: 'Ana Lee', phone: '+1 555 010 0100', email: '' } },
    }))
  })

  it('offers to reconnect Google when a permission is missing, and to switch off', async () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null)
    mock.list.mockResolvedValue(payload([
      ability({ enabled: true, available: true, needs_consent: false, needs_connection: true, reason: 'Reconnect Google to allow everything this can do.' }),
    ]))
    mock.connect.mockResolvedValue({ auth_url: 'https://accounts.google.com/o/oauth2/v2/auth?x=1' })
    mock.disable.mockResolvedValue({ key: 'email', enabled: false })
    render(<AssistantAbilities onClose={() => {}} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Reconnect Google' }))
    await waitFor(() => expect(mock.connect).toHaveBeenCalledWith('email'))
    await waitFor(() => expect(open).toHaveBeenCalledWith(
      'https://accounts.google.com/o/oauth2/v2/auth?x=1', 'espresso-google', expect.any(String)))
    // Google's popup says when it is done, and the list is read again.
    window.dispatchEvent(new MessageEvent('message', { data: 'gmail-connected' }))
    await waitFor(() => expect(mock.list).toHaveBeenCalledTimes(2))
    fireEvent.click(screen.getByRole('button', { name: 'Switch off' }))
    await waitFor(() => expect(mock.disable).toHaveBeenCalledWith('email'))
    open.mockRestore()
  })

  it('says so when the list cannot be loaded, and closes', async () => {
    mock.list.mockRejectedValue(new ApiError('nope', 403, { detail: { message: 'Not switched on for this workspace.' } }))
    const onClose = vi.fn()
    render(<AssistantAbilities onClose={onClose} />)
    expect((await screen.findByRole('alert')).textContent).toBe('Not switched on for this workspace.')
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onClose).toHaveBeenCalled()
  })
})

describe('apiErrorText', () => {
  it('reads the server detail, whichever shape it has', () => {
    expect(apiErrorText(new ApiError('x', 400, { detail: 'Plain.' }), 'fallback')).toBe('Plain.')
    expect(apiErrorText(new ApiError('x', 400, { detail: { message: 'Nested.' } }), 'fallback')).toBe('Nested.')
    expect(apiErrorText(new ApiError('x', 400, { detail: { code: 'no_message' } }), 'fallback')).toBe('fallback')
    expect(apiErrorText(new ApiError('x', 500, null), 'fallback')).toBe('fallback')
    expect(apiErrorText(new Error('network'), 'fallback')).toBe('fallback')
  })
})
