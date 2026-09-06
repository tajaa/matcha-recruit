import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../../../components/ui'
import CredentialTemplates from './CredentialTemplates'

const api = vi.hoisted(() => ({
  fetchRoleCategories: vi.fn(),
  fetchTemplates: vi.fn(),
  fetchCredentialTypeSettings: vi.fn(),
  createCredentialType: vi.fn(),
  updateCredentialTypeSettings: vi.fn(),
  resetCredentialTypeSettings: vi.fn(),
}))

vi.mock('../../../api/employees/credentialTemplates', () => ({
  ...api,
  approveTemplate: vi.fn(),
  rejectTemplate: vi.fn(),
  updateTemplate: vi.fn(),
  triggerResearch: vi.fn(),
  deleteTemplate: vi.fn(),
  previewRequirements: vi.fn(),
  updateCredentialTypeSettings: api.updateCredentialTypeSettings,
  resetCredentialTypeSettings: api.resetCredentialTypeSettings,
}))

const systemType = {
  id: 'system-type', key: 'food_handler_card', label: 'Food Handler Card',
  category: 'clearance', description: null, has_expiration: true,
  has_number: true, has_state: true, is_system: true,
}

describe('CredentialTemplates custom options', () => {
  beforeEach(() => {
    api.fetchRoleCategories.mockReset().mockResolvedValue([])
    api.fetchTemplates.mockReset().mockResolvedValue([])
    api.fetchCredentialTypeSettings.mockReset().mockResolvedValue({
      is_configured: false,
      manageable: true,
      selected_type_ids: [],
      credential_types: [systemType],
    })
    api.createCredentialType.mockReset()
    api.updateCredentialTypeSettings.mockReset()
    api.resetCredentialTypeSettings.mockReset()
  })

  it('creates and immediately displays a tenant credential option', async () => {
    const customType = {
      ...systemType,
      id: 'custom-type',
      key: 'custom_123',
      label: 'Forklift Certification',
      has_number: false,
      has_state: false,
      is_system: false,
      company_id: 'company-1',
    }
    api.createCredentialType.mockResolvedValue(customType)
    api.fetchCredentialTypeSettings
      .mockReset()
      .mockResolvedValueOnce({
        is_configured: false,
        manageable: true,
        selected_type_ids: [],
        credential_types: [systemType],
      })
      .mockResolvedValueOnce({
        is_configured: true,
        manageable: true,
        selected_type_ids: [systemType.id, customType.id],
        credential_types: [systemType, customType],
      })
    render(<ToastProvider><CredentialTemplates /></ToastProvider>)

    fireEvent.click(await screen.findByRole('button', { name: 'Dropdown options' }))
    fireEvent.change(await screen.findByLabelText('Name'), { target: { value: 'Forklift Certification' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add credential option' }))

    await waitFor(() => expect(api.createCredentialType).toHaveBeenCalledWith({
      label: 'Forklift Certification',
      category: 'clearance',
      description: undefined,
      has_expiration: true,
      has_number: false,
      has_state: false,
    }))
    expect(await screen.findAllByText('Forklift Certification')).not.toHaveLength(0)
    expect(screen.getByRole('checkbox', { name: /Forklift Certification/ })).toBeChecked()
  })

  it('serializes creation with settings changes and reloads authoritative state', async () => {
    const customType = {
      ...systemType,
      id: 'custom-type',
      key: 'custom_123',
      label: 'Forklift Certification',
      is_system: false,
      company_id: 'company-1',
    }
    let resolveCreate: ((value: typeof customType) => void) | undefined
    api.createCredentialType.mockReturnValue(new Promise((resolve) => { resolveCreate = resolve }))
    api.fetchCredentialTypeSettings
      .mockReset()
      .mockResolvedValueOnce({
        is_configured: false,
        manageable: true,
        selected_type_ids: [],
        credential_types: [systemType],
      })
      .mockResolvedValueOnce({
        is_configured: true,
        manageable: true,
        selected_type_ids: [systemType.id, customType.id],
        credential_types: [systemType, customType],
      })
    render(<ToastProvider><CredentialTemplates /></ToastProvider>)

    fireEvent.click(await screen.findByRole('button', { name: 'Dropdown options' }))
    fireEvent.change(await screen.findByLabelText('Name'), { target: { value: 'Forklift Certification' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add credential option' }))

    expect(screen.getByRole('button', { name: 'Save options' })).toBeDisabled()
    expect(screen.getByRole('checkbox', { name: /Food Handler Card/ })).toBeDisabled()

    await act(async () => { resolveCreate?.(customType) })

    expect(await screen.findByRole('checkbox', { name: /Forklift Certification/ })).toBeChecked()
    expect(api.fetchCredentialTypeSettings).toHaveBeenCalledTimes(2)
  })

  it('shows an actionable save error and keeps the entered name', async () => {
    api.createCredentialType.mockRejectedValue(new Error('A credential option with this name already exists'))
    render(<ToastProvider><CredentialTemplates /></ToastProvider>)

    fireEvent.click(await screen.findByRole('button', { name: 'Dropdown options' }))
    const name = await screen.findByLabelText('Name')
    fireEvent.change(name, { target: { value: 'Forklift Certification' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add credential option' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('already exists')
    expect(name).toHaveValue('Forklift Certification')
  })

  it('explains that an empty name is required before saving', async () => {
    render(<ToastProvider><CredentialTemplates /></ToastProvider>)

    fireEvent.click(await screen.findByRole('button', { name: 'Dropdown options' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Add credential option' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Enter a name')
    expect(api.createCredentialType).not.toHaveBeenCalled()
  })
})
