import type { HealthStatus } from '../lib/api'

interface Props {
  health: HealthStatus | null
  onLogout: () => void
}

export function Header({ health, onLogout }: Props) {
  const online = health?.status === 'ok'
  const features: string[] = []
  if (health?.gmail) features.push('gmail')
  if (health?.calendar) features.push('cal')
  if (health?.slack) features.push('slack')

  return (
    <header class="header">
      <div class="header-left">
        <div class="header-logo">&#x2618;</div>
        <span class="header-title">matcha-agent</span>
      </div>
      <div class="header-right">
        <div class="status">
          <span class={`status-dot ${online ? 'online' : 'offline'}`} />
          <span class="status-label">
            {online
              ? features.length
                ? `online · ${features.join(', ')}`
                : 'online'
              : 'offline'}
          </span>
        </div>
        <button class="btn-logout" onClick={onLogout}>
          logout
        </button>
      </div>
    </header>
  )
}
