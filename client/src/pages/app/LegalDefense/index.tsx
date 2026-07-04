import { useEffect, useRef, useState } from 'react'
import { Loader2, Plus, Scale } from 'lucide-react'
import { Button, useToast } from '../../../components/ui'
import {
  listMatters, getMatter, getEvidence, generatePacket, downloadPacket, streamChat,
  runResearch, listResearch,
  type Matter, type MatterMessage, type EvidencePreview, type Packet, type ChatResult, type ResearchRow,
} from '../../../api/legalDefense'
import { LABEL, typeLabel } from './shared'
import { Masthead } from './Masthead'
import { Console } from './Console'
import { EvidencePanel } from './EvidencePanel'
import { LegalContextPanel } from './LegalContextPanel'
import { PacketsPanel } from './PacketsPanel'
import { NewMatterModal, ShareModal } from './modals'

export default function LegalDefense() {
  const { toast } = useToast()
  const [matters, setMatters] = useState<Matter[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [matter, setMatter] = useState<Matter | null>(null)
  const [evidence, setEvidence] = useState<EvidencePreview | null>(null)
  const [research, setResearch] = useState<ResearchRow | null>(null)
  const [researching, setResearching] = useState(false)
  const [loading, setLoading] = useState(true)
  const [showNew, setShowNew] = useState(false)
  // Which matter the async state below belongs to. Fetches and the ~2-minute
  // research call resolve long after the user may have switched matters —
  // every awaited setState checks this ref so a slow response for matter A
  // can never clobber matter B's view.
  const activeIdRef = useRef<string | null>(null)

  useEffect(() => {
    listMatters().then((m) => { setMatters(m); setLoading(false) }).catch(() => setLoading(false))
  }, [])

  async function openMatter(id: string) {
    activeIdRef.current = id
    setSelectedId(id)
    setMatter(null)
    setEvidence(null)
    setResearch(null)
    setResearching(false)
    const [m, ev, researchRows] = await Promise.all([
      getMatter(id), getEvidence(id).catch(() => null), listResearch(id).catch(() => []),
    ])
    if (activeIdRef.current !== id) return
    setMatter(m)
    setEvidence(ev)
    setResearch(researchRows[0] ?? null)
  }

  async function handleRunResearch(includeGuidance = true) {
    const id = selectedId
    if (!id || researching) return
    setResearching(true)
    try {
      const row = await runResearch(id, includeGuidance)
      if (activeIdRef.current === id) setResearch(row)
    } catch (e) {
      if (activeIdRef.current === id) toast(e instanceof Error ? e.message : 'Research failed', 'error')
    } finally {
      if (activeIdRef.current === id) setResearching(false)
    }
  }

  async function onCreated(m: Matter) {
    setShowNew(false)
    setMatters((prev) => [m, ...prev])
    void openMatter(m.id)
  }

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden rounded-xl border border-white/[0.06] bg-zinc-950">
      {/* Matters rail */}
      <div className="flex w-60 shrink-0 flex-col border-r border-white/[0.06]">
        <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3">
          <h1 className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
            <Scale className="h-4 w-4 text-emerald-400" /> Legal Pilot
          </h1>
          <button
            onClick={() => setShowNew(true)}
            aria-label="New matter"
            className="rounded p-1 text-zinc-400 transition-colors hover:bg-white/[0.04] hover:text-zinc-100"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>
        <div className={`border-b border-white/[0.06] px-4 py-2 ${LABEL}`}>Matters</div>
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <p className="px-4 py-3 text-xs text-zinc-600">Loading…</p>
          ) : matters.length === 0 ? (
            <p className="px-4 py-3 text-xs text-zinc-500">No matters yet. Open one when a legal request arrives.</p>
          ) : matters.map((m) => (
            <button key={m.id} onClick={() => openMatter(m.id)}
              className={`block w-full border-b border-white/[0.04] border-l-2 px-4 py-2.5 text-left transition-colors ${
                selectedId === m.id
                  ? 'border-l-emerald-400 bg-white/[0.03]'
                  : 'border-l-transparent hover:bg-white/[0.02]'}`}>
              <div className="truncate text-[13px] font-medium text-zinc-100">{m.title}</div>
              <div className="mt-0.5 flex items-center gap-2 font-mono text-[10px] uppercase tracking-wide text-zinc-500">
                <span className="truncate">{typeLabel(m.matter_type)}</span>
                <span className={m.status === 'closed' ? 'text-zinc-600' : 'text-emerald-400/90'}>{m.status}</span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Workbench */}
      <div className="min-w-0 flex-1">
        {!selectedId ? (
          <div className="flex h-full flex-col items-center justify-center gap-4 px-8 text-center">
            <Scale className="h-8 w-8 text-zinc-700" />
            <p className="max-w-md text-sm leading-relaxed text-zinc-500">
              Select or create a matter. Describe the legal request; the assistant organizes your
              records — incidents, ER, compliance, discipline, training, policies — into a packet for your attorney.
            </p>
            <Button size="sm" onClick={() => setShowNew(true)}><Plus className="h-4 w-4" /> New matter</Button>
          </div>
        ) : !matter ? (
          <div className="flex h-full items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-zinc-500" />
          </div>
        ) : (
          <MatterWorkbench
            matter={matter} evidence={evidence} research={research} researching={researching}
            onRunResearch={handleRunResearch} onRefresh={() => openMatter(matter.id)} toast={toast}
          />
        )}
      </div>

      {showNew && <NewMatterModal onClose={() => setShowNew(false)} onCreated={onCreated} />}
    </div>
  )
}

function MatterWorkbench({ matter, evidence, research, researching, onRunResearch, onRefresh, toast }: {
  matter: Matter; evidence: EvidencePreview | null; research: ResearchRow | null; researching: boolean
  onRunResearch: (includeGuidance?: boolean) => void; onRefresh: () => void
  toast: ReturnType<typeof useToast>['toast']
}) {
  const [messages, setMessages] = useState<MatterMessage[]>(matter.messages ?? [])
  const [status, setStatus] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const [genKind, setGenKind] = useState<'pdf' | 'zip' | 'both' | null>(null)
  const [shareFor, setShareFor] = useState<Packet | null>(null)

  useEffect(() => { setMessages(matter.messages ?? []) }, [matter.id, matter.messages])

  async function send(text: string) {
    if (sending) return
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

  async function generate(kind: 'pdf' | 'both', includeResearch: boolean) {
    setGenKind(kind)
    try {
      const { packets } = await generatePacket(matter.id, kind, includeResearch)
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

  return (
    <div className="flex h-full min-h-0 flex-col">
      <Masthead matter={matter} evidence={evidence} genKind={genKind} hasAssistant={hasAssistant} research={research}
        onGenerate={(k, includeResearch) => void generate(k, includeResearch)} />
      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1">
          <Console messages={messages} status={status} sending={sending} evidence={evidence} onSend={(t) => void send(t)} />
        </div>
        <div className="flex w-80 shrink-0 flex-col border-l border-white/[0.06]">
          <LegalContextPanel legalContext={evidence?.legal_context} research={research}
            onRunResearch={onRunResearch} researching={researching} />
          <EvidencePanel evidence={evidence} />
          <PacketsPanel matterId={matter.id} packets={matter.packets ?? []} toast={toast} onShare={setShareFor} />
        </div>
      </div>
      {shareFor && <ShareModal matterId={matter.id} packet={shareFor} onClose={() => setShareFor(null)} toast={toast} />}
    </div>
  )
}
