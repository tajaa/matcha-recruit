import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import AiConnectorsSettings from './AiConnectorsSettings'

const mock = vi.hoisted(() => ({ list: vi.fn(), disconnect: vi.fn() }))
vi.mock('../../api/matchaWork', () => ({ listConnectors: mock.list, disconnectConnector: mock.disconnect }))

const state = {
  mcp_url: 'https://matcha.test/api/mcp',
  grants: [{ client_id: 'c1', client_name: 'Codex', kind: 'codex', connected_at: null, last_used_at: null }],
  connected: { claude: false, chatgpt: false, claude_code: false, codex: true },
  claude_code_command: 'claude mcp add --transport http matcha https://matcha.test/api/mcp',
  codex_commands: ['codex mcp add matcha --url https://matcha.test/api/mcp', 'codex mcp login matcha'],
}

beforeEach(() => {
  vi.clearAllMocks()
  mock.list.mockResolvedValue(state)
  mock.disconnect.mockResolvedValue({ disconnected: true })
})

describe('AI connectors settings', () => {
  it('shows the connect steps and what is connected', async () => {
    render(<AiConnectorsSettings />)
    expect(await screen.findByText('codex mcp login matcha')).toBeTruthy()
    expect(screen.getByText('codex mcp add matcha --url https://matcha.test/api/mcp')).toBeTruthy()
    expect(screen.getByText(state.claude_code_command)).toBeTruthy()
    expect(screen.getAllByText('Connected')).toHaveLength(1)
  })

  it('disconnects a grant and reloads', async () => {
    render(<AiConnectorsSettings />)
    fireEvent.click(await screen.findByText('Disconnect'))
    await waitFor(() => expect(mock.disconnect).toHaveBeenCalledWith('c1'))
    await waitFor(() => expect(mock.list).toHaveBeenCalledTimes(2))
  })
})
