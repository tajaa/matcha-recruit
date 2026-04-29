import { useRef, useState } from 'react'
import { Loader2, Upload } from 'lucide-react'
import { api } from '../../api/client'

export default function Step2Employees({ onDone }: { onDone: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [uid, setUid] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [uploading, setUploading] = useState(false)
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
        uid: uid.trim() || null,
        skip_invitation: true,
        skip_google_workspace_provisioning: true,
      })
      setFirstName('')
      setLastName('')
      setEmail('')
      setUid('')
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

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-zinc-100 mb-1">Add employees</h2>
        <p className="text-sm text-zinc-400">
          Add at least one to continue. UIDs (badge or employee numbers) are optional but make incident filing faster.
        </p>
      </div>

      <form onSubmit={handleAdd} className="space-y-3 bg-zinc-900/40 border border-zinc-800 rounded p-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label="First name" value={firstName} onChange={setFirstName} />
          <Field label="Last name" value={lastName} onChange={setLastName} />
        </div>
        <Field label="Email" type="email" value={email} onChange={setEmail} />
        <Field label="UID" value={uid} onChange={setUid} optional placeholder="e.g. EMP-001" />
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
          Required columns: email, first_name, last_name. Optional: uid, work_state, job_title, department.
        </p>
        <div className="flex items-center gap-3">
          <a href="/api/employees/bulk-upload/template" className="text-xs text-emerald-500 hover:text-emerald-400 underline">
            Download template
          </a>
          <label className="flex items-center gap-2 text-sm text-zinc-300 hover:text-zinc-100 cursor-pointer">
            <Upload className="w-4 h-4" />
            <span>{uploading ? 'Uploading...' : 'Upload CSV'}</span>
            <input ref={fileRef} type="file" accept=".csv" onChange={handleCsv} className="hidden" />
          </label>
        </div>
      </div>

      {result && <p className="text-sm text-emerald-400">{result}</p>}
      {error && <p className="text-sm text-red-400">{error}</p>}

      <button
        onClick={onDone}
        className="text-sm text-zinc-300 hover:text-zinc-100 underline"
      >
        Continue →
      </button>
    </div>
  )
}

function Field({
  label,
  value,
  onChange,
  type = 'text',
  optional,
  placeholder,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  type?: string
  optional?: boolean
  placeholder?: string
}) {
  return (
    <label className="block">
      <span className="text-xs text-zinc-400 uppercase tracking-wide">
        {label}
        {optional && <span className="text-zinc-600 normal-case ml-1">(optional)</span>}
      </span>
      <input
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700"
      />
    </label>
  )
}
