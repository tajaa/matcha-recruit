import { useState } from 'preact/hooks'
import { tryConnect } from '../lib/api'

interface Props {
  onLogin: () => void
}

export function Login({ onLogin }: Props) {
  const [token, setToken] = useState('')
  const [error, setError] = useState('')
  const [connecting, setConnecting] = useState(false)

  const handleLogin = async () => {
    setError('')
    setConnecting(true)
    try {
      await tryConnect(token)
      onLogin()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Connection failed')
    }
    setConnecting(false)
  }

  return (
    <div class="login">
      <div class="login-card">
        <div class="login-icon">&#x2618;</div>
        <h1>matcha-agent</h1>
        <input
          type="password"
          placeholder="api secret"
          value={token}
          onInput={(e) => setToken((e.target as HTMLInputElement).value)}
          onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
          autoFocus
        />
        <button onClick={handleLogin} disabled={connecting}>
          {connecting ? 'connecting...' : 'connect'}
        </button>
        {error && <div class="login-error">{error}</div>}
        <div class="login-hint">leave blank if no secret is configured</div>
      </div>
    </div>
  )
}
