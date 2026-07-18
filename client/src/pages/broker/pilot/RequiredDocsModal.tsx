import { useState } from 'react'
import { CheckCircle2, Circle, ExternalLink, Loader2, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { uploadPilotDocument, type DocRequirement, type PilotSession } from '../../../api/brokerPilot'
import { FileUpload } from '../../../components/ui'
import { DOC_TYPE_LABEL, LABEL, requirementStatus } from './shared'

const ACCEPT = '.pdf,.docx,.txt,.csv'

interface RequiredDocsModalProps {
  session: PilotSession
  requirements: DocRequirement[]
  /** Refetches session + context — a satisfied row is server-computed, never guessed here. */
  onChanged: () => Promise<void> | void
  onClose: () => void
}

/**
 * The mode's document prompt. Opened automatically when a moded session starts
 * without the documents that mode analyzes, and reachable afterwards from the
 * docs checklist and the blocked-chat banner.
 *
 * Deliberately skippable: the gate behind it is soft (chat 409s but takes
 * `force`), because a broker asks exploratory questions before the paper lands,
 * and because doc_type is AI-assigned — a misclassified upload must never trap
 * anyone in here.
 */
export function RequiredDocsModal({ session, requirements, onChanged, onClose }: RequiredDocsModalProps) {
  // Per-row, so two uploads can't collide on one spinner.
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const upload = async (req: DocRequirement, files: File[]) => {
    if (!files.length) return
    setBusy(req.doc_type)
    setError(null)
    try {
      // Sequential: each upload is a synchronous classify+extract pass, and the
      // server caps documents per session.
      for (const file of files) await uploadPilotDocument(session.id, file)
      await onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setBusy(null)
    }
  }

  const outstanding = requirements.filter((r) => r.required && !r.satisfied).length

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-lg border border-zinc-700 bg-zinc-900 p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-1 flex items-start justify-between">
          <div>
            <div className={LABEL}>{session.template?.label ?? 'Session mode'}</div>
            <h2 className="mt-1 text-base font-semibold text-zinc-100">
              {outstanding ? 'Add the documents this analysis needs' : 'Documents for this analysis'}
            </h2>
          </div>
          <button onClick={onClose} className="text-zinc-500 transition-colors hover:text-zinc-300">
            <X className="h-4 w-4" />
          </button>
        </div>
        <p className="mb-4 text-xs leading-relaxed text-zinc-500">
          Each document is analyzed once — key figures extracted — and grounds every answer from then
          on. Anything the client already has on the platform is marked covered and needs no upload.
        </p>

        {error && <p className="mb-3 text-[11px] text-red-400">{error}</p>}

        <div className="space-y-2">
          {requirements.map((req) => {
            const uploading = busy === req.doc_type
            return (
              <div
                key={req.doc_type}
                className={`rounded-md border px-3 py-2.5 ${
                  req.satisfied ? 'border-emerald-600/30 bg-emerald-600/[0.06]' : 'border-zinc-700'
                }`}
              >
                <div className="flex items-start gap-2.5">
                  {uploading ? (
                    <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-emerald-400" />
                  ) : req.satisfied ? (
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
                  ) : (
                    <Circle className="mt-0.5 h-4 w-4 shrink-0 text-zinc-600" />
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-zinc-100">{req.label}</span>
                      <span className="rounded border border-white/[0.08] bg-white/[0.03] px-1.5 py-px text-[10px] text-zinc-400">
                        {DOC_TYPE_LABEL[req.doc_type]}
                      </span>
                      {!req.required && (
                        <span className="text-[10px] uppercase tracking-wide text-zinc-600">Optional</span>
                      )}
                    </div>
                    <p className="mt-1 text-[11px] leading-relaxed text-zinc-500">{req.hint}</p>

                    {req.satisfied ? (
                      <p className="mt-1.5 text-[11px] text-emerald-400/90">
                        {uploading ? 'Analyzing document…' : requirementStatus(req)}
                      </p>
                    ) : uploading ? (
                      <p className="mt-2 text-[11px] text-zinc-400">
                        Analyzing document — this takes a moment.
                      </p>
                    ) : (
                      <div className="mt-2">
                        <FileUpload
                          accept={ACCEPT}
                          multiple
                          maxSizeMB={15}
                          disabled={busy !== null}
                          onFiles={(files) => void upload(req, files)}
                        />
                        {/* On-platform clients have a strictly better path for a
                            contract: the limit-adequacy ingest extracts the indemnity
                            clause and stamps an insurability verdict, which a plain
                            pilot upload does not. Off-platform clients have no such
                            path, so they only see the dropzone. */}
                        {req.doc_type === 'contract' && session.subject_kind === 'company' && (
                          <p className="mt-1.5 text-[11px] leading-relaxed text-zinc-600">
                            <Link
                              to={`/broker/clients/${session.subject_id}`}
                              className="inline-flex items-center gap-1 text-emerald-400/90 transition-colors hover:text-emerald-300"
                            >
                              Add it under the client's Limits tab <ExternalLink className="h-3 w-3" />
                            </Link>{' '}
                            for full clause extraction and insurability verdicts (needs the client's
                            Limit Adequacy feature). Dropping the PDF here gives a basic read.
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        <div className="mt-4 flex items-center justify-between">
          <p className="text-[11px] text-zinc-600">
            {outstanding
              ? 'You can ask questions without these — the analyst will say what it’s missing.'
              : 'Everything this mode needs is in scope.'}
          </p>
          <button
            onClick={onClose}
            disabled={busy !== null}
            className="rounded-md bg-emerald-700 px-3 py-1.5 text-xs text-white transition-colors hover:bg-emerald-600 disabled:opacity-40"
          >
            {outstanding ? 'Skip for now' : 'Done'}
          </button>
        </div>
      </div>
    </div>
  )
}
