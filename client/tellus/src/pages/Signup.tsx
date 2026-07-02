import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { tellusPublicPost } from '../api/tellusClient'
import { useAccount } from '../hooks/useAccount'
import { Button, Card, ErrorText, Input } from '../components/ui'
import type { AccountType, SignupResponse } from '../api/types'
import { AuthShell } from './AuthShell'

export default function Signup() {
  const { setSession } = useAccount()
  const navigate = useNavigate()
  const [type, setType] = useState<AccountType>('consumer')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [brandName, setBrandName] = useState('')
  const [city, setCity] = useState('')
  const [state, setState] = useState('')
  const [err, setErr] = useState('')
  const [sent, setSent] = useState(false)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setErr(''); setBusy(true)
    try {
      const res = await tellusPublicPost<SignupResponse>('/auth/signup', {
        email, password, display_name: displayName || null, account_type: type,
        brand_name: type === 'brand' ? brandName : null,
        city: type === 'consumer' ? city : null,
        state: type === 'consumer' ? state : null,
      })
      if (res.verification_required) {
        setSent(true)
      } else if (res.access_token && res.refresh_token && res.account) {
        setSession({ access_token: res.access_token, refresh_token: res.refresh_token, expires_in: res.expires_in ?? 0, account: res.account })
        navigate('/')
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Signup failed')
    } finally {
      setBusy(false)
    }
  }

  if (sent) {
    return (
      <AuthShell title="Check your inbox" subtitle={`We sent a confirmation link to ${email}.`}>
        <Card><p className="text-sm text-tu-dim">Click the link in that email to activate your account, then sign in.</p></Card>
        <p className="mt-4 text-center text-sm text-tu-dim">
          <Link to="/login" className="font-semibold text-tu-accent hover:underline">Back to sign in</Link>
        </p>
      </AuthShell>
    )
  }

  return (
    <AuthShell title="Join Tell-Us" subtitle="Feedback that pays off.">
      <Card>
        <div className="mb-4 grid grid-cols-2 gap-2">
          {(['consumer', 'brand'] as AccountType[]).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setType(t)}
              className={`rounded-lg border px-3 py-2 text-sm font-semibold capitalize transition ${
                type === t ? 'border-tu-accent bg-tu-accent/10 text-tu-accent' : 'border-tu-border text-tu-dim hover:text-tu-text'
              }`}
            >
              {t === 'consumer' ? "I'm a customer" : "I'm a brand"}
            </button>
          ))}
        </div>
        <form onSubmit={submit} className="space-y-4">
          <Input label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          <Input label="Password" type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} />
          <Input label="Display name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="Optional" />
          {type === 'brand' ? (
            <Input label="Brand name" required value={brandName} onChange={(e) => setBrandName(e.target.value)} />
          ) : (
            <div className="grid grid-cols-2 gap-3">
              <Input label="City" value={city} onChange={(e) => setCity(e.target.value)} placeholder="e.g. Austin" />
              <Input label="State" value={state} onChange={(e) => setState(e.target.value)} placeholder="TX" />
            </div>
          )}
          <ErrorText>{err}</ErrorText>
          <Button type="submit" loading={busy} className="w-full">Create account</Button>
        </form>
      </Card>
      <p className="mt-4 text-center text-sm text-tu-dim">
        Already have an account? <Link to="/login" className="font-semibold text-tu-accent hover:underline">Sign in</Link>
      </p>
    </AuthShell>
  )
}
