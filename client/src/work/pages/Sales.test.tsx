import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Sales from './Sales'
import type { SalesCampaignDetail } from '../api/matchaWork/sales'
import { campaign, prospect } from './Sales/testFixtures'
import { WorkSurfaceProvider } from '../routes/WorkSurfaceContext'

const api = vi.hoisted(() => ({
  listSalesWorkspaces: vi.fn(),
  getPlaybookOptions: vi.fn(),
  listCampaigns: vi.fn(),
  createCampaign: vi.fn(),
  getCampaign: vi.fn(),
  getCampaignStatus: vi.fn(),
  updateCampaign: vi.fn(),
  deleteCampaign: vi.fn(),
  importProspects: vi.fn(),
  updateProspect: vi.fn(),
  deleteProspect: vi.fn(),
  optOutProspect: vi.fn(),
  resolveUnknown: vi.fn(),
  sendBatch: vi.fn(),
  campaignAction: vi.fn(),
}))
vi.mock('../api/matchaWork/sales', () => api)
const agent = vi.hoisted(() => ({ agentEmailStatus: vi.fn() }))
vi.mock('../api/matchaWork/agent', () => agent)

const HOUSE = {
  title: 'Matcha consulting', target: 'US employers', offer: 'Four services', playbook: 'consulting',
  cta_url: 'https://hey-matcha.com/services?book=1',
}

function detail(over: Partial<SalesCampaignDetail> = {}): SalesCampaignDetail {
  return {
    campaign: campaign({ playbook: 'consulting', cta_url: HOUSE.cta_url }),
    prospects: [
      prospect({ id: 'weak', name: 'Bo Lee', company: 'Lee Cafe', fit: 1, review_token: 'tw' }),
      prospect({
        id: 'strong', fit: 3, segment: 'growing', service: 'hr', review_token: 'ts',
        signal: 'Hiring their first HR Generalist (Greenhouse, Oct 2026)',
        research: 'Acme Dental runs 4 clinics.', sources: ['https://boards.greenhouse.io/acme/jobs/1'],
        review_flags: ['Include no link but the booking link.'],
      }),
    ],
    counts: { draft: 2 },
    offset: 0,
    ...over,
  }
}

function Where() {
  const l = useLocation()
  return <span data-testid="where">{l.pathname + l.search}</span>
}

function renderAt(path: string) {
  return render(
    <WorkSurfaceProvider value="espresso">
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/espresso/sales" element={<><Sales /><Where /></>} />
          <Route path="/espresso/assistant" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </WorkSurfaceProvider>,
  )
}

beforeEach(() => {
  api.listSalesWorkspaces.mockResolvedValue({ workspaces: [{ id: 'w1', title: 'Outreach' }] })
  api.getPlaybookOptions.mockResolvedValue({ playbooks: [], house: HOUSE })
  api.listCampaigns.mockResolvedValue({ campaigns: [campaign({ playbook: 'consulting' })], workspace_campaigns: [] })
  api.getCampaign.mockResolvedValue(detail())
  agent.agentEmailStatus.mockResolvedValue({ connected: true, email: 'diego@example.com', snapshot_max_emails: 0 })
})

afterEach(() => vi.useRealTimers())

