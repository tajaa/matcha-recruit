import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../../api/client'

const { createMock, updateMock, assignMock } = vi.hoisted(() => ({
  createMock: vi.fn(), updateMock: vi.fn(), assignMock: vi.fn(),
}))

vi.mock('../../../api/employees/scheduleStores', async (importOriginal) => ({
  // The real PartialAssignmentError: the dialog tells it apart with instanceof.
  ...(await importOriginal<typeof import('../../../api/employees/scheduleStores')>()),
  createScheduleStore: createMock,
  updateScheduleStore: updateMock,
  assignEmployeesToStore: assignMock,
}))

import { PartialAssignmentError } from '../../../api/employees/scheduleStores'
import type { StoreSetup } from '../../../hooks/employees/useStoreSetup'
import type { CompanyLocation } from '../../../hooks/useLocationScope'
import { ToastProvider } from '../../ui'
import { EMPTY_STORE, storeFormError, withStoreChange } from '../storeForm'
import {
  EmptyRosterHelp, NoStoresYet, StoreActions, StoreSetupModals, StoreSetupNotice,
} from './StoreSetup'

const DOWNTOWN: CompanyLocation = {
  id: 'loc-1', name: 'Downtown', address: '1 Main', city: 'Austin', state: 'TX',
  zipcode: '78701', is_active: true, timezone: null,
}

const NOT_READY = {
  ready_to_publish: false, missing_fields: ['timezone'],
  message: 'This location needs a timezone before its schedule can be published.',
}

// Reserved example.com addresses only (root CLAUDE.md test-data rule).
const WAITING = [
  { id: 'e1', first_name: 'Sam', last_name: 'Rivera', email: 'sam@example.com', job_title: 'Barista', work_state: 'TX' },
  { id: 'e2', first_name: null, last_name: null, email: 'priya@example.com', job_title: null, work_state: 'TX' },
]

function setup(overrides: Partial<StoreSetup> = {}): StoreSetup {
  return {
    modal: null, setModal: vi.fn(), readiness: null, unassigned: [], refresh: vi.fn(),
    ...overrides,
  }
}

function renderIn(node: React.ReactNode) {
  return render(<MemoryRouter><ToastProvider>{node}</ToastProvider></MemoryRouter>)
}

beforeEach(() => {
  createMock.mockReset()
  updateMock.mockReset()
  assignMock.mockReset()
})

describe('store form rules', () => {
  it('names the first missing field, in form order', () => {
    expect(storeFormError(EMPTY_STORE)).toBe('Give the store a name.')
    const filled = { name: 'D', address: '1 Main', city: 'Austin', state: 'TX', zipcode: '7870', timezone: '' }
    expect(storeFormError(filled)).toMatch(/Zip code/)
    expect(storeFormError({ ...filled, zipcode: '78701' })).toMatch(/time zone/)
    expect(storeFormError({ ...filled, zipcode: '78701-1234', timezone: 'America/Chicago' })).toBeNull()
  })

  it('keeps the time zone in step with the state until the manager picks one', () => {
    const california = withStoreChange(EMPTY_STORE, { state: 'CA' })
    expect(california.timezone).toBe('America/Los_Angeles')
    // Still following: a new one-zone state replaces it; a split-zone state clears it.
    expect(withStoreChange(california, { state: 'NY' }).timezone).toBe('America/New_York')
    expect(withStoreChange(california, { state: 'TX' }).timezone).toBe('')
    // A deliberate choice survives a later state change.
    const chosen = { ...california, timezone: 'America/Phoenix' }
    expect(withStoreChange(chosen, { state: 'NY' }).timezone).toBe('America/Phoenix')
  })
})

