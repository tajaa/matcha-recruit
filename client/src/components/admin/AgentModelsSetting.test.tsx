import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AgentModelsSetting } from './AgentModelsSetting'
import {
  adminSettingsApi, type AgentModelApp, type AgentModelChoice, type AgentModels,
} from '../../api/admin/platformSettings'

vi.mock('../../api/admin/platformSettings', () => ({ adminSettingsApi: { setAgentModels: vi.fn() } }))

const REGISTRY: AgentModelApp[] = [
  {
    key: 'matcha',
    label: 'Matcha',
    description: 'The HR and operations platform.',
    surfaces: [
      { key: 'matcha.huume', label: 'Huume', description: 'Threads.', builtin: 'OpenAI Luna' },
      { key: 'matcha.ir', label: 'Incidents (IR)', description: 'Analysis.', builtin: 'Gemini' },
    ],
  },
  { key: 'espresso', label: 'Espresso', description: 'Personal.', surfaces: [] },
]

const MODELS: AgentModels = {
  apps: { matcha: 'claude-haiku-5-5', espresso: 'default' },
  surfaces: { 'matcha.huume': 'inherit', 'matcha.ir': 'inherit' },
}

const CHOICES: AgentModelChoice[] = [
  { id: 'claude-haiku-5-5', label: 'Claude Haiku 5.5' },
  { id: 'claude-sonnet-5-5', label: 'Claude Sonnet 5.5' },
]

beforeEach(() => { vi.clearAllMocks() })

function setup(anthropicConfigured = true) {
  const onSaved = vi.fn()
  render(
    <AgentModelsSetting
      models={MODELS} registry={REGISTRY} choices={CHOICES} version="v1"
      anthropicConfigured={anthropicConfigured} onSaved={onSaved}
    />,
  )
  return { user: userEvent.setup(), onSaved }
}

describe('AgentModelsSetting', () => {
  it('lists each app with its products, following the app until overridden', () => {
    setup()
    expect(screen.getByText('Matcha')).toBeInTheDocument()
    expect(screen.getByText('Espresso')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Incidents (IR)' })).toHaveTextContent('Same as Matcha: Haiku 5.5')
    expect(screen.getByRole('button', { name: 'Saved' })).toBeDisabled()
  })

  it('saves a per-product override and reports what the server stored', async () => {
    const stored = { ...MODELS, surfaces: { ...MODELS.surfaces, 'matcha.ir': 'default' } }
    vi.mocked(adminSettingsApi.setAgentModels).mockResolvedValue({ agent_models: stored, version: 'v2' })
    const { user, onSaved } = setup()

    await user.click(screen.getByRole('button', { name: 'Incidents (IR)' }))
    await user.click(screen.getByRole('button', { name: 'Built-in' }))
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(stored, 'v2'))
    // The loaded version goes back, so a stale page gets a 409 instead of overwriting.
    expect(adminSettingsApi.setAgentModels).toHaveBeenCalledWith({ ...stored, version: 'v1' })
  })

  it('offers Claude only while the server has a key, but keeps a stored choice visible', async () => {
    const { user } = setup(false)
    await user.click(screen.getByRole('button', { name: 'Espresso default' }))
    expect(screen.queryByRole('button', { name: 'Claude Sonnet 5.5' })).not.toBeInTheDocument()
    expect(screen.getByText(/ANTHROPIC_API_KEY/)).toBeInTheDocument()
    // Matcha's stored Haiku still shows rather than vanishing.
    expect(screen.getByRole('button', { name: 'Matcha default' })).toHaveTextContent('Claude Haiku 5.5')
  })

  it('shows a failed save instead of pretending it worked', async () => {
    vi.mocked(adminSettingsApi.setAgentModels).mockRejectedValue(new Error('Claude is not configured'))
    const { user, onSaved } = setup()
    await user.click(screen.getByRole('button', { name: 'Espresso default' }))
    await user.click(screen.getByRole('button', { name: 'Claude Sonnet 5.5' }))
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(screen.getByText('Claude is not configured')).toBeInTheDocument())
    expect(onSaved).not.toHaveBeenCalled()
  })
})
