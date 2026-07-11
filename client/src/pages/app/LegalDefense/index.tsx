import { useEffect, useRef, useState } from 'react'
import { HelpCircle, Loader2, Plus, Scale } from 'lucide-react'
import { Button, Select, useToast } from '../../../components/ui'
import { HowItWorksModal } from '../../../components/ui/HowItWorksModal'
import { useShowOnce } from '../../../hooks/useShowOnce'
import { LEGAL_PILOT_HOW_IT_WORKS_STEPS } from './howItWorksSteps'
import {
  listMatters, getMatter, getEvidence, generatePacket, downloadPacket, streamChat,
  runResearch, listResearch, updateMatter,
  type Matter, type MatterMessage, type EvidencePreview, type Packet, type ChatResult, type ResearchRow,
  type MatterTheory, type SubjectTheory,
} from '../../../api/legalDefense'
import { LABEL, seedRecap, startersFor, typeLabel } from './shared'
import { Masthead } from './Masthead'
import { Console } from './Console'
import { Chronology } from './Chronology'
import { EvidencePanel } from './EvidencePanel'
import { LegalContextPanel } from './LegalContextPanel'
import { PacketsPanel } from './PacketsPanel'
import { NewMatterModal, ShareModal } from './modals'

export default function LegalDefense() {
  const { toast } = useToast()
  const [showHelp, setShowHelp] = useShowOnce('legal-pilot')
  const [matters, setMatters] = useState<Matter[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [matter, setMatter] = useState<Matter | null>(null)
  const [evidence, setEvidence] = useState<EvidencePreview | null>(null)
  const [research, setResearch] = useState<ResearchRow | null>(null)
  const [researching, setResearching] = useState(false)
  const [loading, setLoading] = useState(true)
  const [showNew, setShowNew] = useState(false)
  // Matter id awaiting its auto-seeded first turn — set only on creation, so
  // reopening an existing matter later never re-triggers the seed.
  const [justCreatedId, setJustCreatedId] = useState<string | null>(null)
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
    setJustCreatedId(m.id)
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
          <div className="flex items-center gap-0.5">
            <button
              onClick={() => setShowHelp(true)}
              aria-label="How Legal Pilot works"
              className="rounded p-1 text-zinc-400 transition-colors hover:bg-white/[0.04] hover:text-zinc-100"
            >
              <HelpCircle className="h-4 w-4" />
            </button>
            <button
              onClick={() => setShowNew(true)}
              aria-label="New matter"
              className="rounded p-1 text-zinc-400 transition-colors hover:bg-white/[0.04] hover:text-zinc-100"
            >
              <Plus className="h-4 w-4" />
            </button>
          </div>
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
            <button
              onClick={() => setShowHelp(true)}
              className="text-xs text-zinc-500 underline-offset-2 transition-colors hover:text-zinc-300 hover:underline"
            >
              How Legal Pilot works
            </button>
          </div>
        ) : !matter ? (
          <div className="flex h-full items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-zinc-500" />
          </div>
        ) : (
          <MatterWorkbench
            matter={matter} evidence={evidence} research={research} researching={researching}
            onRunResearch={handleRunResearch} onRefresh={() => openMatter(matter.id)} toast={toast}
            autoSeed={matter.id === justCreatedId}
          />
        )}
      </div>

      {showNew && <NewMatterModal onClose={() => setShowNew(false)} onCreated={onCreated} />}
      {showHelp && (
        <HowItWorksModal
          title="How Legal Pilot works"
          steps={LEGAL_PILOT_HOW_IT_WORKS_STEPS}
          onClose={() => setShowHelp(false)}
        />
      )}
    </div>
  )
}

