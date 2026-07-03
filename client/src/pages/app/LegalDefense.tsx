import { useEffect, useRef, useState } from 'react'
import {
  Scale, Plus, Send, FileText, FileArchive, Share2, Loader2, ShieldAlert, X, Download, ChevronDown,
} from 'lucide-react'
import { Card, Button, Input, Textarea, Select, Toggle, Badge, Modal, useToast } from '../../components/ui'
import {
  listMatters, createMatter, getMatter, getEvidence, generatePacket, downloadPacket,
  sharePacket, streamChat,
  type Matter, type MatterType, type MatterMessage, type EvidencePreview, type Packet,
  type ChatResult,
} from '../../api/legalDefense'

const MATTER_TYPES: { value: MatterType; label: string }[] = [
  { value: 'class_action', label: 'Class action' },
  { value: 'single_plaintiff', label: 'Single-plaintiff suit' },
  { value: 'eeoc_charge', label: 'EEOC / agency charge' },
  { value: 'subpoena', label: 'Subpoena' },
  { value: 'audit', label: 'Regulator audit' },
  { value: 'other', label: 'Other' },
]
const typeLabel = (t: MatterType) => MATTER_TYPES.find((m) => m.value === t)?.label ?? t

const DISCLAIMER =
  'This organizes your own records to help your attorney — it is an evidence-assembly aid, not legal advice, and renders no legal conclusion. Have counsel review before relying on it.'

