import { useState, useRef } from 'preact/hooks'

interface Props {
  loading: boolean
  onSend: (message: string) => void
}

export function MessageInput({ loading, onSend }: Props) {
  const [value, setValue] = useState('')
  const ref = useRef<HTMLTextAreaElement>(null)

  const handleSend = () => {
    if (!value.trim() || loading) return
    onSend(value.trim())
    setValue('')
    if (ref.current) ref.current.style.height = 'auto'
  }

  const handleInput = (e: Event) => {
    const el = e.target as HTMLTextAreaElement
    setValue(el.value)
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 160) + 'px'
  }

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div class="input-area">
      <div class="input-row">
        <textarea
          ref={ref}
          value={value}
          onInput={handleInput}
          onKeyDown={handleKeyDown}
          placeholder="type a message..."
          rows={1}
        />
        <button
          class="send-btn"
          onClick={handleSend}
          disabled={loading || !value.trim()}
        >
          &#8593;
        </button>
      </div>
    </div>
  )
}
