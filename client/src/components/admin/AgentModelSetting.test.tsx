import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AgentModelSetting } from './AgentModelSetting'
import { adminSettingsApi } from '../../api/admin/platformSettings'

vi.mock('../../api/admin/platformSettings', () => ({ adminSettingsApi: { setAgentModel: vi.fn() } }))

beforeEach(() => { vi.clearAllMocks() })

describe('AgentModelSetting', () => {
  it('saves a Claude pick and reports what the server stored', async () => {
    vi.mocked(adminSettingsApi.setAgentModel).mockResolvedValue({ agent_model: 'claude-sonnet-5-5' })
    const onSaved = vi.fn()
    render(<AgentModelSetting current="default" anthropicConfigured onSaved={onSaved} />)

    expect(screen.getByRole('radio', { name: /Default/ })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('button', { name: 'Saved' })).toBeDisabled()
    fireEvent.click(screen.getByRole('radio', { name: /Claude Sonnet 5.5/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith('claude-sonnet-5-5'))
    expect(adminSettingsApi.setAgentModel).toHaveBeenCalledWith('claude-sonnet-5-5')
  })

  it('cannot pick Claude while the server has no key', () => {
    render(<AgentModelSetting current="default" anthropicConfigured={false} onSaved={vi.fn()} />)
    fireEvent.click(screen.getByRole('radio', { name: /Claude Haiku 5.5/ }))
    expect(screen.getByRole('radio', { name: /Claude Haiku 5.5/ })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByRole('button', { name: 'Saved' })).toBeDisabled()
    expect(screen.getByText(/ANTHROPIC_API_KEY/)).toBeInTheDocument()
  })

  it('shows a failed save instead of pretending it worked', async () => {
    vi.mocked(adminSettingsApi.setAgentModel).mockRejectedValue(new Error('Claude is not configured'))
    const onSaved = vi.fn()
    render(<AgentModelSetting current="default" anthropicConfigured onSaved={onSaved} />)
    fireEvent.click(screen.getByRole('radio', { name: /Claude Haiku 5.5/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(screen.getByText('Claude is not configured')).toBeInTheDocument())
    expect(onSaved).not.toHaveBeenCalled()
  })
})