describe('StoreSetupNotice', () => {
  it('renders nothing for a ready, fully staffed store', () => {
    renderIn(
      <StoreSetupNotice setup={setup({ readiness: { ready_to_publish: true, missing_fields: [], message: null } })} store={DOWNTOWN} />,
    )
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('says what the store is missing before a week is built, with the fix', () => {
    const stores = setup({ readiness: NOT_READY })
    renderIn(<StoreSetupNotice setup={stores} store={DOWNTOWN} />)

    expect(screen.getByText(NOT_READY.message)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Fix store details' }))
    expect(stores.setModal).toHaveBeenCalledWith('edit')
  })

  it('counts the employees an import left without a store and offers to place them', () => {
    const stores = setup({ unassigned: WAITING })
    renderIn(<StoreSetupNotice setup={stores} store={DOWNTOWN} />)

    expect(screen.getByText(/2 employees aren't assigned to a store/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Assign to Downtown' }))
    expect(stores.setModal).toHaveBeenCalledWith('assign')
  })
})

describe('store actions and empty states', () => {
  it('offers Add always and Edit only once a store is selected', () => {
    const stores = setup()
    const { rerender } = renderIn(<StoreActions setup={stores} canEdit={false} />)
    expect(screen.queryByRole('button', { name: 'Edit store details' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Add store/ }))
    expect(stores.setModal).toHaveBeenCalledWith('add')

    rerender(<MemoryRouter><ToastProvider><StoreActions setup={stores} canEdit /></ToastProvider></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: 'Edit store details' }))
    expect(stores.setModal).toHaveBeenCalledWith('edit')
  })

  it('gives a brand-new account one thing to do: add a store', () => {
    const stores = setup()
    renderIn(<NoStoresYet setup={stores} />)
    fireEvent.click(screen.getByRole('button', { name: /Add a store/ }))
    expect(stores.setModal).toHaveBeenCalledWith('add')
  })

  it('explains an empty roster and points at whichever fix applies', () => {
    const stores = setup({ unassigned: WAITING })
    const { unmount } = renderIn(<EmptyRosterHelp setup={stores} storeName="Downtown" />)
    expect(screen.getByText('No one is assigned to Downtown yet.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Assign 2 waiting employees' }))
    expect(stores.setModal).toHaveBeenCalledWith('assign')
    unmount()

    // Nobody waiting: the roster itself has not been imported yet.
    renderIn(<EmptyRosterHelp setup={setup()} storeName="Downtown" />)
    expect(screen.getByRole('link', { name: 'Import your roster' })).toHaveAttribute('href', '/app/employees')
  })
})

