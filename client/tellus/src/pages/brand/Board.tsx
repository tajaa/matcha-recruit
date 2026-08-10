import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Heart, Pencil, Plus, Star } from 'lucide-react'
import { tellusApi } from '../../api/tellusClient'
import { BoardPostCard } from '../../components/BoardPostCard'
import { Button, Card, Chip, Empty, ErrorText, Input, Select, Spinner, Textarea } from '../../components/ui'
import type {
  BoardJoinRequest, BoardManageReplyRow, BoardManageSummary, BoardMemberEntry,
  BoardPage, BoardPost, BoardPostKind, BrandTeamMember, Listing, ModeratedBrand,
} from '../../api/types'

function toErrorMessage(e: unknown, fallback: string): string {
  return e instanceof Error ? e.message : fallback
}

function SummarySection({ summary, onSave }: { summary: BoardManageSummary; onSave: (patch: Partial<BoardManageSummary>) => Promise<void> }) {
  const [title, setTitle] = useState(summary.title ?? '')
  const [description, setDescription] = useState(summary.description ?? '')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  async function save() {
    setSaving(true); setErr('')
    try { await onSave({ title: title || null, description: description || null }) }
    catch (e) { setErr(toErrorMessage(e, 'Could not save')) }
    finally { setSaving(false) }
  }

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-3 text-sm text-tu-dim">
        <Chip>{summary.pending_requests} pending requests</Chip>
        <Chip>{summary.held_replies} replies awaiting approval</Chip>
        <Chip>{summary.member_count} members</Chip>
        <label className="ml-auto flex items-center gap-1.5 text-xs">
          <input type="checkbox" checked={summary.is_active} onChange={(e) => void onSave({ is_active: e.target.checked })} />
          Board active
        </label>
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <Input label="Board title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder={`e.g. ${summary.title || 'Regulars'}`} />
        <div className="sm:col-span-2"><Textarea label="Description" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} /></div>
      </div>
      <ErrorText>{err}</ErrorText>
      <Button size="sm" variant="soft" className="mt-2" loading={saving} onClick={() => void save()}>Save</Button>
    </Card>
  )
}

function ComposeSection({ qs, isOwner, onPosted }: { qs: string; isOwner: boolean; onPosted: () => void }) {
  const [kind, setKind] = useState<BoardPostKind>('update')
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [listingId, setListingId] = useState('')
  const [boardListings, setBoardListings] = useState<Listing[] | null>(null)
  const [eventStart, setEventStart] = useState('')
  const [eventEnd, setEventEnd] = useState('')
  const [posting, setPosting] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    if (kind !== 'deal' || boardListings !== null) return
    // resolve_moderated_brand-gated, not require_paid_brand (GET /listings) —
    // a consumer-typed team moderator has no brand account, so /listings 403s.
    tellusApi.get<Listing[]>(`/board/manage/listings${qs}`).then(setBoardListings).catch(() => setBoardListings([]))
  }, [kind, boardListings, qs])

  async function submit(e: FormEvent) {
    e.preventDefault(); setErr(''); setPosting(true)
    try {
      await tellusApi.post(`/board/posts${qs}`, {
        kind, title, body: body || null,
        listing_id: kind === 'deal' ? (listingId || null) : null,
        event_starts_at: kind === 'event' && eventStart ? new Date(eventStart).toISOString() : null,
        event_ends_at: kind === 'event' && eventEnd ? new Date(eventEnd).toISOString() : null,
      })
      setTitle(''); setBody(''); setListingId(''); setEventStart(''); setEventEnd('')
      onPosted()
    } catch (e) {
      setErr(toErrorMessage(e, 'Could not post'))
    } finally {
      setPosting(false)
    }
  }

  return (
    <Card>
      <h2 className="text-sm font-semibold">Post to the board</h2>
      <form onSubmit={submit} className="mt-2 space-y-2.5">
        <div className="flex gap-2">
          <div className="w-40">
            <Select value={kind} onChange={(e) => setKind(e.target.value as BoardPostKind)} options={[
              { value: 'update', label: 'Update' }, { value: 'deal', label: 'Deal' },
              { value: 'event', label: 'Event' }, { value: 'question', label: 'Question' },
            ]} />
          </div>
          <div className="flex-1"><Input required value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title" /></div>
        </div>
        <Textarea rows={2} value={body} onChange={(e) => setBody(e.target.value)} placeholder="Details (optional)" />
        {kind === 'event' && (
          <div className="grid gap-2 sm:grid-cols-2">
            <Input label="Starts" type="datetime-local" value={eventStart} onChange={(e) => setEventStart(e.target.value)} />
            <Input label="Ends (optional)" type="datetime-local" value={eventEnd} onChange={(e) => setEventEnd(e.target.value)} />
          </div>
        )}
        {kind === 'deal' && (
          boardListings === null ? <Spinner /> : boardListings.length === 0 ? (
            <p className="text-xs text-tu-faint">
              {isOwner ? (
                <>No board-only rewards yet — <Link to="/brand/listings" className="font-semibold text-tu-accent hover:underline">create one on Listings</Link>.</>
              ) : (
                'No board-only rewards yet — ask the brand owner to create one.'
              )}
            </p>
          ) : (
            <Select required value={listingId} onChange={(e) => setListingId(e.target.value)} options={[
              { value: '', label: 'Pick a board-only reward…' },
              ...boardListings.map((l) => ({ value: l.id, label: `${l.title} (${l.points_cost} pts)` })),
            ]} />
          )
        )}
        <ErrorText>{err}</ErrorText>
        <Button type="submit" loading={posting} disabled={kind === 'deal' && !listingId}><Plus className="h-4 w-4" /> Post</Button>
      </form>
    </Card>
  )
}

