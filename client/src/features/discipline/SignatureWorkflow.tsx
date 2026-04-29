import { useState } from 'react'
import { Button, Textarea } from '../../components/ui'
import {
  CheckCircle2,
  Send,
  Ban,
  Upload,
  Download,
  Loader2,
} from 'lucide-react'
import type { DisciplineRecord } from '../../api/discipline'

type Props = {
  record: DisciplineRecord
  employeeName?: string
  onMeetingHeld: () => Promise<unknown>
  onRequestSignature: () => Promise<unknown>
  onRefuse: (notes: string) => Promise<unknown>
  onUploadPhysical: (file: File) => Promise<unknown>
  onDownloadLetter: () => Promise<unknown>
}

type Tab = 'digital' | 'refused' | 'physical'

export default function SignatureWorkflow({
  record,
  employeeName,
  onMeetingHeld,
  onRequestSignature,
  onRefuse,
  onUploadPhysical,
  onDownloadLetter,
}: Props) {
  const [busy, setBusy] = useState(false)
  const [activeTab, setActiveTab] = useState<Tab>('digital')
  const [refuseNotes, setRefuseNotes] = useState('')
  const [error, setError] = useState('')
  const [file, setFile] = useState<File | null>(null)

  const meetingHeld = !!record.meeting_held_at
  const status = record.status
  const sigStatus = record.signature_status
  const isClosed =
    status === 'active' || status === 'expired' || status === 'escalated' || status === 'completed'

  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    setError('')
    try {
      await action()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed')
    } finally {
      setBusy(false)
    }
  }

  if (isClosed) {
    return (
      <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-4 text-sm text-zinc-300">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>
            Workflow complete — signature: <strong className="text-zinc-100">{sigStatus}</strong>,{' '}
            status: <strong className="text-zinc-100">{status}</strong>.
          </span>
        </div>
        {record.signature_completed_at && (
          <div className="text-xs text-zinc-500 mt-1">
            Completed {new Date(record.signature_completed_at).toLocaleString()}
          </div>
        )}
      </div>
    )
  }

  if (!meetingHeld) {
    return (
      <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-4 space-y-3">
        <div className="text-sm text-zinc-300">
          Have you conducted the disciplinary meeting with the employee?
        </div>
        <div className="text-xs text-zinc-500">
          Once confirmed, you'll be able to send the document for signature.
        </div>
        <Button onClick={() => run(onMeetingHeld)} disabled={busy}>
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
          <span className="ml-2">Yes — meeting held</span>
        </Button>
        {error && <div className="text-sm text-red-400">{error}</div>}
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-4 space-y-4">
      <div className="text-sm text-zinc-300">
        Meeting held on <strong className="text-zinc-100">
          {record.meeting_held_at ? new Date(record.meeting_held_at).toLocaleDateString() : ''}
        </strong>. Choose how the signature will be captured:
      </div>

      <div className="flex gap-1 border-b border-zinc-800">
        {(['digital', 'refused', 'physical'] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            className={`px-3 py-2 text-sm border-b-2 -mb-px ${
              activeTab === t
                ? 'border-zinc-100 text-zinc-100'
                : 'border-transparent text-zinc-500 hover:text-zinc-300'
            }`}
            onClick={() => setActiveTab(t)}
          >
            {t === 'digital' && 'Digital signature'}
            {t === 'refused' && 'Refused to sign'}
            {t === 'physical' && 'Physical / scanned'}
          </button>
        ))}
      </div>

      {activeTab === 'digital' && (
        <div className="space-y-3">
          <div className="text-sm text-zinc-400">
            Send the discipline letter to{' '}
            <strong className="text-zinc-200">{employeeName || 'the employee'}</strong>{' '}
            for digital signature via the configured provider. The status will move to{' '}
            <code className="text-xs">requested</code> until the provider's webhook reports completion.
          </div>
          <Button onClick={() => run(onRequestSignature)} disabled={busy || sigStatus === 'requested'}>
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            <span className="ml-2">
              {sigStatus === 'requested' ? 'Signature requested — awaiting employee' : 'Send for signature'}
            </span>
          </Button>
        </div>
      )}

      {activeTab === 'refused' && (
        <div className="space-y-3">
          <div className="text-sm text-zinc-400">
            Record that the employee refused to sign. The warning still counts and is marked
            active. Required notes documenting the refusal.
          </div>
          <Textarea
            label="Notes"
            value={refuseNotes}
            onChange={(e) => setRefuseNotes(e.target.value)}
            rows={3}
            placeholder="Witness names, employee statement, time/place"
          />
          <Button
            variant="secondary"
            className="border border-red-900/40 text-red-300 hover:bg-red-950/40"
            onClick={() => run(() => onRefuse(refuseNotes))}
            disabled={busy || !refuseNotes.trim()}
          >
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Ban className="w-4 h-4" />}
            <span className="ml-2">Mark as refused</span>
          </Button>
        </div>
      )}

      {activeTab === 'physical' && (
        <div className="space-y-3">
          <div className="text-sm text-zinc-400">
            Download the letter for in-person signing, then upload the scanned signed copy.
          </div>
          <div className="flex gap-2 flex-wrap">
            <Button variant="secondary" onClick={() => run(onDownloadLetter)} disabled={busy}>
              <Download className="w-4 h-4" />
              <span className="ml-2">Download letter PDF</span>
            </Button>
            <label className="inline-flex items-center gap-2 cursor-pointer rounded-lg border border-zinc-700 px-3.5 py-2.5 text-sm text-zinc-200 hover:bg-zinc-800">
              <Upload className="w-4 h-4" />
              <span>{file ? file.name : 'Choose signed PDF'}</span>
              <input
                type="file"
                accept="application/pdf"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </label>
            <Button
              onClick={() => file && run(() => onUploadPhysical(file))}
              disabled={busy || !file}
            >
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Upload signed copy'}
            </Button>
          </div>
        </div>
      )}

      {error && <div className="text-sm text-red-400">{error}</div>}
    </div>
  )
}
