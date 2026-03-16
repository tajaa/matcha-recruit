import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ERTimelinePanel } from './ERTimelinePanel'

// Mock the api module
vi.mock('../../api/client', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

import { api } from '../../api/client'

const mockGet = vi.mocked(api.get)
const mockPost = vi.mocked(api.post)

const CASE_ID = 'fc421ec9-22db-408e-89ae-2faaf3855839'

const mockTimeline = {
  generated_at: '2026-03-15T10:00:00Z',
  analysis: {
    events: [
      {
        date: '2026-01-15',
        time: '14:00',
        description: 'Initial complaint filed',
        participants: ['Jane Doe'],
        confidence: 'high',
        evidence_quote: 'Employee reported harassment on Jan 15',
      },
    ],
    gaps_identified: ['Missing documentation for Feb 1-15'],
    timeline_summary: 'Complaint filed and investigated over 2 months.',
  },
}

describe('ERTimelinePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetches existing timeline exactly once on mount', async () => {
    mockGet.mockResolvedValue(mockTimeline)
    const onChange = vi.fn()

    render(
      <ERTimelinePanel caseId={CASE_ID} timeline={null} onTimelineChange={onChange} />,
    )

    // Should show loading state
    expect(screen.getByText('Analyzing timeline...')).toBeInTheDocument()

    // Wait for fetch to complete
    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(mockTimeline)
    })

    // api.get should have been called exactly once — not in a loop
    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(mockGet).toHaveBeenCalledWith(`/er/cases/${CASE_ID}/analysis/timeline`)
  })

  it('does not fetch if timeline is already provided', () => {
    const onChange = vi.fn()

    render(
      <ERTimelinePanel caseId={CASE_ID} timeline={mockTimeline} onTimelineChange={onChange} />,
    )

    // Should render the timeline directly, not fetch
    expect(mockGet).not.toHaveBeenCalled()
    expect(screen.getByText('Initial complaint filed')).toBeInTheDocument()
  })

  it('does not re-fetch on re-render', async () => {
    mockGet.mockResolvedValue({ generated_at: null })
    const onChange = vi.fn()

    const { rerender } = render(
      <ERTimelinePanel caseId={CASE_ID} timeline={null} onTimelineChange={onChange} />,
    )

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledTimes(1)
    })

    // Re-render with same props — should NOT trigger another fetch
    rerender(
      <ERTimelinePanel caseId={CASE_ID} timeline={null} onTimelineChange={onChange} />,
    )

    // Still just 1 call, not 2+
    expect(mockGet).toHaveBeenCalledTimes(1)
  })

  it('shows generate button when no existing timeline is found', async () => {
    mockGet.mockResolvedValue({ generated_at: null })
    const onChange = vi.fn()

    render(
      <ERTimelinePanel caseId={CASE_ID} timeline={null} onTimelineChange={onChange} />,
    )

    await waitFor(() => {
      expect(screen.getByText('Generate Timeline')).toBeInTheDocument()
    })
  })

  it('generates timeline when button is clicked', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValueOnce({ generated_at: null }) // initial fetch
    mockPost.mockResolvedValueOnce({}) // POST to generate
    mockGet.mockResolvedValueOnce(mockTimeline) // GET after generate
    const onChange = vi.fn()

    render(
      <ERTimelinePanel caseId={CASE_ID} timeline={null} onTimelineChange={onChange} />,
    )

    // Wait for generate button to appear
    await waitFor(() => {
      expect(screen.getByText('Generate Timeline')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Generate Timeline'))

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith(`/er/cases/${CASE_ID}/analysis/timeline`)
      expect(onChange).toHaveBeenCalledWith(mockTimeline)
    })
  })

  it('renders timeline events and gaps', () => {
    render(
      <ERTimelinePanel caseId={CASE_ID} timeline={mockTimeline} onTimelineChange={vi.fn()} />,
    )

    expect(screen.getByText('Complaint filed and investigated over 2 months.')).toBeInTheDocument()
    expect(screen.getByText('Initial complaint filed')).toBeInTheDocument()
    expect(screen.getByText('2026-01-15 14:00')).toBeInTheDocument()
    expect(screen.getByText('Participants: Jane Doe')).toBeInTheDocument()
    expect(screen.getByText('- Missing documentation for Feb 1-15')).toBeInTheDocument()
  })

  it('toggles evidence quotes on click', async () => {
    const user = userEvent.setup()

    render(
      <ERTimelinePanel caseId={CASE_ID} timeline={mockTimeline} onTimelineChange={vi.fn()} />,
    )

    // Evidence hidden by default
    expect(screen.queryByText(/Employee reported harassment/)).not.toBeInTheDocument()

    // Click "Show evidence"
    await user.click(screen.getByText('Show evidence'))
    expect(screen.getByText(/Employee reported harassment/)).toBeInTheDocument()

    // Click "Hide evidence"
    await user.click(screen.getByText('Hide evidence'))
    expect(screen.queryByText(/Employee reported harassment/)).not.toBeInTheDocument()
  })
})