export default function LegalDefense() {
  const { toast } = useToast()
  const [matters, setMatters] = useState<Matter[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [matter, setMatter] = useState<Matter | null>(null)
  const [evidence, setEvidence] = useState<EvidencePreview | null>(null)
  const [loading, setLoading] = useState(true)
  const [showNew, setShowNew] = useState(false)

  useEffect(() => {
    listMatters().then((m) => { setMatters(m); setLoading(false) }).catch(() => setLoading(false))
  }, [])

  async function openMatter(id: string) {
    setSelectedId(id)
    setMatter(null)
    setEvidence(null)
    const [m, ev] = await Promise.all([getMatter(id), getEvidence(id).catch(() => null)])
    setMatter(m)
    setEvidence(ev)
  }

  async function onCreated(m: Matter) {
    setShowNew(false)
    setMatters((prev) => [m, ...prev])
    void openMatter(m.id)
  }

  return (
    <div className="flex h-[calc(100vh-4rem)] gap-4">
      {/* Matters list */}
      <div className="w-72 shrink-0 flex flex-col">
        <div className="flex items-center justify-between mb-3">
          <h1 className="flex items-center gap-2 text-lg font-semibold text-zinc-100">
            <Scale className="h-5 w-5 text-emerald-400" /> Legal Pilot
          </h1>
          <Button size="sm" onClick={() => setShowNew(true)}><Plus className="h-4 w-4" /></Button>
        </div>
        <div className="flex-1 overflow-y-auto space-y-1.5 pr-1">
          {loading ? (
            <p className="text-sm text-zinc-500">Loading…</p>
          ) : matters.length === 0 ? (
            <p className="text-sm text-zinc-500">No matters yet. Open one when a legal request arrives.</p>
          ) : matters.map((m) => (
            <button key={m.id} onClick={() => openMatter(m.id)}
              className={`w-full text-left rounded-lg border px-3 py-2 transition-colors ${
                selectedId === m.id ? 'border-emerald-500/40 bg-emerald-500/[0.08]' : 'border-white/[0.06] hover:bg-zinc-800/40'}`}>
              <div className="text-sm font-medium text-zinc-100 truncate">{m.title}</div>
              <div className="mt-0.5 flex items-center gap-2 text-[11px] text-zinc-500">
                <span>{typeLabel(m.matter_type)}</span>
                <Badge variant={m.status === 'closed' ? 'neutral' : 'success'}>{m.status}</Badge>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Detail */}
      <div className="flex-1 min-w-0">
        {!selectedId ? (
          <Card><div className="p-8 text-center text-sm text-zinc-500">
            <Scale className="mx-auto mb-3 h-8 w-8 text-zinc-600" />
            Select or create a matter. Describe the legal request; the assistant organizes your
            records (incidents, ER, compliance, discipline, training, policies) into a packet for your attorney.
          </div></Card>
        ) : !matter ? (
          <div className="flex h-full items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-zinc-500" /></div>
        ) : (
          <MatterDetail matter={matter} evidence={evidence} onRefresh={() => openMatter(matter.id)} toast={toast} />
        )}
      </div>

      {showNew && <NewMatterModal onClose={() => setShowNew(false)} onCreated={onCreated} />}
    </div>
  )
}

function MatterDetail({ matter, evidence, onRefresh, toast }: {
  matter: Matter; evidence: EvidencePreview | null; onRefresh: () => void
  toast: ReturnType<typeof useToast>['toast']
}) {
  const [messages, setMessages] = useState<MatterMessage[]>(matter.messages ?? [])
  const [input, setInput] = useState('')
  const [status, setStatus] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const [genKind, setGenKind] = useState<'pdf' | 'zip' | 'both' | null>(null)
  const [shareFor, setShareFor] = useState<Packet | null>(null)
  const [showOlderPackets, setShowOlderPackets] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => { setMessages(matter.messages ?? []) }, [matter.id, matter.messages])
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, status])

  async function send() {
    const text = input.trim()
    if (!text || sending) return
    setInput('')
    setSending(true)
    setStatus('Organizing your records…')
    const now = new Date().toISOString()
    setMessages((prev) => [...prev, { role: 'user', content: text, metadata: null, created_at: now }])
    await streamChat(matter.id, text, {
      onStatus: (m) => setStatus(m),
      onResult: (data: ChatResult) => {
        setMessages((prev) => [...prev, {
          role: 'assistant', content: data.assistant_text, created_at: new Date().toISOString(),
          metadata: { evidence_map: data.evidence_map, open_questions: data.open_questions, dropped_citations: data.dropped_citations },
        }])
      },
      onError: (m) => toast(m, 'error'),
    })
    setStatus(null)
    setSending(false)
  }

  async function generate(kind: 'pdf' | 'zip' | 'both') {
    setGenKind(kind)
    try {
      const { packets } = await generatePacket(matter.id, kind)
      toast(`Generated ${packets.length} file(s) — downloading…`, 'success')
      onRefresh()
      // Generating doesn't imply the user will hunt for the new row in the
      // side panel — deliver what they asked for immediately.
      for (const p of packets) {
        await downloadPacket(matter.id, p).catch((e) =>
          toast(e instanceof Error ? e.message : `Download failed for ${p.filename}`, 'error'))
      }
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Generation failed', 'error')
    } finally {
      setGenKind(null)
    }
  }

  const hasAssistant = messages.some((m) => m.role === 'assistant')

  // Packets are already ordered newest-first by the backend. Regenerating
  // creates a new row each time (old share links must keep working — see
  // downloadPacket/sharePacket), so a matter worked on over several sessions
  // accumulates a long tail. Surface only the latest PDF/ZIP; older ones are
  // one click away instead of cluttering the panel by default.
  const packets = matter.packets ?? []
  const latestPackets: Packet[] = []
  const seenKinds = new Set<string>()
  for (const p of packets) {
    if (!seenKinds.has(p.kind)) { seenKinds.add(p.kind); latestPackets.push(p) }
  }
  const latestIds = new Set(latestPackets.map((p) => p.id))
  const olderPackets = packets.filter((p) => !latestIds.has(p.id))

  return (
    <div className="flex h-full gap-4">
      <div className="flex-1 min-w-0 flex flex-col">
        {/* Header */}
        <div className="mb-3">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-zinc-100 truncate">{matter.title}</h2>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="secondary" disabled={!hasAssistant || genKind !== null} onClick={() => generate('pdf')}>
                {genKind === 'pdf' ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />} Memo PDF
              </Button>
              <Button size="sm" variant="secondary" disabled={!hasAssistant || genKind !== null} onClick={() => generate('both')}>
                {genKind === 'both' ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileArchive className="h-4 w-4" />} PDF + ZIP
              </Button>
            </div>
          </div>
          <div className="mt-1 flex items-center gap-2 text-xs text-zinc-500">
            <span>{typeLabel(matter.matter_type)}</span>
            {matter.counsel_directed && <Badge variant="success">At counsel's direction</Badge>}
            {(matter.evidence_start || matter.evidence_end) && (
              <span>· {matter.evidence_start ?? '…'} – {matter.evidence_end ?? '…'}</span>
            )}
          </div>
        </div>

        <div className="mb-3 flex items-start gap-2 rounded-lg border border-amber-500/20 bg-amber-500/[0.06] px-3 py-2">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
          <p className="text-[11px] leading-relaxed text-amber-200/80">{DISCLAIMER}</p>
        </div>

        {/* Chat */}
        <div className="flex-1 overflow-y-auto rounded-xl border border-white/[0.06] bg-zinc-900/30 p-4 space-y-4">
          {messages.length === 0 && (
            <p className="text-sm text-zinc-500">
              Describe what's being claimed and the timeframe. Example: “We were served a class action
              alleging we ignored repeated safety complaints at our Dallas site in 2025.”
            </p>
          )}
          {messages.map((m, i) => <MessageBubble key={i} m={m} />)}
          {status && (
            <div className="flex items-center gap-2 text-sm text-zinc-400">
              <Loader2 className="h-4 w-4 animate-spin text-emerald-400" /> {status}
            </div>
          )}
          <div ref={endRef} />
        </div>

        {/* Composer */}
        <div className="mt-3 flex items-end gap-2">
          <Textarea label="" value={input} onChange={(e) => setInput(e.target.value)} rows={2}
            placeholder="Describe the matter or ask what the records show…"
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); void send() } }}
            className="flex-1" />
          <Button onClick={() => void send()} disabled={sending || !input.trim()}>
            {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      {/* Side panel: evidence in scope + packet history */}
      <div className="w-72 shrink-0 overflow-y-auto space-y-4">
        <Card>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">
            Records in scope {evidence ? `(${evidence.total})` : ''}
          </div>
          {!evidence ? <p className="text-sm text-zinc-500">Loading…</p> : evidence.total === 0 ? (
            <p className="text-sm text-zinc-500">No records found in the matter's date range.</p>
          ) : (
            <div className="space-y-2">
              {Object.entries(evidence.sources).map(([key, s]) => (
                <div key={key} className="flex items-center justify-between text-sm">
                  <span className="text-zinc-300">{s.label}</span>
                  <Badge variant="neutral">{s.records.length}</Badge>
                </div>
              ))}
              {evidence.notes.map((n, i) => <p key={i} className="text-[11px] text-zinc-500">{n}</p>)}
            </div>
          )}
        </Card>

        {packets.length > 0 && (
          <Card>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">Packets</div>
            <div className="space-y-2">
              {latestPackets.map((p) => (
                <PacketRow key={p.id} matterId={matter.id} packet={p} toast={toast} onShare={() => setShareFor(p)} />
              ))}
            </div>
            {olderPackets.length > 0 && (
              <div className="mt-2">
                <button
                  className="flex w-full items-center gap-1 text-[11px] text-zinc-500 hover:text-zinc-300"
                  onClick={() => setShowOlderPackets((v) => !v)}
                >
                  <ChevronDown className={`h-3 w-3 transition-transform ${showOlderPackets ? 'rotate-180' : ''}`} />
                  {showOlderPackets ? 'Hide' : `${olderPackets.length} earlier version${olderPackets.length === 1 ? '' : 's'}`}
                </button>
                {showOlderPackets && (
                  <div className="mt-2 space-y-2 opacity-70">
                    {olderPackets.map((p) => (
                      <PacketRow key={p.id} matterId={matter.id} packet={p} toast={toast} onShare={() => setShareFor(p)} />
                    ))}
                  </div>
                )}
              </div>
            )}
          </Card>
        )}
      </div>

      {shareFor && <ShareModal matterId={matter.id} packet={shareFor} onClose={() => setShareFor(null)} toast={toast} />}
    </div>
  )
}

