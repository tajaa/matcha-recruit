import { useState } from 'react'
import { Button, Input } from '../../components/ui'
import { HelpHint } from '../../components/broker/HelpHint'
import { api } from '../../api/client'
import { Lock, Check } from 'lucide-react'

export default function BrokerSettings({ embedded = false }: { embedded?: boolean }) {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setSuccess(false)

    if (newPassword.length < 8) {
      setError('New password must be at least 8 characters')
      return
    }
    if (newPassword !== confirmPassword) {
      setError('Passwords do not match')
      return
    }

    setSaving(true)
    try {
      await api.post('/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword,
      })
      setSuccess(true)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to change password')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="max-w-xl">
      {!embedded && (
        <>
          <h1 className="mb-2 flex items-center gap-2 text-xl font-semibold tracking-tight text-zinc-100">Settings <HelpHint text="Your broker account preferences — login, password, and account-level options." /></h1>
          <p className="mb-6 text-sm text-zinc-500">Manage your broker account settings.</p>
        </>
      )}

      <div className="overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-900/50">
        <div className="flex items-center gap-2 border-b border-zinc-800/60 px-5 py-3.5">
          <Lock size={15} className="text-zinc-500" />
          <h2 className="text-[11px] font-bold uppercase tracking-widest text-zinc-500">Change password</h2>
        </div>

        <form onSubmit={handleChangePassword} className="space-y-3 p-5">
          <Input
            label="Current Password"
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            required
          />
          <Input
            label="New Password"
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
          />
          <Input
            label="Confirm New Password"
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
          />

          {error && <p className="text-sm text-red-400">{error}</p>}
          {success && (
            <div className="flex items-center gap-2 text-sm text-zinc-100">
              <Check size={14} />
              Password changed successfully
            </div>
          )}

          <Button type="submit" size="sm" disabled={saving || !currentPassword || !newPassword || !confirmPassword}>
            {saving ? 'Changing...' : 'Change Password'}
          </Button>
        </form>
      </div>
    </div>
  )
}
