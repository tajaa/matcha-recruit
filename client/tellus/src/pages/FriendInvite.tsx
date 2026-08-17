import { useEffect, useState } from 'react'
import { Check, Copy, Users } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { ApiError, tellusApi } from '../api/tellusClient'
import { useAccount } from '../hooks/useAccount'
import { Button, Card, ErrorText, Spinner } from '../components/ui'

interface InvitePreview {
  owner: {
    display_name: string
    handle: string | null
  }
}

export default function FriendInvite() {
  const { token = '' } = useParams()
  const { account, loading: accountLoading } = useAccount()
  const [preview, setPreview] = useState<InvitePreview | null>(null)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)
  const [redeemed, setRedeemed] = useState(false)
  const [error, setError] = useState('')

  const returnTo = `/f/${encodeURIComponent(token)}`

  useEffect(() => {
    if (!account || account.account_type !== 'consumer' || !token) return
    let live = true
    setLoading(true)
    setError('')
    tellusApi.get<InvitePreview>(`/friends/invite/${encodeURIComponent(token)}`)
      .then((value) => { if (live) setPreview(value) })
      .catch((e: unknown) => {
        if (!live) return
        setError(e instanceof Error ? e.message : 'This invite is no longer available.')
      })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [account?.account_type, account?.id, token])

  async function redeem() {
    setError('')
    setBusy(true)
    try {
      await tellusApi.post(`/friends/invite/${encodeURIComponent(token)}/redeem`)
      setRedeemed(true)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not redeem this invite.')
    } finally {
      setBusy(false)
    }
  }

  async function copyToken() {
    try {
      await navigator.clipboard.writeText(token)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    } catch {
      setError('Could not copy the invite code. Select it and copy it manually.')
    }
  }

  if (!token) {
    return (
      <div className="mx-auto max-w-md px-4 py-16 text-center">
        <h1 className="text-lg font-bold">Invalid invite</h1>
        <p className="mt-2 text-sm text-tu-dim">This invite link is missing its code.</p>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-md px-4 py-12">
      <div className="mb-6 text-center">
        <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-tu-accent text-black">
          <Users className="h-6 w-6" />
        </div>
        <h1 className="text-xl font-bold">You&apos;ve been invited to connect</h1>
        <p className="mt-1 text-sm text-tu-dim">Join your friend on Tell-Us.</p>
      </div>

      <Card>
        <p className="text-xs font-medium uppercase tracking-wide text-tu-faint">Invite code</p>
        <code className="mt-2 block break-all rounded-lg bg-tu-panel2 px-3 py-2 text-sm text-tu-text">{token}</code>
        <Button variant="soft" size="sm" className="mt-3" onClick={copyToken}>
          {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          {copied ? 'Copied' : 'Copy code'}
        </Button>

        <div className="mt-5 space-y-3">
          <ErrorText>{error}</ErrorText>

          {accountLoading ? (
            <Spinner />
          ) : !account ? (
            <>
              <p className="text-sm text-tu-dim">Sign in or create a consumer account to preview and redeem this invite.</p>
              <div className="flex gap-2">
                <Link className="flex-1" to={`/login?returnTo=${encodeURIComponent(returnTo)}`}>
                  <Button className="w-full">Sign in</Button>
                </Link>
                <Link className="flex-1" to={`/signup?returnTo=${encodeURIComponent(returnTo)}`}>
                  <Button variant="soft" className="w-full">Create account</Button>
                </Link>
              </div>
            </>
          ) : account.account_type !== 'consumer' ? (
            <p className="text-sm text-tu-dim">Friend invites are available to consumer accounts.</p>
          ) : loading ? (
            <Spinner />
          ) : preview ? (
            <>
              <p className="text-sm text-tu-dim">
                <span className="font-semibold text-tu-text">{preview.owner.display_name}</span>
                {preview.owner.handle ? ` (@${preview.owner.handle})` : ''} invited you to connect.
              </p>
              {redeemed ? (
                <p className="flex items-center gap-2 text-sm text-tu-good"><Check className="h-4 w-4" /> You&apos;re friends now.</p>
              ) : (
                <Button className="w-full" loading={busy} onClick={() => void redeem()}>Add friend</Button>
              )}
            </>
          ) : null}
        </div>
      </Card>
    </div>
  )
}