function RequestsSection({ items, qs, onDecided }: { items: BoardJoinRequest[]; qs: string; onDecided: () => void }) {
  const [busyId, setBusyId] = useState<string | null>(null)
  const [err, setErr] = useState('')

  async function decide(id: string, action: 'approve' | 'decline') {
    setBusyId(id); setErr('')
    try { await tellusApi.post(`/board/manage/requests/${id}/${action}${qs}`); onDecided() }
    catch (e) { setErr(toErrorMessage(e, `Could not ${action}`)) }
    finally { setBusyId(null) }
  }

  return (
    <Card>
      <h2 className="text-sm font-semibold">Join requests</h2>
      <ErrorText>{err}</ErrorText>
      {items.length === 0 ? (
        <p className="mt-2 text-sm text-tu-faint">No pending requests.</p>
      ) : (
        <div className="mt-2 space-y-2">
          {items.map((r) => (
            <div key={r.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-tu-border px-3 py-2">
              <div>
                <p className="text-sm font-medium">{r.account_display_name}</p>
                <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-tu-faint">
                  <span className="inline-flex items-center gap-1"><Star className="h-3 w-3" /> {r.review_count} reviews</span>
                  {r.hearted && <span className="inline-flex items-center gap-1"><Heart className="h-3 w-3" /> hearted</span>}
                  <span>{r.redemption_count} redemptions</span>
                </div>
                {r.note && <p className="mt-1 text-xs text-tu-dim">"{r.note}"</p>}
              </div>
              <div className="flex gap-2">
                <Button size="sm" loading={busyId === r.id} onClick={() => void decide(r.id, 'approve')}>Approve</Button>
                <Button size="sm" variant="ghost" loading={busyId === r.id} onClick={() => void decide(r.id, 'decline')}>Decline</Button>
              </div>
            </div>
          ))}
        </div>
      )}
      <p className="mt-2 text-[11px] text-tu-faint">Signals reflect identified activity only — anonymous reviewers aren't counted.</p>
    </Card>
  )
}

function RepliesSection({ items, qs, onDecided }: { items: BoardManageReplyRow[]; qs: string; onDecided: () => void }) {
  const [busyId, setBusyId] = useState<string | null>(null)
  const [err, setErr] = useState('')

  async function decide(id: string, action: 'approve' | 'reject') {
    setBusyId(id); setErr('')
    try { await tellusApi.post(`/board/replies/${id}/${action}${qs}`); onDecided() }
    catch (e) { setErr(toErrorMessage(e, `Could not ${action}`)) }
    finally { setBusyId(null) }
  }

  return (
    <Card>
      <h2 className="text-sm font-semibold">Replies awaiting approval</h2>
      <ErrorText>{err}</ErrorText>
      {items.length === 0 ? (
        <p className="mt-2 text-sm text-tu-faint">Nothing held right now.</p>
      ) : (
        <div className="mt-2 space-y-2">
          {items.map((r) => (
            <div key={r.id} className="rounded-lg border border-tu-border px-3 py-2">
              <p className="text-xs text-tu-faint">{r.post_title} · {r.author_name}</p>
              <p className="mt-1 whitespace-pre-wrap text-sm">{r.body}</p>
              <div className="mt-2 flex gap-2">
                <Button size="sm" loading={busyId === r.id} onClick={() => void decide(r.id, 'approve')}>Approve</Button>
                <Button size="sm" variant="ghost" loading={busyId === r.id} onClick={() => void decide(r.id, 'reject')}>Reject</Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

function MembersSection({ items, qs, onRemoved }: { items: BoardMemberEntry[]; qs: string; onRemoved: () => void }) {
  const [busyId, setBusyId] = useState<string | null>(null)
  const [err, setErr] = useState('')

  async function remove(id: string) {
    if (!confirm('Remove this member from the board?')) return
    setBusyId(id); setErr('')
    try { await tellusApi.post(`/board/manage/members/${id}/remove${qs}`); onRemoved() }
    catch (e) { setErr(toErrorMessage(e, 'Could not remove member')) }
    finally { setBusyId(null) }
  }

  return (
    <Card>
      <h2 className="text-sm font-semibold">Members ({items.length})</h2>
      <ErrorText>{err}</ErrorText>
      {items.length === 0 ? (
        <p className="mt-2 text-sm text-tu-faint">No members yet.</p>
      ) : (
        <div className="mt-2 space-y-1.5">
          {items.map((m) => (
            <div key={m.id} className="flex items-center justify-between gap-2 text-sm">
              <span>{m.account_display_name}</span>
              <button disabled={busyId === m.id} onClick={() => void remove(m.id)} className="text-xs text-tu-bad hover:underline disabled:opacity-50">Remove</button>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

function TeamSection({
  items, isOwner, qs, onChanged,
}: { items: BrandTeamMember[]; isOwner: boolean; qs: string; onChanged: () => void }) {
  const [email, setEmail] = useState('')
  const [adding, setAdding] = useState(false)
  const [err, setErr] = useState('')

  async function add(e: FormEvent) {
    e.preventDefault(); setErr(''); setAdding(true)
    try { await tellusApi.post(`/board/team${qs}`, { email }); setEmail(''); onChanged() }
    catch (e) { setErr(toErrorMessage(e, 'Could not add team member')) }
    finally { setAdding(false) }
  }

  async function remove(id: string) {
    if (!confirm('Remove this moderator from your team?')) return
    setErr('')
    try { await tellusApi.delete(`/board/team/${id}${qs}`); onChanged() }
    catch (e) { setErr(toErrorMessage(e, 'Could not remove team member')) }
  }

  async function toggleInbox(id: string, enabled: boolean) {
    setErr('')
    try { await tellusApi.patch(`/comms/team/${id}/inbox`, { enabled }); onChanged() }
    catch (e) { setErr(toErrorMessage(e, 'Could not update Comms access')) }
  }

  return (
    <Card>
      <h2 className="text-sm font-semibold">Moderator team</h2>
      {isOwner && (
        <form onSubmit={add} className="mt-2 flex gap-2">
          <div className="flex-1"><Input required type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="teammate@example.com" /></div>
          <Button type="submit" loading={adding}><Plus className="h-4 w-4" /> Add</Button>
        </form>
      )}
      <ErrorText>{err}</ErrorText>
      <div className="mt-3 space-y-1.5">
        {items.map((m) => (
          <div key={m.id} className="flex items-center justify-between gap-2 text-sm">
            <span>{m.account_display_name} <span className="text-xs text-tu-faint">({m.email})</span></span>
            <div className="flex items-center gap-2">
              <Chip>{m.role}</Chip>
              {isOwner && m.role !== 'owner' && <label className="flex items-center gap-1 text-xs text-tu-dim"><input type="checkbox" checked={m.can_manage_inbox} onChange={e => void toggleInbox(m.id, e.target.checked)} /> Comms</label>}
              {isOwner && m.role !== 'owner' && <button onClick={() => void remove(m.id)} className="text-xs text-tu-bad hover:underline">Remove</button>}
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}

function toLocalInput(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function EditPostForm({ post, qs, onSaved, onCancel }: { post: BoardPost; qs: string; onSaved: () => void; onCancel: () => void }) {
  const [title, setTitle] = useState(post.title)
  const [body, setBody] = useState(post.body ?? '')
  const [isPinned, setIsPinned] = useState(post.is_pinned)
  const [eventStart, setEventStart] = useState(toLocalInput(post.event_starts_at))
  const [eventEnd, setEventEnd] = useState(toLocalInput(post.event_ends_at))
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  async function save() {
    setSaving(true); setErr('')
    try {
      await tellusApi.patch(`/board/posts/${post.id}${qs}`, {
        title, body: body || null, is_pinned: isPinned,
        ...(post.kind === 'event' ? {
          event_starts_at: eventStart ? new Date(eventStart).toISOString() : null,
          event_ends_at: eventEnd ? new Date(eventEnd).toISOString() : null,
        } : {}),
      })
      onSaved()
    } catch (e) {
      setErr(toErrorMessage(e, 'Could not save'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card className="border-tu-accent/40">
      <Input label="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
      <div className="mt-2"><Textarea label="Details" rows={2} value={body} onChange={(e) => setBody(e.target.value)} /></div>
      {post.kind === 'event' && (
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          <Input label="Starts" type="datetime-local" value={eventStart} onChange={(e) => setEventStart(e.target.value)} />
          <Input label="Ends (optional)" type="datetime-local" value={eventEnd} onChange={(e) => setEventEnd(e.target.value)} />
        </div>
      )}
      <label className="mt-2 flex items-center gap-1.5 text-xs">
        <input type="checkbox" checked={isPinned} onChange={(e) => setIsPinned(e.target.checked)} />
        Pinned
      </label>
      <ErrorText>{err}</ErrorText>
      <div className="mt-2 flex gap-2">
        <Button size="sm" loading={saving} onClick={() => void save()}>Save</Button>
        <Button size="sm" variant="ghost" onClick={onCancel}>Cancel</Button>
      </div>
    </Card>
  )
}

function PostsSection({ page, qs, onChanged }: { page: BoardPage; qs: string; onChanged: () => void }) {
  const [editingId, setEditingId] = useState<string | null>(null)
  const [err, setErr] = useState('')

  async function remove(postId: string) {
    setErr('')
    try { await tellusApi.delete(`/board/posts/${postId}${qs}`); onChanged() }
    catch (e) { setErr(toErrorMessage(e, 'Could not delete post')) }
  }

  return (
    <Card>
      <h2 className="text-sm font-semibold">
        Your posts ({page.posts.length}{page.posts.length < page.total ? ` of ${page.total}` : ''})
      </h2>
      <ErrorText>{err}</ErrorText>
      {page.posts.length === 0 ? (
        <p className="mt-2 text-sm text-tu-faint">Nothing posted yet — compose one above.</p>
      ) : (
        <div className="mt-2 space-y-2">
          {page.posts.map((p) => (
            editingId === p.id ? (
              <EditPostForm key={p.id} post={p} qs={qs} onSaved={() => { setEditingId(null); onChanged() }} onCancel={() => setEditingId(null)} />
            ) : (
              <div key={p.id} className="relative">
                <button
                  type="button" onClick={() => setEditingId(p.id)}
                  className="absolute right-3 top-3 z-10 text-tu-faint hover:text-tu-accent" title="Edit post"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </button>
                <BoardPostCard post={p} viewerRole={page.viewer_role} slug={page.brand_slug} brandId={page.brand_id} onRemove={remove} />
              </div>
            )
          ))}
        </div>
      )}
    </Card>
  )
}

export default function BrandBoard() {
  // Bootstrap: which brand does this account moderate? A real brand-typed
  // owner has exactly one; a consumer-typed team moderator (POST /board/team)
  // has no brand_id of its own, so this list is the only way to find their
  // board. Single-brand assumption per product decision — always take the
  // first entry, no picker, but still send brand_id explicitly on every call
  // below so a multi-board account never trips resolve_moderated_brand's
  // "Specify brand_id" 400.
  const [moderated, setModerated] = useState<ModeratedBrand | null>(null)
  const [boardPage, setBoardPage] = useState<BoardPage | null>(null)
  const [summary, setSummary] = useState<BoardManageSummary | null>(null)
  const [requests, setRequests] = useState<BoardJoinRequest[]>([])
  const [replies, setReplies] = useState<BoardManageReplyRow[]>([])
  const [members, setMembers] = useState<BoardMemberEntry[]>([])
  const [team, setTeam] = useState<BrandTeamMember[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')

  // Scoped loaders — each action refetches only the section(s) it can have
  // changed, instead of a blanket loadAll (was 6 endpoints on every checkbox
  // toggle or approve/decline click). Mount still uses loadAll for the
  // initial fetch.
  function loadSummary(brand: ModeratedBrand) {
    return tellusApi.get<BoardManageSummary>(`/board/manage?brand_id=${brand.brand_id}`).then(setSummary)
  }
  function loadRequests(brand: ModeratedBrand) {
    return tellusApi.get<BoardJoinRequest[]>(`/board/manage/requests?brand_id=${brand.brand_id}`).then(setRequests)
  }
  function loadReplies(brand: ModeratedBrand) {
    return tellusApi.get<BoardManageReplyRow[]>(`/board/manage/replies?status=held&brand_id=${brand.brand_id}`).then(setReplies)
  }
  function loadMembers(brand: ModeratedBrand) {
    return tellusApi.get<BoardMemberEntry[]>(`/board/manage/members?brand_id=${brand.brand_id}`).then(setMembers)
  }
  function loadTeam(brand: ModeratedBrand) {
    return tellusApi.get<BrandTeamMember[]>(`/board/team?brand_id=${brand.brand_id}`).then(setTeam)
  }
  function loadPage(brand: ModeratedBrand) {
    return tellusApi.get<BoardPage>(`/boards/${brand.slug}?limit=50`).then(setBoardPage)
  }

  async function loadAll(brand: ModeratedBrand) {
    try {
      await Promise.all([
        loadSummary(brand), loadRequests(brand), loadReplies(brand),
        loadMembers(brand), loadTeam(brand), loadPage(brand),
      ])
    } catch (e) {
      setErr(toErrorMessage(e, 'Failed to load your regulars board'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    (async () => {
      try {
        const brands = await tellusApi.get<ModeratedBrand[]>('/me/moderated-brands')
        if (brands.length === 0) {
          setErr('Not a moderator of any regulars board'); setLoading(false); return
        }
        setModerated(brands[0])
        await loadAll(brands[0])
      } catch (e) {
        setErr(toErrorMessage(e, 'Failed to load your regulars board')); setLoading(false)
      }
    })()
  }, [])

  if (loading) return <Spinner />
  if (err || !summary || !moderated || !boardPage) return <ErrorText>{err}</ErrorText>

  const qs = `?brand_id=${moderated.brand_id}`
  const isOwner = summary.viewer_role === 'owner'

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold">Regulars board</h1>
      {!summary.is_active && (
        <Card className="border-tu-accent/40 bg-tu-accent/5">
          <p className="text-sm text-tu-dim">Your board isn't visible yet — check "Board active" below to publish it on your brand page.</p>
        </Card>
      )}
      <SummarySection
        summary={summary}
        onSave={async (patch) => { setSummary(await tellusApi.patch(`/board/manage${qs}`, patch)) }}
      />
      <ComposeSection qs={qs} isOwner={isOwner} onPosted={() => void Promise.all([loadPage(moderated), loadSummary(moderated)])} />
      <PostsSection page={boardPage} qs={qs} onChanged={() => void Promise.all([loadPage(moderated), loadSummary(moderated)])} />
      <RequestsSection
        items={requests} qs={qs}
        onDecided={() => void Promise.all([loadRequests(moderated), loadMembers(moderated), loadSummary(moderated)])}
      />
      <RepliesSection items={replies} qs={qs} onDecided={() => void Promise.all([loadReplies(moderated), loadSummary(moderated)])} />
      <MembersSection items={members} qs={qs} onRemoved={() => void Promise.all([loadMembers(moderated), loadSummary(moderated)])} />
      <TeamSection items={team} isOwner={isOwner} qs={qs} onChanged={() => void loadTeam(moderated)} />
      {members.length === 0 && requests.length === 0 && <Empty>Share your brand page to start building your regulars.</Empty>}
    </div>
  )
}
