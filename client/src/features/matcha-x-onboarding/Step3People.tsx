import { useRef, useState } from 'react'
import { Link2, Loader2, Upload } from 'lucide-react'
import { api } from '../../api/client'

// CSV bulk-add (send_invitations=false during onboarding) OR connect an HRIS via
// Finch. Both reuse existing endpoints unchanged.
export default function Step3People({ onDone }: { onDone: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [connecting, setConnecting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<string | null>(null)

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    if (!firstName || !lastName || !email) return
    setSubmitting(true)
    setError(null)
    try {
      await api.post('/employees', {
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        email: email.trim().toLowerCase(),
        skip_invitation: true,
        skip_google_workspace_provisioning: true,
      })
      setFirstName('')
      setLastName('')
      setEmail('')
      setResult('Employee added.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add employee')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleCsv(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setError(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await api.upload<{ created: number; failed: number }>(
        '/employees/bulk-upload?send_invitations=false',
        fd,
      )
      setResult(`Imported ${res.created} employees${res.failed ? `, ${res.failed} failed` : ''}.`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to upload CSV')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  async function connectHris() {
    setConnecting(true)
    setError(null)
    try {
      const res = await api.get<{ oauth_url: string }>('/provisioning/hris/finch/authorize')
      if (res.oauth_url) {
        window.location.href = res.oauth_url
        return
      }
      setError('Could not start HRIS connection.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start HRIS connection')
    } finally {
      setConnecting(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-zinc-100 mb-1">Add your team</h2>
        <p className="text-sm text-zinc-400">
          Drop a CSV, add someone manually, or connect your HRIS. Their work states feed
          straight into the compliance build. No invitations are sent during setup.
        </p>
      </div>

      {/* HRIS connect — pulls the roster automatically */}
      <button
        type="button"
        onClick={connectHris}
        disabled={connecting}
        className="w-full flex items-center justify-between gap-3 bg-zinc-900 border border-zinc-800 hover:border-emerald-800 rounded-lg px-4 py-3 transition-colors disabled:opacity-50"
      >
        <span className="flex items-center gap-2.5 text-sm text-zinc-200">
          <Link2 className="w-4 h-4 text-emerald-400" />
          Connect your HRIS (Rippling, BambooHR, ADP, Gusto…)
        </span>
        {connecting ? <Loader2 className="w-4 h-4 animate-spin text-zinc-400" /> : <span className="text-xs text-zinc-500">via Finch →</span>}
      </button>

      <div className="flex items-center gap-3 text-xs text-zinc-600">
        <div className="h-px flex-1 bg-zinc-800" /> or add manually <div className="h-px flex-1 bg-zinc-800" />
      </div>

      <form onSubmit={handleAdd} className="space-y-3 bg-zinc-900/40 border border-zinc-800 rounded p-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label="First name" value={firstName} onChange={setFirstName} />
          <Field label="Last name" value={lastName} onChange={setLastName} />
        </div>
        <Field label="Email" type="email" value={email} onChange={setEmail} />
        <button
          type="submit"
          disabled={submitting || !firstName || !lastName || !email}
          className="bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded transition-colors flex items-center"
        >
          {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Add employee'}
        </button>
      </form>

      <div className="bg-zinc-900/40 border border-zinc-800 rounded p-4">
        <h3 className="text-sm font-semibold text-zinc-200 mb-2">Or upload a CSV</h3>
        <p className="text-xs text-zinc-500 mb-3">
          Required columns: email, first_name, last_name. Optional: work_state, job_title, department.
        </p>
        <div className="flex items-center gap-3">
          <a href="/api/employees/bulk-upload/template" className="text-xs text-emerald-500 hover:text-emerald-400 underline">
            Download template
          </a>
          <label className="flex items-center gap-2 text-sm text-zinc-300 hover:text-zinc-100 cursor-pointer">
            <Upload className="w-4 h-4" />
            <span>{uploading ? 'Uploading…' : 'Upload CSV'}</span>
            <input ref={fileRef} type="file" accept=".csv" onChange={handleCsv} className="hidden" />
          </label>
        </div>
      </div>

      {result && <p className="text-sm text-emerald-400">{result}</p>}
      {error && <p className="text-sm text-red-400">{error}</p>}

      <button
        onClick={onDone}
        className="bg-emerald-700 hover:bg-emerald-600 text-white font-medium px-5 py-2 rounded transition-colors"
      >
        Continue to the build →
      </button>
    </div>
  )
}

function Field({
  label,
  value,
  onChange,
  type = 'text',
}: {
  label: string
  value: string
  onChange: (v: string) => void
  type?: string
}) {
  return (
    <label className="block">
      <span className="text-xs text-zinc-400 uppercase tracking-wide">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700"
      />
    </label>
  )
}
