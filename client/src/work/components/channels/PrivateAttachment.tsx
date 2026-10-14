import { useEffect, useState } from 'react'
import { FileText, Lock } from 'lucide-react'
import { getAssistantInputLink } from '../../api/matchaWork/assistant'

type Attachment = { url: string; filename: string; content_type: string; size: number }

function sizeLabel(bytes: number) {
  return bytes >= 1_000_000 ? `${(bytes / 1_000_000).toFixed(1)}MB` : `${Math.round(bytes / 1_000)}KB`
}

/**
 * A file given to Espresso. It has no public URL (server:
 * agent_runtime/inputs.py): a photo loads through a short-lived link, and a
 * document's link is fetched when it's opened, so it's never stale.
 */
export default function PrivateAttachment({ att, inputId }: { att: Attachment; inputId: string }) {
  const isImage = att.content_type.startsWith('image/')
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!isImage) return
    let cancelled = false
    getAssistantInputLink(inputId)
      .then((link) => { if (!cancelled) setImageUrl(link.url) })
      .catch(() => { if (!cancelled) setFailed(true) })
    return () => { cancelled = true }
  }, [inputId, isImage])

  async function open() {
    try {
      const link = await getAssistantInputLink(inputId)
      window.open(link.url, '_blank', 'noopener,noreferrer')
    } catch {
      setFailed(true)
    }
  }

  if (isImage && imageUrl && !failed) {
    return (
      <button type="button" onClick={open} title="Only you can open this file">
        <img src={imageUrl} alt={att.filename} className="max-w-xs max-h-48 rounded-md border border-w-line" />
      </button>
    )
  }
  return (
    <button
      type="button"
      onClick={open}
      title="Only you can open this file"
      className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-w-surface2 border border-w-line text-xs text-w-text hover:text-white hover:border-w-accent/40 transition-colors"
    >
      <FileText size={12} className="shrink-0" />
      <span className="truncate max-w-[200px]">{att.filename}</span>
      {failed ? (
        <span className="text-w-dim shrink-0">unavailable</span>
      ) : (
        <span className="text-w-dim shrink-0">{sizeLabel(att.size)}</span>
      )}
      <Lock size={10} className="shrink-0 text-w-dim" />
    </button>
  )
}