function MatterWorkbench({ matter, evidence, research, researching, onRunResearch, onRefresh, toast, autoSeed }: {
  matter: Matter; evidence: EvidencePreview | null; research: ResearchRow | null; researching: boolean
  onRunResearch: (includeGuidance?: boolean) => void; onRefresh: () => void
  toast: ReturnType<typeof useToast>['toast']
  autoSeed: boolean
}) {
  const [messages, setMessages] = useState<MatterMessage[]>(matter.messages ?? [])
  const [status, setStatus] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const [genKind, setGenKind] = useState<'pdf' | 'zip' | 'both' | null>(null)
  const [shareFor, setShareFor] = useState<Packet | null>(null)
  const [tab, setTab] = useState<'console' | 'chronology' | 'examples'>('console')
  const [prefill, setPrefill] = useState<{ text: string; nonce: number } | null>(null)
  const seededRef = useRef(false)
  const prefillNonceRef = useRef(0)

  useEffect(() => { setMessages(matter.messages ?? []) }, [matter.id, matter.messages])

  // Auto-seed the first turn from the intake form so a just-created matter
  // never asks the user to re-describe the claim/timeframe they just typed.
  // Reads matter.messages (the prop), not local state — the resync setter
  // above isn't visible via closure within the same commit. seededRef is set
  // synchronously so StrictMode's dev double-invoke can't fire send() twice.
  useEffect(() => {
    if (!autoSeed || seededRef.current) return
    if ((matter.messages ?? []).length > 0) return
    const recap = seedRecap(matter)
    if (!recap) return
    seededRef.current = true
    void send(recap)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matter.id])

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
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex shrink-0 items-center gap-1 border-b border-white/[0.06] px-5 py-1.5">
            {(['console', 'chronology', 'examples'] as const).map((t) => (
              <button key={t} onClick={() => setTab(t)}
                className={`rounded px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.15em] transition-colors ${
                  tab === t ? 'bg-white/[0.06] text-zinc-200' : 'text-zinc-500 hover:text-zinc-300'}`}>
                {t === 'console' ? 'Analyst console' : t === 'chronology' ? 'Chronology' : 'Examples'}
              </button>
            ))}
          </div>
          <div className="min-h-0 flex-1">
            {tab === 'console'
              ? <Console messages={messages} status={status} sending={sending} evidence={evidence}
                  onSend={(t) => void send(t)} matterType={matter.matter_type} prefill={prefill} />
              : tab === 'chronology'
              ? <Chronology evidence={evidence} />
              : <ExamplesPanel
                  items={startersFor(matter.matter_type)}
                  onUse={(t) => { setTab('console'); setPrefill({ text: t, nonce: ++prefillNonceRef.current }) }}
                />}
          </div>
        </div>
        <div className="flex min-h-0 w-80 shrink-0 flex-col overflow-y-auto border-l border-white/[0.06]">
          <LegalContextPanel legalContext={evidence?.legal_context} research={research}
            onRunResearch={onRunResearch} researching={researching}
            matterId={matter.id} onRefresh={onRefresh} />
          {/* Sibling, not nested: LegalContextPanel swaps itself for the
              jurisdiction setter when no jurisdiction is set, and the subject
              override has to stay reachable either way. */}
          <SubjectScopeSetter matter={matter} theory={evidence?.theory} onRefresh={onRefresh} />
          <EvidencePanel evidence={evidence} />
          <PacketsPanel matterId={matter.id} packets={matter.packets ?? []} toast={toast} onShare={setShareFor} />
        </div>
      </div>
      {shareFor && <ShareModal matterId={matter.id} packet={shareFor} onClose={() => setShareFor(null)} toast={toast} />}
    </div>
  )
}

// --------------------------------------------------------------------------- //
// SubjectScopeSetter — the override for the derived evidence subject.
//
// The backend reads the subject off the allegation, and a derivation can be
// wrong. Without a control the only recovery would be rewriting the allegation
// — mutating the legal record of what's being claimed to steer a classifier —
// or deleting the matter and losing its transcript, packets and audit trail.
// Same shape as the jurisdiction override that already sits above it.
// --------------------------------------------------------------------------- //

const SUBJECT_OPTIONS: { value: SubjectTheory | ''; label: string }[] = [
  { value: '', label: 'Auto — read from the allegation' },
  { value: 'wage_hour', label: 'Wage and hour' },
  { value: 'eeo', label: 'Discrimination / EEO' },
  { value: 'safety', label: 'Workplace safety' },
  { value: 'all', label: 'All records — no subject filter' },
]

function SubjectScopeSetter({ matter, theory, onRefresh }: {
  matter: Matter
  theory: MatterTheory | null | undefined
  onRefresh: () => void
}) {
  const { toast } = useToast()
  const [saving, setSaving] = useState(false)
  const current = matter.subject_theory ?? ''

  async function save(next: string) {
    if (saving || next === current) return
    setSaving(true)
    try {
      // '' clears the override back to derive — send null, not the empty string.
      await updateMatter(matter.id, { subject_theory: (next || null) as SubjectTheory | null })
      onRefresh()
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to set the evidence subject', 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="border-b border-white/[0.06] px-4 py-3">
      <div className="flex items-center justify-between gap-2">
        <span className={LABEL}>Evidence subject</span>
        {saving && <Loader2 className="h-3 w-3 animate-spin text-zinc-600" />}
      </div>
      <Select
        className="mt-2"
        value={current}
        options={SUBJECT_OPTIONS}
        onChange={(e) => void save(e.target.value)}
      />
      <p className="mt-1.5 text-[11px] leading-relaxed text-zinc-500">
        {matter.subject_theory
          ? 'Records outside this subject are left out of the corpus and the chat.'
          : theory
            ? `Read as ${theory.label} from the allegation. Set it yourself if that's wrong.`
            : 'Every subject is included. Narrow it to cut records unrelated to the claim.'}
      </p>
      <p className="mt-1 text-[10px] leading-relaxed text-zinc-600">
        The attorney packet always includes every record in scope, whichever subject is set.
      </p>
    </div>
  )
}

// --------------------------------------------------------------------------- //
// ExamplesPanel — browsable example prompts, matches the Console's own
// starter-row visual language so it reads as the same feature, not a bolt-on.
// --------------------------------------------------------------------------- //

function ExamplesPanel({ items, onUse }: { items: string[]; onUse: (text: string) => void }) {
  return (
    <div className="h-full overflow-y-auto px-5 py-8">
      <div className={LABEL}>Example prompts</div>
      <p className="mt-2 max-w-[60ch] text-sm leading-relaxed text-zinc-400">
        Click one to drop it into the console composer, then edit or send it as-is.
      </p>
      <div className="mt-4 max-w-[60ch]">
        {items.map((s) => (
          <button key={s}
            onClick={() => onUse(s)}
            className="group flex w-full items-start gap-2.5 border-t border-white/[0.06] py-2.5 text-left text-[13px] text-zinc-500 transition-colors last:border-b last:border-white/[0.06] hover:text-zinc-200"
          >
            <span className="font-mono text-emerald-500/70 transition-colors group-hover:text-emerald-400">›</span>
            {s}
          </button>
        ))}
      </div>
    </div>
  )
}
