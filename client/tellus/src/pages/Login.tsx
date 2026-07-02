import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { tellusPublicPost } from '../api/tellusClient'
import { useAccount } from '../hooks/useAccount'
import { Button, Card, ErrorText, Input } from '../components/ui'
import type { TokenResponse } from '../api/types'
import { AuthShell } from './AuthShell'

export default function Login() {
  const { setSession } = useAccount()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const [needsConfirm, setNeedsConfirm] = useState(false)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setErr(''); setNeedsConfirm(false); setBusy(true)
    try {
      const res = await tellusPublicPost<TokenResponse>('/auth/login', { email, password })
      setSession(res)
      navigate('/')
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Login failed'
      setErr(msg)
      if (msg.toLowerCase().includes('confirm your email')) setNeedsConfirm(true)
    } finally {
      setBusy(false)
    }
  }

  async function resend() {
    try { await tellusPublicPost('/auth/resend-verification', { email }); setErr('Confirmation email sent — check your inbox.') } catch { /* ignore */ }
  }

  return (
    <AuthShell title="Welcome back" subtitle="Sign in to give feedback and claim rewards.">
      <Card>
        <form onSubmit={submit} className="space-y-4">
          <Input label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          <Input label="Password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          <ErrorText>{err}</ErrorText>
          {needsConfirm && (
            <button type="button" onClick={resend} className="text-xs text-tu-accent hover:underline">
              Resend confirmation email
            </button>
          )}
          <Button type="submit" loading={busy} className="w-full">Sign in</Button>
        </form>
      </Card>
      <p className="mt-4 text-center text-sm text-tu-dim">
        New here? <Link to="/signup" className="font-semibold text-tu-accent hover:underline">Create an account</Link>
      </p>
    </AuthShell>
  )
}
