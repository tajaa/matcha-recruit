import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { tellusApi } from '../../api/tellusClient'
import { BoardPostCard } from '../../components/BoardPostCard'
import { Card, Empty, ErrorText, Select, Spinner } from '../../components/ui'
import type { BoardPage, BoardPostKind } from '../../api/types'

const KIND_OPTIONS: { value: BoardPostKind | ''; label: string }[] = [
  { value: '', label: 'All posts' },
  { value: 'update', label: 'Updates' },
  { value: 'deal', label: 'Deals' },
  { value: 'event', label: 'Events' },
  { value: 'question', label: 'Questions' },
]

export default function BoardFeed() {
  const { slug = '' } = useParams()
  const [page, setPage] = useState<BoardPage | null>(null)
  const [kind, setKind] = useState<BoardPostKind | ''>('')
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [forbidden, setForbidden] = useState(false)
  const [redeemMsg, setRedeemMsg] = useState('')

  async function load() {
    setLoading(true); setErr(''); setForbidden(false)
    try {
      const qs = kind ? `?kind=${kind}` : ''
      setPage(await tellusApi.get<BoardPage>(`/boards/${slug}${qs}`))
    } catch (e) {
      if (e instanceof Error && e.message.includes('Request to join')) setForbidden(true)
      else setErr(e instanceof Error ? e.message : 'Failed to load this board')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [slug, kind])

  async function redeem(listingId: string) {
    setRedeemMsg('')
    try {
      await tellusApi.post('/redeem', { listing_id: listingId })
      setRedeemMsg('Redeemed! Check My Rewards for your code.')
    } catch (e) {
      setRedeemMsg(e instanceof Error ? e.message : 'Could not redeem this reward.')
    }
  }

  if (loading) return <Spinner />

  if (forbidden) {
    return (
      <Card>
        <p className="text-sm text-tu-dim">
          You need to be an approved member of this regulars board to view it.{' '}
          <Link to={`/b/${slug}`} className="font-semibold text-tu-accent hover:underline">Request to join from the brand page →</Link>
        </p>
      </Card>
    )
  }

  if (err || !page) return <ErrorText>{err || 'This board is unavailable.'}</ErrorText>

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        {page.logo_url && <img src={page.logo_url} alt="" className="h-10 w-10 rounded-lg object-cover" />}
        <div>
          <h1 className="text-lg font-semibold">{page.brand_name} — Regulars</h1>
          {page.description && <p className="text-sm text-tu-dim">{page.description}</p>}
        </div>
      </div>

      {page.plan_paused && (
        <Card className="border-tu-bad/30 bg-tu-bad/5">
          <p className="text-sm text-tu-dim">This board is paused — you can read past posts, but new replies aren't accepted right now.</p>
        </Card>
      )}

      <div className="w-48"><Select value={kind} onChange={(e) => setKind(e.target.value as BoardPostKind | '')} options={KIND_OPTIONS} /></div>

      {redeemMsg && <p className="text-sm text-tu-accent">{redeemMsg}</p>}

      {page.posts.length === 0 ? (
        <Empty>No posts here yet.</Empty>
      ) : (
        <div className="space-y-3">
          {page.posts.map((p) => (
            <BoardPostCard key={p.id} post={p} viewerRole={page.viewer_role} slug={slug} onRedeem={redeem} />
          ))}
        </div>
      )}
    </div>
  )
}
