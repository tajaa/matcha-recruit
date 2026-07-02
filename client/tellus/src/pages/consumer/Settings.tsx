import { useState } from 'react'
import { tellusApi } from '../../api/tellusClient'
import { useAccount } from '../../hooks/useAccount'
import { Button, Card, ErrorText, Input } from '../../components/ui'
import type { TellusAccount } from '../../api/types'

export default function ConsumerSettings() {
  const { account, refreshAccount } = useAccount()
  const [displayName, setDisplayName] = useState(account?.display_name ?? '')
  const [city, setCity] = useState(account?.city ?? '')
  const [state, setState] = useState(account?.state ?? '')
  const [optIn, setOptIn] = useState(account?.leaderboard_opt_in ?? true)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  async function saveProfile() {
    setBusy(true); setErr(''); setMsg('')
    try {
      await tellusApi.patch<TellusAccount>('/me', { display_name: displayName, leaderboard_opt_in: optIn })
      await refreshAccount()
      setMsg('Saved.')
    } catch (e) { setErr(e instanceof Error ? e.message : 'Save failed') } finally { setBusy(false) }
  }

  async function saveLocation() {
    setBusy(true); setErr(''); setMsg('')
    try {
      await tellusApi.post<TellusAccount>('/me/location', { city, state })
      await refreshAccount()
      setMsg('Location updated.')
    } catch (e) { setErr(e instanceof Error ? e.message : 'Save failed') } finally { setBusy(false) }
  }

  return (
    <div className="max-w-lg space-y-5">
      <h1 className="text-lg font-bold">Settings</h1>

      <Card className="space-y-4">
        <h2 className="text-sm font-semibold">Profile</h2>
        <Input label="Display name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
        <label className="flex items-center gap-2 text-sm text-tu-dim">
          <input type="checkbox" checked={optIn} onChange={(e) => setOptIn(e.target.checked)} className="accent-tu-accent" />
          Show me on the leaderboard
        </label>
        <Button onClick={saveProfile} loading={busy} variant="soft">Save profile</Button>
      </Card>

      <Card className="space-y-4">
        <h2 className="text-sm font-semibold">Your city</h2>
        <p className="text-xs text-tu-faint">Sets which local rewards you see in the marketplace.</p>
        <div className="grid grid-cols-2 gap-3">
          <Input label="City" value={city} onChange={(e) => setCity(e.target.value)} />
          <Input label="State" value={state} onChange={(e) => setState(e.target.value)} />
        </div>
        <Button onClick={saveLocation} loading={busy} variant="soft">Update location</Button>
      </Card>

      {msg && <p className="text-sm text-tu-good">{msg}</p>}
      <ErrorText>{err}</ErrorText>
    </div>
  )
}
