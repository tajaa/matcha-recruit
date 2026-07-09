import { useCallback, useEffect, useState } from 'react'
import { Check, Copy, Link2, Loader2 } from 'lucide-react'
import { handbooks } from '../../api/client'
import { Button, Card, useToast } from '../ui'
import type { HandbookShareLink } from '../../types/handbook'

// ---------------------------------------------------------------------------
// HandbookShareCard — mint / copy / revoke the public read-only link for a
// published handbook. The link needs no account: anyone holding the URL can
// read the handbook, and revoking is how you take it back.
// ---------------------------------------------------------------------------

export function HandbookShareCard({ handbookId }: { handbookId: string }) {
  const { toast } = useToast()
  const [link, setLink] = useState<HandbookShareLink | null>(null)
  const [loading, setLoading] = useState(true)
  // A failed lookup must not render as "never shared" — that hides a live public
  // URL from the one person who might need to revoke it.
  const [loadError, setLoadError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)

  const load = useCallback(async () => {
    try {
      setLink(await handbooks.getShareLink(handbookId))
      setLoadError(null)
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : 'Could not check for an existing link')
    } finally {
      setLoading(false)
    }
  }, [handbookId])

  useEffect(() => { void load() }, [load])

  const fullUrl = link ? `${window.location.origin}${link.url}` : ''

  const create = async () => {
    setBusy(true)
    try {
      setLink(await handbooks.createShareLink(handbookId))
      toast('Public link created', 'success')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Could not create the link', 'error')
    } finally {
      setBusy(false)
    }
  }

  const revoke = async () => {
    setBusy(true)
    try {
      await handbooks.revokeShareLink(handbookId)
      setLink(null)
      toast('Link revoked — it no longer opens', 'success')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Could not revoke the link', 'error')
    } finally {
      setBusy(false)
    }
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(fullUrl)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      toast('Could not copy — select the link and copy manually', 'error')
    }
  }

  if (loading) return null

  return (
    <Card className="mb-4">
      <div className="flex items-center gap-2 mb-2">
        <Link2 className="h-4 w-4 text-emerald-500" />
        <h3 className="text-sm font-semibold text-zinc-300">Public link</h3>
      </div>

      {loadError ? (
        <div className="flex items-center justify-between gap-4">
          <p className="text-xs text-amber-400">
            ⚠ {loadError}. This handbook may already have a live public link — reload before
            creating another.
          </p>
          <Button size="sm" variant="secondary" onClick={() => void load()} className="shrink-0">
            Retry
          </Button>
        </div>
      ) : !link ? (
        <div className="flex items-center justify-between gap-4">
          <p className="text-xs text-zinc-500">
            Create a link anyone can open to read this handbook — no account needed. It's read-only
            and has no download; revoke it at any time.
          </p>
          <Button size="sm" onClick={create} disabled={busy} className="shrink-0">
            {busy ? 'Creating…' : 'Create link'}
          </Button>
        </div>
      ) : (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <input
              readOnly
              value={fullUrl}
              onFocus={(e) => e.currentTarget.select()}
              className="flex-1 rounded-lg bg-zinc-900 border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 font-mono"
            />
            <Button size="sm" variant="secondary" onClick={copy} className="shrink-0">
              {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            </Button>
            <Button size="sm" variant="ghost" onClick={revoke} disabled={busy} className="shrink-0">
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Revoke'}
            </Button>
          </div>
          <p className="text-[11px] text-zinc-600">
            {link.view_count} view{link.view_count === 1 ? '' : 's'}
            {link.expires_at && <> · expires {new Date(link.expires_at).toLocaleDateString()}</>}
            {' · '}Read-only. Anyone with this link can read the handbook.
          </p>
        </div>
      )}
    </Card>
  )
}
