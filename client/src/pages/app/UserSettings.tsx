import { useRef, useState, useCallback } from 'react'
import { Camera, Loader2, Check } from 'lucide-react'
import { useMe } from '../../hooks/useMe'
import { uploadAvatar } from '../../api/client'
import Avatar from '../../components/Avatar'
import ProfileResumeSection from '../../components/profile/ProfileResumeSection'

export default function UserSettings() {
  const { me, refresh } = useMe()
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  const currentAvatar = avatarUrl ?? me?.user?.avatar_url ?? null
  const userName = me?.profile?.name ?? me?.user?.email ?? 'User'

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

      <div className="mt-6">
        <ProfileResumeSection />
      </div>
    </div>
  )
}
