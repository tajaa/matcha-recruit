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

  it('copies the connector URL as it opens ChatGPT', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    render(<AiConnectorsSettings />)
    const link = (await screen.findByText(/Copy URL & open ChatGPT/)).closest('a')!
    expect(link.getAttribute('href')).toBe('https://chatgpt.com/plugins')
    expect(link.getAttribute('target')).toBe('_blank')
    link.addEventListener('click', (e) => e.preventDefault()) // jsdom can't open tabs
    fireEvent.click(link)
    expect(writeText).toHaveBeenCalledWith(state.mcp_url)
    expect(await screen.findByText('URL copied')).toBeTruthy()
  })

  it('re-checks connections when the tab becomes visible again', async () => {
    render(<AiConnectorsSettings />)
    await screen.findByText('codex mcp login matcha')
    expect(mock.list).toHaveBeenCalledTimes(1)
    document.dispatchEvent(new Event('visibilitychange'))
    await waitFor(() => expect(mock.list).toHaveBeenCalledTimes(2))
  })

  it('points Mac users at Espresso and no one else', async () => {
    const ua = vi.spyOn(navigator, 'userAgent', 'get')
    ua.mockReturnValue('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)')
    const { unmount } = render(<AiConnectorsSettings />)
    expect(await screen.findByText(/Espresso app signs in to ChatGPT/)).toBeTruthy()
    unmount()
    ua.mockReturnValue('Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
    render(<AiConnectorsSettings />)
    await screen.findByText('codex mcp login matcha')
    expect(screen.queryByText(/Espresso app signs in to ChatGPT/)).toBeNull()
    ua.mockRestore()
  })
})
