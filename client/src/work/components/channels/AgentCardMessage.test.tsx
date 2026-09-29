import { describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import AgentCardMessage from './AgentCardMessage'
import { isAgentCardMessage, splitTicketToken } from './agentCardMessageHelpers'
import type { AgentChatMetadata } from '../../types'

const result: AgentChatMetadata = {
  kind: 'agent_card_result',
  task_id: 't1',
  result: {
    headline: 'Best pick: Anker braided cable',
    summary: 'Strongest match for the request.',
    top_pick: {
      name: 'Anker 6 ft USB-C cable',
      brand: 'Anker',
      image_url: 'https://cdn.example.com/a.webp',
      price_text: '$19.99',
      buy_url: 'https://www.anker.com/products/a82e2?variant=1',
      retailer: 'Anker store',
      rating: { value: 4.9, scale: 5, count: 298 },
      why: ['240W charging', 'USB-IF certified'],
    },
    alternatives: [
      { name: 'UGREEN 2 pack', price_text: '$16.99', image_url: 'http://insecure.example.com/x.jpg', buy_url: 'javascript:alert(1)' },
    ],
    source_count: 7,
  },
}

describe('AgentCardMessage', () => {
  it('renders the result as a card: photo, price, rating, reasons, hardened store link', () => {
    render(<AgentCardMessage metadata={result} content="" />)
    expect(screen.getByText('Best pick: Anker braided cable')).toBeTruthy()
    expect(screen.getByText('$19.99')).toBeTruthy()
    expect(screen.getByText('4.9')).toBeTruthy()
    expect(screen.getByText('240W charging')).toBeTruthy()
    const buy = screen.getByRole('link', { name: /View at Anker store/ })
    expect(buy.getAttribute('href')).toBe('https://www.anker.com/products/a82e2?variant=1')
    expect(buy.getAttribute('rel')).toBe('noopener noreferrer nofollow')
    expect(buy.getAttribute('target')).toBe('_blank')
    const images = screen.getAllByRole('img')
    expect(images.map((i) => i.getAttribute('src'))).toEqual(['https://cdn.example.com/a.webp'])  // https only
    // The alternative's javascript: link never renders.
    expect(screen.getAllByRole('link')).toHaveLength(1)
    expect(screen.getByText(/7 sources/)).toBeTruthy()
  })

  const buyQuestion: AgentChatMetadata = {
    kind: 'agent_card_prompt',
    prompt_kind: 'purchase',
    prompt_id: 'p1',
    owner_user_id: 'u1',
    view: {
      question: 'Want me to buy it?',
      offer: { item_name: 'Anker 6 ft USB-C cable', retailer: 'Anker store', price_text: '$19.99' },
      buttons: [
        { label: 'Buy it', reply: 'Buy it', style: 'primary' },
        { label: 'No thanks', reply: 'No thanks', style: 'secondary' },
      ],
    },
  }

  it('a pressed button shows it is sending until the server closes the question', () => {
    const onQuickReply = vi.fn(() => true)
    const { rerender } = render(
      <AgentCardMessage metadata={buyQuestion} content="Want me to buy it? Reply yes" userId="u1" onQuickReply={onQuickReply} />,
    )
    expect(screen.getByText('Want me to buy it?')).toBeTruthy()
    fireEvent.click(screen.getByText('Buy it'))
    expect(onQuickReply).toHaveBeenCalledWith('Buy it')
    expect(screen.queryByText('No thanks')).toBeNull()
    expect(screen.getByText('Sending “Buy it”…')).toBeTruthy()
    // The socket's agent_card_prompt_updated event stamps the message.
    rerender(
      <AgentCardMessage
        metadata={{ ...buyQuestion, prompt_status: 'answered', answer: 'yes', answer_text: 'Going ahead with the purchase' }}
        content="" userId="u1" onQuickReply={onQuickReply}
      />,
    )
    expect(screen.getByText('Going ahead with the purchase')).toBeTruthy()
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('buttons come back if the question stays open (e.g. no saved card yet)', () => {
    vi.useFakeTimers()
    try {
      render(<AgentCardMessage metadata={buyQuestion} content="" userId="u1" onQuickReply={() => true} />)
      fireEvent.click(screen.getByText('Buy it'))
      expect(screen.queryByText('Buy it')).toBeNull()
      act(() => { vi.advanceTimersByTime(8000) })
      expect(screen.getByText('Buy it')).toBeTruthy()
    } finally {
      vi.useRealTimers()
    }
  })

  it('an offline press keeps the buttons and says so', () => {
    render(<AgentCardMessage metadata={buyQuestion} content="" userId="u1" onQuickReply={() => false} />)
    fireEvent.click(screen.getByText('Buy it'))
    expect(screen.getByText('Buy it')).toBeTruthy()
    expect(screen.getByText(/Couldn't send: you're offline/)).toBeTruthy()
    expect(screen.queryByText(/Sending/)).toBeNull()
  })

  it("someone else's buy question shows no buttons", () => {
    render(<AgentCardMessage metadata={buyQuestion} content="" userId="u2" onQuickReply={() => true} />)
    expect(screen.queryByRole('button')).toBeNull()
    expect(screen.getByText('Waiting for the buyer to answer.')).toBeTruthy()
  })

  it('a question past its expiry shows as expired without a reload', () => {
    const meta = { ...buyQuestion, expires_at: '2020-01-01T00:00:00+00:00' }
    render(<AgentCardMessage metadata={meta} content="" userId="u1" onQuickReply={() => true} />)
    expect(screen.queryByRole('button')).toBeNull()
    expect(screen.getByText('This question expired')).toBeTruthy()
  })

  it('an answered question from history shows its answer and no buttons', () => {
    const meta: AgentChatMetadata = {
      kind: 'agent_card_prompt',
      prompt_kind: 'show_result',
      prompt_status: 'answered',
      answer: 'yes',
      answer_text: 'Showed the result',
      view: { question: 'I finished it. Want to see what I found?', buttons: [{ label: 'Show me', reply: 'Show me', style: 'primary' }] },
    }
    render(<AgentCardMessage metadata={meta} content={'I finished "Balm". Want to see what I found? Reply yes or no.'} />)
    expect(screen.getByText('I finished it. Want to see what I found?')).toBeTruthy()
    expect(screen.queryByRole('button')).toBeNull()
    expect(screen.getByText('Showed the result')).toBeTruthy()
  })

  it('the heading is the server question, never cut from the user-titled content', () => {
    const meta: AgentChatMetadata = {
      kind: 'agent_card_prompt',
      prompt_kind: 'show_result',
      view: { question: 'I finished it. Want to see what I found?', buttons: [] },
    }
    render(<AgentCardMessage metadata={meta} content={'I finished "Find a Reply-All blocker". Want to see what I found? Reply yes or no.'} />)
    expect(screen.getByText('I finished it. Want to see what I found?')).toBeTruthy()
  })

  it('renders a flight result as flight rows, labelled when fares are sandbox data', () => {
    const meta: AgentChatMetadata = {
      kind: 'agent_card_result',
      result: {
        headline: 'Cheapest: two one-ways', summary: 'Saves $110.', top_pick: null, alternatives: [],
        flights: {
          test_data: true,
          options: [{
            label: 'Cheapest', price_text: '$310.00', total_with_bags_text: '$380.00', carriers: ['Delta'],
            ticketing: 'separate', warning: 'Two separate tickets',
            slices: [{ origin: 'SFO', destination: 'JFK', departing_at: '2026-11-12T22:05:00',
              arriving_at: '2026-11-13T06:40:00', stops: 0, duration_minutes: 335, flight_numbers: ['DL 300'] }],
          }],
        },
      },
    }
    render(<AgentCardMessage metadata={meta} content="" />)
    expect(screen.getByText(/TEST DATA/)).toBeTruthy()
    expect(screen.getByText('$380.00')).toBeTruthy()
    expect(screen.getByText('with bags')).toBeTruthy()
    expect(screen.getByText(/2 tickets/)).toBeTruthy()
    expect(screen.getByText('+1')).toBeTruthy()
    expect(screen.getByText(/Two separate tickets/)).toBeTruthy()
    expect(screen.getByText(/no location, device, cookies or history sent/)).toBeTruthy()
  })

  it('renders the receipt with test-mode labelling', () => {
    const meta: AgentChatMetadata = {
      kind: 'agent_card_receipt',
      receipt: {
        status: 'paid_test', item_name: 'Classic Clean Shampoo', brand: 'California Naturals',
        total_text: '$11.99', card_text: 'Visa ending 4242 (stripe test)', payment_intent_id: 'pi_123',
        order_ref: '272B90C9', date: '2026-09-29T08:13:00+00:00', product_url: 'https://thecalifornianaturals.com/p',
      },
    }
    render(<AgentCardMessage metadata={meta} content="" />)
    expect(screen.getByText('Purchase complete')).toBeTruthy()
    expect(screen.getByText('TEST MODE')).toBeTruthy()
    expect(screen.getByText('$11.99')).toBeTruthy()
    expect(screen.getByText('pi_123')).toBeTruthy()
    expect(screen.getByRole('link', { name: /View product/ }).getAttribute('href')).toBe('https://thecalifornianaturals.com/p')
  })
})

describe('agent card helpers', () => {
  it('recognises only complete agent-card payloads', () => {
    expect(isAgentCardMessage(result)).toBe(true)
    expect(isAgentCardMessage({ kind: 'agent_card_result' })).toBe(false)
    expect(isAgentCardMessage({ action: { kind: 'event_draft' } })).toBe(false)
    expect(isAgentCardMessage(undefined)).toBe(false)
  })

  it('splits the ticket marker from the body', () => {
    expect(splitTicketToken('⟦ticket:abc|Find a balm|Review⟧\nHello')).toEqual({ title: 'Find a balm', body: 'Hello' })
    expect(splitTicketToken('plain text')).toEqual({ title: null, body: 'plain text' })
  })
})