describe('Sales', () => {
  it('opens the only workspace and lists its campaigns', async () => {
    renderAt('/espresso/sales')
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('workspace=w1'))
    expect(await screen.findByRole('button', { name: /Clinics/ })).toBeInTheDocument()
    expect(api.listCampaigns).toHaveBeenCalledWith('w1')
  })

  it('starts Matcha’s consulting campaign from the house offer', async () => {
    api.createCampaign.mockResolvedValue(campaign({ id: 'new' }))
    renderAt('/espresso/sales?workspace=w1')
    fireEvent.click(await screen.findByRole('button', { name: 'New campaign' }))
    fireEvent.click(screen.getByRole('checkbox', { name: /Start from Matcha's consulting offer/ }))
    expect(screen.getByLabelText('Name')).toHaveValue('Matcha consulting')
    fireEvent.change(screen.getByLabelText('Who to reach'), { target: { value: 'Clinics in Texas' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create campaign' }))
    await waitFor(() => expect(api.createCampaign).toHaveBeenCalledWith('w1', expect.objectContaining({
      title: 'Matcha consulting', target: 'Clinics in Texas', playbook: 'consulting', house: true,
    })))
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('campaign=new'))
  })

  it('shows the best fit first, with why now and what to check', async () => {
    renderAt('/espresso/sales?workspace=w1&campaign=c1')
    const list = await screen.findAllByRole('listitem')
    expect(within(list[0]).getByText(/Strong fit · Growing, no HR lead · Hiring their first HR Generalist/)).toBeInTheDocument()
    expect(within(list[0]).getByText('1 thing to check')).toBeInTheDocument()
    fireEvent.click(within(list[0]).getByRole('button'))
    const pane = await screen.findByRole('region', { name: 'Prospect Ana Ruiz' })
    expect(within(pane).getByText('Why now')).toBeInTheDocument()
    expect(within(pane).getByText('Strong fit · Growing, no HR lead · HR consulting')).toBeInTheDocument()
    expect(within(pane).getByText('• Include no link but the booking link.')).toBeInTheDocument()
    expect(within(pane).getByRole('link', { name: 'https://boards.greenhouse.io/acme/jobs/1' })).toBeInTheDocument()
  })

  it('saves an edited draft against the version that was opened', async () => {
    api.updateProspect.mockResolvedValue(prospect())
    renderAt('/espresso/sales?workspace=w1&campaign=c1&prospect=strong')
    const pane = await screen.findByRole('region', { name: 'Prospect Ana Ruiz' })
    fireEvent.change(within(pane).getByLabelText('Message'), { target: { value: 'New words' } })
    fireEvent.click(within(pane).getByRole('button', { name: 'Save draft' }))
    await waitFor(() => expect(api.updateProspect).toHaveBeenCalledWith('c1', 'strong', { review_token: 'ts', body: 'New words' }))
  })

  it('reviews a batch exactly as it goes out, then sends it from the person’s Gmail', async () => {
    api.sendBatch.mockResolvedValue({ status: 'sending' })
    renderAt('/espresso/sales?workspace=w1&campaign=c1')
    fireEvent.click(await screen.findByRole('button', { name: 'Select 2' }))
    fireEvent.click(screen.getByRole('button', { name: 'Review and send 2' }))
    const dialog = await screen.findByRole('dialog', { name: 'Review and send' })
    expect(await within(dialog).findByText('diego@example.com')).toBeInTheDocument()
    // Body then footer, as composed on the server.
    expect(within(dialog).getAllByText(/Hello\s+Reply stop\.\s+Acme, 1 Main St/)).toHaveLength(2)
    expect(within(dialog).getByText(/1 message has something to check/)).toBeInTheDocument()
    const send = within(dialog).getByRole('button', { name: 'Send 2' })
    expect(send).toBeDisabled()
    fireEvent.click(within(dialog).getByRole('checkbox', { name: "I've read every message above" }))
    fireEvent.click(send)
    await waitFor(() => expect(api.sendBatch).toHaveBeenCalledTimes(1))
    const [id, sender, drafts, requestId] = api.sendBatch.mock.calls[0]
    expect([id, sender]).toEqual(['c1', 'diego@example.com'])
    expect(drafts).toEqual([{ id: 'strong', review_token: 'ts' }, { id: 'weak', review_token: 'tw' }])
    expect(requestId).toMatch(/[0-9a-f-]{36}/)
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('won’t send without Gmail or a footer', async () => {
    agent.agentEmailStatus.mockResolvedValue({ connected: false, email: null, snapshot_max_emails: 0 })
    api.getCampaign.mockResolvedValue(detail({ campaign: campaign({ footer: '' }) }))
    renderAt('/espresso/sales?workspace=w1&campaign=c1')
    fireEvent.click(await screen.findByRole('button', { name: 'Select 2' }))
    fireEvent.click(screen.getByRole('button', { name: 'Review and send 2' }))
    const dialog = await screen.findByRole('dialog', { name: 'Review and send' })
    expect(await within(dialog).findByText(/Connect Gmail to send/)).toBeInTheDocument()
    expect(within(dialog).getByText(/Add a footer/)).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('checkbox'))
    expect(within(dialog).getByRole('button', { name: 'Send 2' })).toBeDisabled()
  })

  it('imports a pasted list and says what it skipped', async () => {
    api.importProspects.mockResolvedValue({ added: 1, duplicates: 1, suppressed: 1 })
    renderAt('/espresso/sales?workspace=w1&campaign=c1')
    fireEvent.click(await screen.findByRole('button', { name: 'Import' }))
    fireEvent.change(screen.getByLabelText('Contacts to import'), { target: { value: 'a@example.com\nb@example.com\nc@example.com' } })
    fireEvent.click(screen.getByRole('button', { name: 'Import contacts' }))
    expect(await screen.findByText('Added 1. Skipped 1 already in the campaign, 1 asked not to be contacted.')).toBeInTheDocument()
    expect(api.importProspects.mock.calls[0][1]).toHaveLength(3)
  })

  it('hands the campaign to Espresso to research and draft', async () => {
    renderAt('/espresso/sales?workspace=w1&campaign=c1')
    fireEvent.click(await screen.findByRole('button', { name: /Research and draft with Espresso/ }))
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/espresso/assistant'))
  })

  it('polls while sending and reloads only when a message moved', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const sending = detail({ campaign: campaign({ status: 'sending' }), counts: { approved: 2 } })
    api.getCampaign.mockResolvedValue(sending)
    api.getCampaignStatus.mockResolvedValue({
      campaign: sending.campaign, counts: sending.counts,
      prospects: sending.prospects.map((p) => ({ id: p.id, status: p.status, error: null, review_token: p.review_token })),
    })
    renderAt('/espresso/sales?workspace=w1&campaign=c1')
    expect(await screen.findByText('Sending')).toBeInTheDocument()
    await act(async () => { await vi.advanceTimersByTimeAsync(15_000) })
    expect(api.getCampaignStatus).toHaveBeenCalledTimes(1)
    expect(api.getCampaign).toHaveBeenCalledTimes(1)
    api.getCampaignStatus.mockResolvedValue({
      campaign: sending.campaign, counts: { sent: 1 },
      prospects: [{ id: 'strong', status: 'sent', error: null, review_token: 'ts' }],
    })
    await act(async () => { await vi.advanceTimersByTimeAsync(15_000) })
    await waitFor(() => expect(api.getCampaign).toHaveBeenCalledTimes(2))
  })
})