describe('StoreSetupModals', () => {
  it('adds a store with an inferred time zone and selects it', async () => {
    const user = userEvent.setup()
    const stores = setup({ modal: 'add' })
    const onStoreSaved = vi.fn()
    createMock.mockResolvedValue({ id: 'loc-2', name: 'Mission' })
    renderIn(<StoreSetupModals setup={stores} store={DOWNTOWN} onStoreSaved={onStoreSaved} onRosterChanged={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: 'Add store' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Give the store a name.')
    expect(createMock).not.toHaveBeenCalled()

    await user.type(screen.getByLabelText(/Store name/), ' Mission ')
    await user.type(screen.getByLabelText(/Street address/), '455 Valencia St')
    await user.type(screen.getByLabelText(/City/), 'San Francisco')
    await user.click(screen.getByRole('button', { name: /^State/ }))
    await user.click(screen.getByRole('button', { name: 'California' }))
    await user.type(screen.getByLabelText(/Zip code/), '94103')
    await user.click(screen.getByRole('button', { name: 'Add store' }))

    await waitFor(() => expect(onStoreSaved).toHaveBeenCalledWith({ id: 'loc-2', name: 'Mission' }, true))
    expect(createMock).toHaveBeenCalledWith({
      name: 'Mission', address: '455 Valencia St', city: 'San Francisco',
      state: 'CA', zipcode: '94103', timezone: 'America/Los_Angeles',
    })
    expect(stores.setModal).toHaveBeenCalledWith(null)
    expect(stores.refresh).toHaveBeenCalled()
  })

  it('opens the fix form on the selected store with the reason and saves the missing time zone', async () => {
    const user = userEvent.setup()
    const stores = setup({ modal: 'edit', readiness: NOT_READY })
    const onStoreSaved = vi.fn()
    updateMock.mockResolvedValue({ id: 'loc-1', name: 'Downtown' })
    renderIn(<StoreSetupModals setup={stores} store={DOWNTOWN} onStoreSaved={onStoreSaved} onRosterChanged={vi.fn()} />)

    expect(screen.getByText('Store details')).toBeInTheDocument()
    expect(screen.getByText(NOT_READY.message)).toBeInTheDocument()
    expect(screen.getByLabelText(/Store name/)).toHaveValue('Downtown')

    // Texas has two zones, so nothing was pre-filled and saving is refused.
    await user.click(screen.getByRole('button', { name: 'Save store' }))
    expect(screen.getByRole('alert')).toHaveTextContent(/time zone/)

    await user.click(screen.getByRole('button', { name: /^Time zone/ }))
    await user.click(screen.getByRole('button', { name: 'US Central (Chicago)' }))
    await user.click(screen.getByRole('button', { name: 'Save store' }))

    await waitFor(() => expect(onStoreSaved).toHaveBeenCalledWith({ id: 'loc-1', name: 'Downtown' }, false))
    expect(updateMock).toHaveBeenCalledWith('loc-1', expect.objectContaining({ timezone: 'America/Chicago' }))
  })

  it('shows the server refusal inside the form and keeps it open', async () => {
    const user = userEvent.setup()
    const stores = setup({ modal: 'edit' })
    updateMock.mockRejectedValue(new ApiError('Request failed', 422, { detail: 'Select a valid IANA time zone, such as America/Los_Angeles.' }))
    renderIn(<StoreSetupModals setup={stores} store={{ ...DOWNTOWN, timezone: 'America/Chicago' }} onStoreSaved={vi.fn()} onRosterChanged={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: 'Save store' }))

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Select a valid IANA time zone'))
    expect(stores.setModal).not.toHaveBeenCalledWith(null)
  })

  it('places the ticked employees at the store and re-reads the roster', async () => {
    const user = userEvent.setup()
    const stores = setup({ modal: 'assign', unassigned: WAITING })
    const onRosterChanged = vi.fn()
    assignMock.mockResolvedValue({ assigned: ['e1'], skipped: [] })
    renderIn(<StoreSetupModals setup={stores} store={DOWNTOWN} onStoreSaved={vi.fn()} onRosterChanged={onRosterChanged} />)

    // Everyone starts ticked; an employee with no name shows their email.
    expect(screen.getByText('Sam Rivera')).toBeInTheDocument()
    await user.click(screen.getByLabelText(/priya@example.com/))
    await user.click(screen.getByRole('button', { name: 'Assign 1 to Downtown' }))

    await waitFor(() => expect(onRosterChanged).toHaveBeenCalled())
    expect(assignMock).toHaveBeenCalledWith('loc-1', ['e1'])
    expect(stores.refresh).toHaveBeenCalled()
    expect(await screen.findByText('1 employee assigned')).toBeInTheDocument()
  })

  it('cannot assign nobody, and reports a failed assignment in place', async () => {
    const user = userEvent.setup()
    const stores = setup({ modal: 'assign', unassigned: WAITING })
    assignMock.mockRejectedValue(new ApiError('Request failed', 403, { detail: 'You are not authorized to manage this location' }))
    renderIn(<StoreSetupModals setup={stores} store={DOWNTOWN} onStoreSaved={vi.fn()} onRosterChanged={vi.fn()} />)

    await user.click(screen.getByLabelText(/Select all/))
    expect(screen.getByRole('button', { name: /^Assign\s+to Downtown/ })).toBeDisabled()
    await user.click(screen.getByLabelText(/Select all/))
    await user.click(screen.getByRole('button', { name: 'Assign 2 to Downtown' }))

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('not authorized'))
  })

  it('reports a partly finished assignment honestly and keeps the rest ready to retry', async () => {
    const user = userEvent.setup()
    const stores = setup({ modal: 'assign', unassigned: WAITING })
    const onRosterChanged = vi.fn()
    assignMock.mockRejectedValueOnce(
      new PartialAssignmentError(['e1'], new ApiError('Request failed', 503, { detail: 'Service unavailable' })),
    )
    renderIn(<StoreSetupModals setup={stores} store={DOWNTOWN} onStoreSaved={vi.fn()} onRosterChanged={onRosterChanged} />)

    await user.click(screen.getByRole('button', { name: 'Assign 2 to Downtown' }))

    // Not "failed": one person is on the roster now, and the page re-reads it.
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('1 employee was assigned, then this stopped: Service unavailable'))
    expect(onRosterChanged).toHaveBeenCalled()
    expect(stores.refresh).toHaveBeenCalled()
    // The dialog stays open with only the one still waiting selected.
    expect(stores.setModal).not.toHaveBeenCalledWith(null)
    assignMock.mockResolvedValueOnce({ assigned: ['e2'], skipped: [] })
    await user.click(screen.getByRole('button', { name: 'Assign 1 to Downtown' }))
    await waitFor(() => expect(assignMock).toHaveBeenLastCalledWith('loc-1', ['e2']))
  })
})
