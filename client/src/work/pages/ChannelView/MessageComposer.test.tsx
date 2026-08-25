import { render, screen } from '@testing-library/react'
import { createRef } from 'react'
import { describe, expect, it, vi } from 'vitest'
import MessageComposer from './MessageComposer'

describe('MessageComposer', () => {
  it('uses the workspace text token for typed text and the caret', () => {
    render(
      <MessageComposer
        pendingFiles={[]}
        setPendingFiles={vi.fn()}
        fileInputRef={createRef<HTMLInputElement>()}
        mentionQuery={null}
        mentionMatches={[]}
        applyMention={vi.fn()}
        inputTextareaRef={createRef<HTMLTextAreaElement>()}
        input=""
        onInputChange={vi.fn()}
        onKeyDown={vi.fn()}
        channelName="operations"
        onSend={vi.fn()}
        uploading={false}
        replyTo={null}
        onClearReply={vi.fn()}
      />,
    )

    expect(screen.getByPlaceholderText('Message #operations...')).toHaveClass('text-w-text', 'caret-w-text')
  })
})
