import { useState, type FormEvent } from 'react'
import { Loader2, UserRound } from 'lucide-react'
import { useMe } from '../../hooks/useMe'
import type { MeResponse } from '../../types/dashboard'
import { updateWorkProfile, uploadWorkAvatar } from '../api/account'
import { ESPRESSO_THEMES, setEspressoTheme, useEspressoTheme } from '../utils/espressoTheme'
import { useWorkSurface } from '../routes/WorkSurfaceContext'
import { avatarValidationError } from '../utils/avatarValidation'
import AiConnectorsSettings from '../components/shell/AiConnectorsSettings'

export function AccountSettings({ me, refresh }: { me: MeResponse; refresh: () => Promise<void> }) {
  const [name, setName] = useState(me.profile?.name ?? '')
  const [phone, setPhone] = useState(me.profile?.phone ?? '')
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState('')
  const canEditProfile = ['admin', 'client', 'individual', 'candidate'].includes(me.user.role) && !!me.profile
  const showPhone = ['client', 'individual', 'candidate'].includes(me.user.role)

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!canEditProfile || !name.trim()) { setMessage('Enter a name.'); return }
    setSaving(true)
    setMessage('')
    try {
      await updateWorkProfile({ name: name.trim(), ...(showPhone ? { phone: phone.trim() } : {}) })
      await refresh()
      setMessage('Profile saved.')
    } catch {
      setMessage('Could not save profile. Try again.')
    } finally { setSaving(false) }
  }

  async function changeAvatar(file: File) {
    const validation = avatarValidationError(file)
    if (validation) { setMessage(validation); return }
    setUploading(true)
    setMessage('')
    try {
      await uploadWorkAvatar(file)
      await refresh()
      setMessage('Photo updated.')
    } catch {
      setMessage('Could not upload photo. Try again.')
    } finally { setUploading(false) }
  }

  return <section className="rounded-xl border border-w-line bg-w-surface p-5">
    <h2 className="mb-4 text-sm font-semibold text-w-text">Account</h2>
    <div className="mb-5 flex items-center gap-4">
      {me.user.avatar_url ? <img src={me.user.avatar_url} alt="Your profile" className="h-14 w-14 rounded-full object-cover" /> : <div className="flex h-14 w-14 items-center justify-center rounded-full bg-w-surface2"><UserRound size={24} /></div>}
      <label className="cursor-pointer rounded-md border border-w-line px-3 py-2 text-xs text-w-text hover:bg-w-surface2">
        {uploading ? 'Uploading…' : 'Change photo'}
        <input type="file" accept="image/jpeg,image/png,image/webp" disabled={uploading} className="sr-only" onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ''; if (file) void changeAvatar(file) }} />
      </label>
    </div>
    <form onSubmit={(event) => void save(event)} className="space-y-4">
      <label className="block text-xs text-w-dim">Email<input value={me.user.email} readOnly className="mt-1 block w-full rounded-md border border-w-line bg-w-bg px-3 py-2 text-sm text-w-faint" /></label>
      {canEditProfile && <>
        <label className="block text-xs text-w-dim">Name<input value={name} onChange={(event) => setName(event.target.value)} required className="mt-1 block w-full rounded-md border border-w-line bg-w-bg px-3 py-2 text-sm text-w-text outline-none focus:border-w-accent" /></label>
        {showPhone && <label className="block text-xs text-w-dim">Phone<input type="tel" value={phone} onChange={(event) => setPhone(event.target.value)} className="mt-1 block w-full rounded-md border border-w-line bg-w-bg px-3 py-2 text-sm text-w-text outline-none focus:border-w-accent" /></label>}
        <button type="submit" disabled={saving} className="rounded-md bg-w-accent px-3 py-2 text-xs font-semibold text-w-on-accent disabled:opacity-50">{saving ? 'Saving…' : 'Save profile'}</button>
      </>}
    </form>
    {message && <p role="status" className="mt-3 text-xs text-w-dim">{message}</p>}
  </section>
}

function AppearanceSettings() {
  const theme = useEspressoTheme()
  return <section className="rounded-xl border border-w-line bg-w-surface p-5">
    <h2 className="mb-3 text-sm font-semibold text-w-text">Appearance</h2>
    <p className="mb-4 text-xs text-w-dim">Choose your Espresso workspace theme. This preference stays in this browser.</p>
    <div className="grid gap-2 sm:grid-cols-2">
      {ESPRESSO_THEMES.map((option) => <label key={option} className={`flex cursor-pointer items-center gap-2 rounded-lg border p-3 text-sm capitalize ${theme === option ? 'border-w-accent bg-w-accent/10 text-w-text' : 'border-w-line text-w-dim hover:bg-w-surface2'}`}><input type="radio" name="espresso-theme" value={option} checked={theme === option} onChange={() => setEspressoTheme(option)} className="accent-[var(--color-w-accent)]" />{option}</label>)}
    </div>
  </section>
}

export default function WorkSettings() {
  const { me, loading, refresh } = useMe()
  const surface = useWorkSurface()
  if (loading && !me) return <div className="flex justify-center p-12"><Loader2 className="animate-spin text-w-dim" /></div>
  return <div className="mx-auto max-w-2xl space-y-4 px-4 py-8 sm:px-6">
    <h1 className="text-2xl font-semibold text-w-text">Settings</h1>
    {me && <AccountSettings me={me} refresh={refresh} />}
    {surface === 'espresso' && <AppearanceSettings />}
    {me && <AiConnectorsSettings />}
    <section className="rounded-xl border border-w-line bg-w-surface p-5"><h2 className="text-sm font-semibold text-w-text">About</h2><p className="mt-2 text-xs text-w-dim">{surface === 'espresso' ? 'Espresso' : 'Matcha Work'} brings your projects, notes, and conversations together.</p></section>
  </div>
}
