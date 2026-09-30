import { describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'
import MessageList from './MessageList'
import type { ChannelMessage } from '../../api/channels'

const message = (id: string, over: Partial<ChannelMessage>): ChannelMessage => ({
  id, channel_id: 'c1', sender_id: 'u1', sender_name: 'haley haley', sender_avatar_url: null,
  content: 'hello', created_at: '2026-09-30T23:00:00Z', edited_at: null, ...over,
})

function renderList(messages: ChannelMessage[]) {
  return render(
    <MessageList
      messages={messages}
      messagesContainerRef={{ current: null }}
      messagesEndRef={{ current: null }}
      userId="u1"
      canModerate={false}
      members={[]}
      onDelete={vi.fn()}
      onReply={vi.fn()}
      onRetry={vi.fn()}
      onLoadOlder={vi.fn()}
      hasMore={false}
      loadingOlder={false}
    />,
  )
}

describe('MessageList', () => {
  it("puts Espresso's messages on the other side and people's on the left", () => {
    const { container } = renderList([
      message('m1', { content: 'are you able to buy domains?' }),
      message('m2', { sender_id: 'bot', sender_name: 'Espresso', sender_is_agent: true, content: 'I can help find one.' }),
    ])
    const person = container.querySelector('#channel-message-m1') as HTMLElement
    const espresso = container.querySelector('#channel-message-m2') as HTMLElement
    expect(person.className).not.toContain('flex-row-reverse')
    expect(espresso.className).toContain('flex-row-reverse')
    expect(espresso.querySelector('.items-end')).not.toBeNull()
  })

  it('keeps a person who happens to be named Espresso on the left', () => {
    const { container } = renderList([message('m3', { sender_id: 'u2', sender_name: 'Espresso' })])
    expect((container.querySelector('#channel-message-m3') as HTMLElement).className).not.toContain('flex-row-reverse')
  })
})
