import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError, tellusApi } from '../../api/tellusClient'
import { BoardPostCard } from '../../components/BoardPostCard'
import { Button, Card, Empty, ErrorText, Select, Spinner } from '../../components/ui'
import type { BoardPage, BoardPost, BoardPostKind } from '../../api/types'

const PAGE_SIZE = 20

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
  const [posts, setPosts] = useState<BoardPost[]>([])
  const [kind, setKind] = useState<BoardPostKind | ''>('')
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [err, setErr] = useState('')
  const [forbidden, setForbidden] = useState(false)
  const [paused, setPaused] = useState(false)
  const [redeemMsg, setRedeemMsg] = useState('')

  async function load(reset: boolean) {
    if (reset) { setLoading(true); setForbidden(false); setPaused(false) } else { setLoadingMore(true) }
    setErr('')
    try {
      const offset = reset ? 0 : posts.length
      const kindQs = kind ? `&kind=${kind}` : ''
      const p = await tellusApi.get<BoardPage>(`/boards/${slug}?limit=${PAGE_SIZE}&offset=${offset}${kindQs}`)
      setPage(p)
      setPosts(reset ? p.posts : [...posts, ...p.posts])
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) setForbidden(true)
      else if (e instanceof ApiError && e.status === 409 && e.message === 'This board is paused.') setPaused(true)
      else setErr(e instanceof Error ? e.message : 'Failed to load this board')
    } finally {
      setLoading(false); setLoadingMore(false)
    }
  }

  useEffect(() => { void load(true) }, [slug, kind])

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

  if (paused) {
    return (
      <Card>
        <p className="text-sm text-tu-dim">This board is paused — new memberships are not being accepted right now.</p>
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

      {(page.plan_paused || !page.is_active) && (
        <Card className="border-tu-bad/30 bg-tu-bad/5">
          <p className="text-sm text-tu-dim">This board is paused — you can read past posts, but new replies aren't accepted right now.</p>
        </Card>
      )}

      <div className="w-48"><Select value={kind} onChange={(e) => setKind(e.target.value as BoardPostKind | '')} options={KIND_OPTIONS} /></div>

      {redeemMsg && <p className="text-sm text-tu-accent">{redeemMsg}</p>}

      {posts.length === 0 ? (
        <Empty>No posts here yet.</Empty>
      ) : (
        <div className="space-y-3">
          {posts.map((p) => (
            <BoardPostCard
              key={p.id} post={p} viewerRole={page.viewer_role} canManageBoard={page.can_manage_board} slug={slug} brandId={page.brand_id} onRedeem={redeem}
              paused={page.plan_paused || !page.is_active}
            />
          ))}
        </div>
      )}

      {posts.length < page.total && (
        <div className="flex justify-center">
          <Button variant="soft" loading={loadingMore} onClick={() => void load(false)}>
            Show more ({page.total - posts.length})
          </Button>
        </div>
      )}
    </div>
  )
}