function shareStatusText(share: Packet['share']): string | null {
  if (!share) return null
  if (share.revoked) return 'Link revoked'
  if (share.expires_at && new Date(share.expires_at) < new Date()) return 'Link expired'
  const who = share.recipient_email ? ` with ${share.recipient_email}` : ''
  if (share.download_count === 0) return `Shared${who} — not yet opened`
  const last = share.last_downloaded_at ? new Date(share.last_downloaded_at).toLocaleDateString() : null
  return `Shared${who} — opened ${share.download_count}×${last ? ` (last ${last})` : ''}`
}

function PacketRow({ matterId, packet, toast, onShare }: {
  matterId: string; packet: Packet; onShare: () => void
  toast: ReturnType<typeof useToast>['toast']
}) {
  const shareText = shareStatusText(packet.share)
  return (
    <div className="rounded-lg border border-white/[0.06] px-2.5 py-2">
      <div className="flex items-center gap-2 text-sm text-zinc-200">
        {packet.kind === 'zip' ? <FileArchive className="h-4 w-4 text-zinc-400" /> : <FileText className="h-4 w-4 text-zinc-400" />}
        <span className="uppercase">{packet.kind}</span>
        <span className="ml-auto text-[11px] text-zinc-500">{new Date(packet.generated_at).toLocaleDateString()}</span>
      </div>
      <div className="mt-1.5 flex gap-1.5">
        <Button size="sm" variant="secondary" onClick={() => void downloadPacket(matterId, packet).catch((e) =>
          toast(e instanceof Error ? e.message : 'Download failed', 'error'))}>
          <Download className="h-3.5 w-3.5" /> Download
        </Button>
        <Button size="sm" variant="secondary" onClick={onShare}>
          <Share2 className="h-3.5 w-3.5" /> Send to counsel
        </Button>
      </div>
      {shareText && <div className="mt-1.5 text-[11px] text-zinc-500">{shareText}</div>}
    </div>
  )
}

