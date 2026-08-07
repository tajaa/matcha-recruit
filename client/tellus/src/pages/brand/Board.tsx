import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Heart, Plus, Star } from 'lucide-react'
import { tellusApi } from '../../api/tellusClient'
import { Button, Card, Chip, Empty, ErrorText, Input, Select, Spinner, Textarea } from '../../components/ui'
import type {
  BoardJoinRequest, BoardManageReplyRow, BoardManageSummary, BoardMemberEntry,
  BoardPostKind, BrandTeamMember, Listing,
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

function ComposeSection({ onPosted }: { onPosted: () => void }) {
  const [kind, setKind] = useState<BoardPostKind>('update')
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [listingId, setListingId] = useState('')
  const [boardListings, setBoardListings] = useState<Listing[] | null>(null)
  const [posting, setPosting] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    if (kind !== 'deal' || boardListings !== null) return
    tellusApi.get<Listing[]>('/listings').then((all) => setBoardListings(all.filter((l) => l.visibility === 'board'))).catch(() => setBoardListings([]))
  }, [kind, boardListings])

  async function submit(e: FormEvent) {
    e.preventDefault(); setErr(''); setPosting(true)
    try {
      await tellusApi.post('/board/posts', {
        kind, title, body: body || null,
        listing_id: kind === 'deal' ? (listingId || null) : null,
      })
      setTitle(''); setBody(''); setListingId('')
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
        {kind === 'deal' && (
          boardListings === null ? <Spinner /> : boardListings.length === 0 ? (
            <p className="text-xs text-tu-faint">
              No board-only rewards yet — <Link to="/brand/listings" className="font-semibold text-tu-accent hover:underline">create one on Listings</Link>.
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

function RequestsSection({ items, onDecided }: { items: BoardJoinRequest[]; onDecided: () => void }) {
  const [busyId, setBusyId] = useState<string | null>(null)
  const [err, setErr] = useState('')

  async function decide(id: string, action: 'approve' | 'decline') {
    setBusyId(id); setErr('')
    try { await tellusApi.post(`/board/manage/requests/${id}/${action}`); onDecided() }
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

function RepliesSection({ items, onDecided }: { items: BoardManageReplyRow[]; onDecided: () => void }) {
  const [busyId, setBusyId] = useState<string | null>(null)
  const [err, setErr] = useState('')

  async function decide(id: string, action: 'approve' | 'reject') {
    setBusyId(id); setErr('')
    try { await tellusApi.post(`/board/replies/${id}/${action}`); onDecided() }
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

function MembersSection({ items, onRemoved }: { items: BoardMemberEntry[]; onRemoved: () => void }) {
  const [busyId, setBusyId] = useState<string | null>(null)

  async function remove(id: string) {
    if (!confirm('Remove this member from the board?')) return
    setBusyId(id)
    try { await tellusApi.post(`/board/manage/members/${id}/remove`); onRemoved() }
    finally { setBusyId(null) }
  }

  return (
    <Card>
      <h2 className="text-sm font-semibold">Members ({items.length})</h2>
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

function TeamSection({ items, onChanged }: { items: BrandTeamMember[]; onChanged: () => void }) {
  const [email, setEmail] = useState('')
  const [adding, setAdding] = useState(false)
  const [err, setErr] = useState('')

  async function add(e: FormEvent) {
    e.preventDefault(); setErr(''); setAdding(true)
    try { await tellusApi.post('/board/team', { email }); setEmail(''); onChanged() }
    catch (e) { setErr(toErrorMessage(e, 'Could not add team member')) }
    finally { setAdding(false) }
  }

  async function remove(id: string) {
    if (!confirm('Remove this moderator from your team?')) return
    await tellusApi.delete(`/board/team/${id}`); onChanged()
  }

  return (
    <Card>
      <h2 className="text-sm font-semibold">Moderator team</h2>
      <form onSubmit={add} className="mt-2 flex gap-2">
        <div className="flex-1"><Input required type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="teammate@example.com" /></div>
        <Button type="submit" loading={adding}><Plus className="h-4 w-4" /> Add</Button>
      </form>
      <ErrorText>{err}</ErrorText>
      <div className="mt-3 space-y-1.5">
        {items.map((m) => (
          <div key={m.id} className="flex items-center justify-between gap-2 text-sm">
            <span>{m.account_display_name} <span className="text-xs text-tu-faint">({m.email})</span></span>
            <div className="flex items-center gap-2">
              <Chip>{m.role}</Chip>
              {m.role !== 'owner' && <button onClick={() => void remove(m.id)} className="text-xs text-tu-bad hover:underline">Remove</button>}
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}

export default function BrandBoard() {
  const [summary, setSummary] = useState<BoardManageSummary | null>(null)
  const [requests, setRequests] = useState<BoardJoinRequest[]>([])
  const [replies, setReplies] = useState<BoardManageReplyRow[]>([])
  const [members, setMembers] = useState<BoardMemberEntry[]>([])
  const [team, setTeam] = useState<BrandTeamMember[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')

  async function loadAll() {
    try {
      const [s, r, rep, m, t] = await Promise.all([
        tellusApi.get<BoardManageSummary>('/board/manage'),
        tellusApi.get<BoardJoinRequest[]>('/board/manage/requests'),
        tellusApi.get<BoardManageReplyRow[]>('/board/manage/replies?status=held'),
        tellusApi.get<BoardMemberEntry[]>('/board/manage/members'),
        tellusApi.get<BrandTeamMember[]>('/board/team'),
      ])
      setSummary(s); setRequests(r); setReplies(rep); setMembers(m); setTeam(t)
    } catch (e) {
      setErr(toErrorMessage(e, 'Failed to load your regulars board'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void loadAll() }, [])

  if (loading) return <Spinner />
  if (err || !summary) return <ErrorText>{err}</ErrorText>

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold">Regulars board</h1>
      <SummarySection summary={summary} onSave={async (patch) => { setSummary(await tellusApi.patch('/board/manage', patch)) }} />
      <ComposeSection onPosted={loadAll} />
      <RequestsSection items={requests} onDecided={loadAll} />
      <RepliesSection items={replies} onDecided={loadAll} />
      <MembersSection items={members} onRemoved={loadAll} />
      <TeamSection items={team} onChanged={loadAll} />
      {members.length === 0 && requests.length === 0 && <Empty>Share your brand page to start building your regulars.</Empty>}
    </div>
  )
}
