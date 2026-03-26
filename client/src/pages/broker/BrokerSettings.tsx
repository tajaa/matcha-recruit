import { useState } from 'react'
import { Button, Input, Card } from '../../components/ui'
import { api } from '../../api/client'
import { Lock, Check } from 'lucide-react'

export default function BrokerSettings() {
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
    <div className="max-w-lg">
      <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight mb-2">Settings</h1>
      <p className="text-sm text-zinc-500 mb-6">Manage your broker account settings.</p>

      <Card className="p-5">
        <div className="flex items-center gap-2 mb-4">
          <Lock size={16} className="text-zinc-400" />
          <h2 className="text-sm font-medium text-zinc-200">Change Password</h2>
        </div>

        <form onSubmit={handleChangePassword} className="space-y-3">
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
            <div className="flex items-center gap-2 text-sm text-emerald-400">
              <Check size={14} />
              Password changed successfully
            </div>
          )}

          <Button type="submit" size="sm" disabled={saving || !currentPassword || !newPassword || !confirmPassword}>
            {saving ? 'Changing...' : 'Change Password'}
          </Button>
        </form>
      </Card>
    </div>
  )
}