function MessageBubble({ m }: { m: MatterMessage }) {
  const isUser = m.role === 'user'
  const meta = m.metadata
  return (
    <div className={isUser ? 'flex justify-end' : 'flex justify-start'}>
      <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm ${
        isUser ? 'bg-emerald-600/20 text-zinc-100' : 'bg-zinc-800/60 text-zinc-200'}`}>
        <p className="whitespace-pre-wrap">{m.content}</p>
        {!isUser && meta?.evidence_map && meta.evidence_map.length > 0 && (
          <div className="mt-3 space-y-1.5 border-t border-white/[0.08] pt-2">
            {meta.evidence_map.map((it, i) => (
              <div key={i} className="text-[12px]">
                <span className="text-zinc-300">{it.point}</span>
                {it.cited_ids.length > 0 && (
                  <span className="ml-1 text-zinc-500">[{it.cited_ids.join(', ')}]</span>
                )}
              </div>
            ))}
          </div>
        )}
        {!isUser && meta?.open_questions && meta.open_questions.length > 0 && (
          <div className="mt-2 border-t border-white/[0.08] pt-2">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-amber-400/80">Open questions for counsel</div>
            <ul className="mt-1 list-disc pl-4 text-[12px] text-zinc-400">
              {meta.open_questions.map((q, i) => <li key={i}>{q}</li>)}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}

function NewMatterModal({ onClose, onCreated }: { onClose: () => void; onCreated: (m: Matter) => void }) {
  const [title, setTitle] = useState('')
  const [type, setType] = useState<MatterType>('class_action')
  const [allegation, setAllegation] = useState('')
  const [context, setContext] = useState('')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [counsel, setCounsel] = useState(false)
  const [counselName, setCounselName] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function submit() {
    if (!title.trim()) { setErr('Give the matter a title.'); return }
    setSaving(true); setErr(null)
    try {
      const m = await createMatter({
        title: title.trim(), matter_type: type,
        allegation: allegation.trim() || null, defense_theory: context.trim() || null,
        evidence_start: start || null, evidence_end: end || null,
        counsel_directed: counsel, counsel_name: counsel ? (counselName.trim() || null) : null,
      })
      onCreated(m)
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to create matter')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal open onClose={onClose} title="New legal matter">
      <div className="space-y-3">
        <Input label="Title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Doe v. Acme — class action" />
        <Select label="Type" value={type} options={MATTER_TYPES}
          onChange={(e) => setType(e.target.value as MatterType)} />
        <Textarea label="What's being alleged?" value={allegation} onChange={(e) => setAllegation(e.target.value)} rows={2}
          placeholder="The claim as you understand it." />
        <Textarea label="Factual context (optional)" value={context} onChange={(e) => setContext(e.target.value)} rows={2}
          placeholder="What you believe the records show. The assistant stays neutral — counsel draws conclusions." />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Evidence from" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
          <Input label="Evidence to" type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
        </div>
        <div className="flex items-center justify-between rounded-lg border border-white/[0.06] px-3 py-2">
          <div>
            <div className="text-sm text-zinc-200">Prepared at the direction of counsel</div>
            <div className="text-[11px] text-zinc-500">Adds a work-product header to the packet.</div>
          </div>
          <Toggle checked={counsel} onChange={setCounsel} />
        </div>
        {counsel && (
          <Input label="Counsel name" value={counselName} onChange={(e) => setCounselName(e.target.value)} placeholder="Firm or attorney" />
        )}
        {err && <p className="text-sm text-red-400">{err}</p>}
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={() => void submit()} disabled={saving}>{saving ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Create'}</Button>
        </div>
      </div>
    </Modal>
  )
}

function ShareModal({ matterId, packet, onClose, toast }: {
  matterId: string; packet: Packet; onClose: () => void; toast: ReturnType<typeof useToast>['toast']
}) {
  const [email, setEmail] = useState('')
  const [days, setDays] = useState(14)
  const [link, setLink] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function create() {
    setBusy(true)
    try {
      const res = await sharePacket(matterId, packet.id, { recipient_email: email.trim() || undefined, expires_days: days })
      setLink(`${window.location.origin}${res.path}`)
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to create link', 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open onClose={onClose} title="Send packet to counsel">
      <div className="space-y-3">
        <p className="text-sm text-zinc-400">
          Creates a private, expiring download link for your attorney — no Matcha login required.
        </p>
        <Input label="Recipient email (optional, for your records)" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="attorney@firm.example" />
        <Input label="Link expires in (days)" type="number" value={String(days)} onChange={(e) => setDays(Math.max(1, Number(e.target.value) || 14))} />
        {link ? (
          <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/[0.06] p-3">
            <div className="text-[11px] uppercase tracking-wide text-emerald-400/80">Share link</div>
            <div className="mt-1 flex items-center gap-2">
              <code className="flex-1 truncate text-xs text-zinc-200">{link}</code>
              <Button size="sm" variant="secondary" onClick={() => { void navigator.clipboard.writeText(link); toast('Copied', 'success') }}>Copy</Button>
            </div>
          </div>
        ) : (
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={onClose}><X className="h-4 w-4" /> Close</Button>
            <Button onClick={() => void create()} disabled={busy}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Create link'}</Button>
          </div>
        )}
      </div>
    </Modal>
  )
}
