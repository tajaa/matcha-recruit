import { describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import AgentCardMessage from './AgentCardMessage'
import { isAgentCardMessage, isAssistantPrompt, splitTicketToken } from './agentCardMessageHelpers'
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

describe('Espresso assistant messages', () => {
  it('shows a run working, then done, with its latest steps', () => {
    const steps = Array.from({ length: 6 }, (_, i) => ({
      seq: i + 1, kind: 'fetch', label: `Read page ${i + 1}`, status: i === 5 ? 'error' : 'ok',
    }))
    const { rerender } = render(<AgentCardMessage metadata={{ kind: 'agent_progress', run_id: 'r1' }} content="On it." />)
    expect(screen.getByText('Starting…')).toBeTruthy()
    rerender(
      <AgentCardMessage
        metadata={{ kind: 'agent_progress', run_id: 'r1', progress: { run_id: 'r1', status: 'running', note: 'Reading shop.example…', steps } }}
        content="On it."
      />,
    )
    expect(screen.getByText('Reading shop.example…')).toBeTruthy()
    // Only the latest few are shown until asked for.
    expect(screen.queryByText('Read page 1')).toBeNull()
    expect(screen.getByText('Read page 6')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Show all 6 steps' }))
    expect(screen.getByText('Read page 1')).toBeTruthy()
    rerender(
      <AgentCardMessage
        metadata={{ kind: 'agent_progress', run_id: 'r1', progress: { run_id: 'r1', status: 'failed', note: 'It took too long.', steps: [] } }}
        content="On it."
      />,
    )
    expect(screen.getByText('It took too long.')).toBeTruthy()
    rerender(
      <AgentCardMessage
        metadata={{ kind: 'agent_progress', run_id: 'r1', progress: { run_id: 'r1', status: 'done', steps: [] } }}
        content="On it."
      />,
    )
    expect(screen.getByText('Done')).toBeTruthy()
  })

  it('renders an answer block by block and skips a block it does not know', () => {
    const meta: AgentChatMetadata = {
      kind: 'agent_result',
      run_id: 'r1',
      result_v2: {
        schema: 'agent_result.v2',
        headline: 'Two things need you today',
        summary: 'A lease renewal and a design review.',
        caveats: ['I only looked at the last 7 days.'],
        blocks: [
          { type: 'emails', items: [{ message_id: 'm1', from: 'Dana <dana@example.org>', subject: 'Lease renewal', snippet: 'Please confirm' }] },
          { type: 'events', items: [{ event_id: 'e1', title: 'Design review', start: '2026-10-02', location: 'Room 2', attendee_count: 3 }] },
          {
            type: 'sections',
            sections: [{ heading: 'Why', body_md: 'See [the page](https://a.example/x), not [this](javascript:alert(1)). ![x](https://a.example/i.png)' }],
          },
          { type: 'sources', sources: [{ title: 'A', url: 'https://a.example/x' }, { title: 'Bad', url: 'javascript:alert(1)' }] },
          { type: 'picks', top_pick: { name: 'Standing desk', price_text: '$449', buy_url: 'https://shop.example/desk', retailer: 'Shop' }, alternatives: [] },
          { type: 'hologram' },
        ],
      },
    }
    render(<AgentCardMessage metadata={meta} content="" />)
    expect(screen.getByText('Two things need you today')).toBeTruthy()
    expect(screen.getByText('Lease renewal')).toBeTruthy()
    expect(screen.getByText('Dana <dana@example.org>')).toBeTruthy()
    expect(screen.getByText('Design review')).toBeTruthy()
    expect(screen.getByText('2026-10-02')).toBeTruthy()  // an all-day date is not shifted by the timezone
    expect(screen.getByText('Room 2 · 3 invited')).toBeTruthy()
    expect(screen.getByText('Standing desk')).toBeTruthy()
    expect(screen.getByText('I only looked at the last 7 days.')).toBeTruthy()
    const links = screen.getAllByRole('link').map((link) => link.getAttribute('href'))
    expect(links).toEqual(['https://a.example/x', 'https://a.example/x', 'https://shop.example/desk'])
    expect(screen.queryByRole('img')).toBeNull()
    expect(screen.queryByText(/hologram/)).toBeNull()
  })

  it('says what became of a booking and links to finish one that needs payment', () => {
    const block = (status: string, extra = {}) => ({
      kind: 'agent_result' as const,
      run_id: 'r1',
      result_v2: {
        schema: 'agent_result.v2' as const, headline: 'Nopa', summary: 'Friday at 7.',
        blocks: [{ type: 'reservation' as const, venue: 'Nopa', when: '2026-10-02 19:00', party_size: 4, status, ...extra }],
      },
    })
    const { rerender } = render(
      <AgentCardMessage metadata={block('booked', { confirmation: 'AB-1234' }) as AgentChatMetadata} content="" />,
    )
    expect(screen.getByText('Booked')).toBeTruthy()
    expect(screen.getByText('Confirmation AB-1234')).toBeTruthy()
    expect(screen.getByText('2026-10-02 19:00 · party of 4')).toBeTruthy()
    rerender(
      <AgentCardMessage
        metadata={block('handoff', { handoff_url: 'https://www.tables.example/checkout' }) as AgentChatMetadata}
        content=""
      />,
    )
    expect(screen.getByText('Needs payment details: finish it yourself')).toBeTruthy()
    const finish = screen.getByRole('link', { name: /Finish booking at tables.example/ })
    expect(finish.getAttribute('href')).toBe('https://www.tables.example/checkout')
    expect(finish.getAttribute('rel')).toBe('noopener noreferrer nofollow')
    rerender(<AgentCardMessage metadata={block('unverified') as AgentChatMetadata} content="" />)
    expect(screen.getByText('Submitted, not confirmed by the site')).toBeTruthy()
  })

  it('points at Settings when buying needs a card or an address first', () => {
    const metadata = {
      kind: 'agent_result' as const,
      run_id: 'r1',
      result_v2: {
        schema: 'agent_result.v2' as const, headline: 'Add a card first', summary: 'Then I can buy it.',
        blocks: [{
          type: 'purchase_setup' as const,
          missing: ['payment_card', 'shipping_address'],
          steps: [
            { key: 'payment_card', label: 'Add a payment card', where: 'Settings → Payment cards', detail: 'Stored encrypted.' },
            { key: 'shipping_address', label: 'Add a shipping address', where: 'Settings → Shipping addresses' },
          ],
        }],
      },
    } as AgentChatMetadata
    render(<AgentCardMessage metadata={metadata} content="" />)
    expect(screen.getByText('Before I can buy it')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Add a payment card' }).getAttribute('href')).toBe('/work/settings#payment-cards')
    expect(screen.getByRole('link', { name: 'Add a shipping address' }).getAttribute('href'))
      .toBe('/work/settings#shipping-addresses')
    expect(screen.getByText(/Never paste a card number in chat/)).toBeTruthy()
  })

  it('shows a receipt for what was done, and says when it was only a dry run', () => {
    const receipt = (status: string, extra = {}): AgentChatMetadata => ({
      kind: 'agent_receipt',
      run_id: 'r1',
      action_receipt: {
        action: 'send_email', title: 'Send an email', status: status as 'done',
        lines: [{ label: 'To', value: 'dana@example.org' }, { label: 'Subject', value: 'Re: Lease renewal' }],
        ...extra,
      },
    })
    const { rerender } = render(<AgentCardMessage metadata={receipt('done')} content="" />)
    expect(screen.getByText('Send an email')).toBeTruthy()
    expect(screen.getByText('DONE')).toBeTruthy()
    expect(screen.getByText('dana@example.org')).toBeTruthy()
    rerender(<AgentCardMessage metadata={receipt('dry_run', { note: 'Dry run: nothing was sent.' })} content="" />)
    expect(screen.getByText('DRY RUN')).toBeTruthy()
    expect(screen.getByText('Dry run: nothing was sent.')).toBeTruthy()
    rerender(<AgentCardMessage metadata={receipt('unknown')} content="" />)
    expect(screen.getByText('OUTCOME UNKNOWN')).toBeTruthy()
    rerender(
      <AgentCardMessage
        metadata={receipt('handoff', { link: { label: 'Finish booking', url: 'javascript:alert(1)' } })}
        content=""
      />,
    )
    expect(screen.getByText('OVER TO YOU')).toBeTruthy()
    expect(screen.queryByRole('link')).toBeNull()
    rerender(
      <AgentCardMessage
        metadata={receipt('failed', { link: { label: 'Open in Calendar', url: 'https://calendar.example/e' } })}
        content=""
      />,
    )
    expect(screen.getByRole('link', { name: /Open in Calendar/ }).getAttribute('href')).toBe('https://calendar.example/e')
  })

  const confirmation: AgentChatMetadata = {
    kind: 'agent_card_prompt',
    prompt_kind: 'confirm_action',
    prompt_id: 'p9',
    run_id: 'r1',
    owner_user_id: 'u1',
    view: {
      question: "Send an email? You didn't mention eve@attacker.test, so I'm checking first.",
      action: { title: 'Send an email', lines: [{ label: 'To', value: 'eve@attacker.test' }, { label: 'Message', value: 'as asked' }] },
      buttons: [
        { label: 'Yes, go ahead', reply: 'yes', style: 'primary' },
        { label: 'No, cancel', reply: 'no', style: 'secondary' },
      ],
    },
  }

  it('shows exactly what a yes will carry out, to the person who was asked', () => {
    const onQuickReply = vi.fn(() => true)
    const asked = render(
      <AgentCardMessage metadata={confirmation} content="" userId="u1" onQuickReply={onQuickReply} />,
    )
    expect(screen.getByText('eve@attacker.test')).toBeTruthy()
    expect(screen.getByText('as asked')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Yes, go ahead' }))
    expect(onQuickReply).toHaveBeenCalledWith('yes')
    asked.unmount()
    // Someone else looking at the same card (their own copy of it, not this one re-rendered).
    const { rerender } = render(
      <AgentCardMessage metadata={confirmation} content="" userId="someone-else" onQuickReply={onQuickReply} />,
    )
    expect(screen.queryByRole('button', { name: 'Yes, go ahead' })).toBeNull()
    expect(screen.getByText('Waiting for the person who asked.')).toBeTruthy()
    rerender(
      <AgentCardMessage
        metadata={{ ...confirmation, prompt_status: 'superseded' }} content="" userId="u1" onQuickReply={onQuickReply}
      />,
    )
    expect(screen.getByText('You moved on to something else')).toBeTruthy()
    rerender(
      <AgentCardMessage
        metadata={{ ...confirmation, prompt_status: 'answered', answer_text: 'Went ahead' }} content="" userId="u1"
      />,
    )
    expect(screen.getByText('Went ahead')).toBeTruthy()
  })

  it('an open question with no suggested answers is answered by typing', () => {
    const meta: AgentChatMetadata = {
      kind: 'agent_card_prompt', prompt_kind: 'ask_user', prompt_id: 'p3', owner_user_id: 'u1',
      view: { question: 'Which day?', buttons: [] },
    }
    render(<AgentCardMessage metadata={meta} content="" userId="u1" onQuickReply={() => true} />)
    expect(screen.getByText('Which day?')).toBeTruthy()
    expect(screen.getByText('Reply to answer.')).toBeTruthy()
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('recognises assistant payloads', () => {
    expect(isAgentCardMessage({ kind: 'agent_progress', run_id: 'r1' })).toBe(true)
    expect(isAgentCardMessage({ kind: 'agent_progress' })).toBe(false)
    expect(isAgentCardMessage({ kind: 'agent_result' })).toBe(false)
    expect(isAgentCardMessage({ kind: 'agent_receipt', action_receipt: { title: 'x', status: 'done', lines: [] } })).toBe(true)
    expect(isAssistantPrompt({ prompt_kind: 'confirm_action' })).toBe(true)
    expect(isAssistantPrompt({ prompt_kind: 'ask_user' })).toBe(true)
    expect(isAssistantPrompt({ prompt_kind: 'purchase' })).toBe(false)
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
