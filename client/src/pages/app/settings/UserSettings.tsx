import { useRef, useState, useCallback } from 'react'
import { Camera, Loader2, Check, Lock } from 'lucide-react'
import { useMe } from '../../../hooks/useMe'
import { uploadAvatar, api } from '../../../api/client'
import Avatar from '../../../components/shared/Avatar'
import ProfileResumeSection from '../../../components/profile/ProfileResumeSection'

function validatePasswordStrength(pw: string): string | null {
  if (pw.length < 8) return 'Must be at least 8 characters'
  if (!/[A-Z]/.test(pw)) return 'Must include an uppercase letter'
  if (!/[a-z]/.test(pw)) return 'Must include a lowercase letter'
  if (!/[0-9]/.test(pw)) return 'Must include a number'
  if (!/[^A-Za-z0-9]/.test(pw)) return 'Must include a special character'
  return null
}

export default function UserSettings() {
  const { me, refresh } = useMe()
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  const [cpCurrent, setCpCurrent] = useState('')
  const [cpNew, setCpNew] = useState('')
  const [cpConfirm, setCpConfirm] = useState('')
  const [cpSaving, setCpSaving] = useState(false)
  const [cpError, setCpError] = useState<string | null>(null)
  const [cpSuccess, setCpSuccess] = useState(false)

  const currentAvatar = avatarUrl ?? me?.user?.avatar_url ?? null
  const userName = me?.profile?.name ?? me?.user?.email ?? 'User'

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault()
    setCpError(null)
    setCpSuccess(false)

    const strengthErr = validatePasswordStrength(cpNew)
    if (strengthErr) { setCpError(strengthErr); return }
    if (cpNew !== cpConfirm) { setCpError('Passwords do not match'); return }

    setCpSaving(true)
    try {
      await api.post('/auth/change-password', { current_password: cpCurrent, new_password: cpNew })
      setCpSuccess(true)
      setCpCurrent('')
      setCpNew('')
      setCpConfirm('')
      setTimeout(() => setCpSuccess(false), 3000)
    } catch (err) {
      setCpError(err instanceof Error ? err.message : 'Failed to change password')
    } finally {
      setCpSaving(false)
    }
  }

  const handleUpload = useCallback(async (file: File) => {
    if (!file.type.startsWith('image/')) {
      setError('Please select an image file')
      return
    }
    if (file.size > 5 * 1024 * 1024) {
      setError('Image must be under 5 MB')
      return
    }

    setUploading(true)
    setError(null)
    setSuccess(false)
    try {
      const result = await uploadAvatar(file)
      setAvatarUrl(result.avatar_url)
      refresh()
      setSuccess(true)
      setTimeout(() => setSuccess(false), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }, [])

  return (
    <div className="max-w-xl mx-auto py-10 px-6">
      <h1 className="text-xl font-semibold text-zinc-100 mb-8">Settings</h1>

      {/* Avatar section */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
        <h2 className="text-sm font-medium text-zinc-300 mb-4">Profile Photo</h2>

        <div className="flex items-center gap-5">
          <div className="relative group">
            <Avatar name={userName} avatarUrl={currentAvatar} size="lg" />
            <button
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              className="absolute inset-0 rounded-full bg-black/50 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity"
            >
              {uploading ? (
                <Loader2 className="w-5 h-5 text-white animate-spin" />
              ) : (
                <Camera className="w-5 h-5 text-white" />
              )}
            </button>
            <input
              ref={fileRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) handleUpload(file)
                e.target.value = ''
              }}
            />
          </div>

          <div>
            <p className="text-sm text-zinc-300">{userName}</p>
            <p className="text-xs text-zinc-500 mt-0.5">{me?.user?.email}</p>
            <button
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              className="mt-2 text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              {currentAvatar ? 'Change photo' : 'Upload photo'}
            </button>
          </div>
        </div>

        {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
        {success && (
          <p className="mt-3 text-sm text-emerald-400 flex items-center gap-1.5">
            <Check className="w-3.5 h-3.5" /> Photo updated
          </p>
        )}

        <p className="mt-4 text-xs text-zinc-600">JPEG, PNG, or WebP. Max 5 MB.</p>
      </div>

      {/* Change password */}
      <div className="mt-6 rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
        <div className="flex items-center gap-2 mb-4">
          <Lock className="w-4 h-4 text-zinc-400" />
          <h2 className="text-sm font-medium text-zinc-300">Change Password</h2>
        </div>

        <form onSubmit={handleChangePassword} className="space-y-3">
          <div>
            <label className="block text-xs text-zinc-400 mb-1">Current Password</label>
            <input
              type="password"
              value={cpCurrent}
              onChange={(e) => setCpCurrent(e.target.value)}
              required
              autoComplete="current-password"
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-zinc-500"
            />
          </div>
          <div>
            <label className="block text-xs text-zinc-400 mb-1">New Password</label>
            <input
              type="password"
              value={cpNew}
              onChange={(e) => setCpNew(e.target.value)}
              required
              autoComplete="new-password"
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-zinc-500"
            />
          </div>
          <div>
            <label className="block text-xs text-zinc-400 mb-1">Confirm New Password</label>
            <input
              type="password"
              value={cpConfirm}
              onChange={(e) => setCpConfirm(e.target.value)}
              required
              autoComplete="new-password"
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-zinc-500"
            />
          </div>

          {cpError && <p className="text-sm text-red-400">{cpError}</p>}
          {cpSuccess && (
            <p className="text-sm text-emerald-400 flex items-center gap-1.5">
              <Check className="w-3.5 h-3.5" /> Password changed
            </p>
          )}

          <button
            type="submit"
            disabled={cpSaving || !cpCurrent || !cpNew || !cpConfirm}
            className="mt-1 rounded-lg bg-zinc-700 px-4 py-1.5 text-sm text-zinc-100 hover:bg-zinc-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {cpSaving ? 'Saving…' : 'Change Password'}
          </button>
        </form>
      </div>

      <div className="mt-6">
        <ProfileResumeSection />
      </div>
    </div>
  )
}
