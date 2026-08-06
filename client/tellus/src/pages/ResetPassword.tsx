import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { tellusPublicPost } from '../api/tellusClient'
import { Button, Card, ErrorText, Input } from '../components/ui'
import { AuthShell } from './AuthShell'

export default function ResetPassword() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setErr('')
    if (password.length < 8) { setErr('Password must be at least 8 characters.'); return }
    if (password !== confirm) { setErr("Passwords don't match."); return }
    setBusy(true)
    try {
      await tellusPublicPost('/auth/reset-password', { token, new_password: password })
      setDone(true)
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to reset password')
    } finally {
      setBusy(false)
    }
  }

  if (!token) {
    return (
      <AuthShell title="Invalid link" subtitle="This password reset link is missing its token.">
        <Card><ErrorText>Ask an admin to generate a new reset link.</ErrorText></Card>
      </AuthShell>
    )
  }

  if (done) {
    return (
      <AuthShell title="Password updated" subtitle="You can now sign in with your new password.">
        <Card>
          <Link to="/login" className="font-semibold text-tu-accent hover:underline">Go to sign in</Link>
        </Card>
      </AuthShell>
    )
  }

  return (
    <AuthShell title="Set a new password" subtitle="Choose a new password for your Tell-Us account.">
      <Card>
        <form onSubmit={submit} className="space-y-4">
          <Input label="New password" type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} />
          <Input label="Confirm password" type="password" required minLength={8} value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          <ErrorText>{err}</ErrorText>
          <Button type="submit" loading={busy} className="w-full">Update password</Button>
        </form>
      </Card>
    </AuthShell>
  )
}
