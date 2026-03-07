interface Props {
  loading: boolean
  onEmails: () => void
  onBriefing: () => void
  onClear: () => void
}

export function Toolbar({ loading, onEmails, onBriefing, onClear }: Props) {
  return (
    <div class="toolbar">
      <button
        class={`tool-btn ${loading ? 'loading' : ''}`}
        onClick={onEmails}
        disabled={loading}
      >
        <span class="icon">&#9993;</span>
        <span>emails</span>
      </button>
      <button
        class={`tool-btn ${loading ? 'loading' : ''}`}
        onClick={onBriefing}
        disabled={loading}
      >
        <span class="icon">&#9783;</span>
        <span>briefing</span>
      </button>
      <div class="toolbar-sep" />
      <button class="tool-btn" onClick={onClear}>
        <span class="icon">&#10005;</span>
        <span>clear</span>
      </button>
    </div>
  )
}
