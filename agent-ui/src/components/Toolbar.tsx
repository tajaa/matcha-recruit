interface Props {
  loading: boolean
  onEmails: () => void
  onBriefing: () => void
  onClear: () => void
  onSettings: () => void
}

export function Toolbar({ loading, onEmails, onBriefing, onClear, onSettings }: Props) {
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
      <button class="tool-btn" onClick={onSettings}>
        <span class="icon">&#9881;</span>
        <span>settings</span>
      </button>
      <button class="tool-btn" onClick={onClear}>
        <span class="icon">&#10005;</span>
        <span>clear</span>
      </button>
    </div>
  )
}
