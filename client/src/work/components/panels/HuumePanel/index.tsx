import { useEffect, useMemo, useRef, useState } from 'react'
import { FileSignature, PlayCircle, BookOpen, Scale, Send, X } from 'lucide-react'
import type { HuumeOffer, HuumePlan, HuumeRecordRef } from '../../../types'
import { getHuumeState, deriveHuumeArtifacts, defaultArtifactKey, type HuumeArtifact } from '../../../utils/huumeState'
import { actionIcon, bannerLabel } from '../../../utils/huumeActionMeta'
import { closeHuumeRecord } from '../../../api/matchaWork/huume'
import { useToast } from '../../../../components/ui'
import OfferLetterViewer from './OfferLetterViewer'
import ActionDocViewer from './ActionDocViewer'
import PlanViewer from './PlanViewer'
import HandbookDraftsViewer from './HandbookDraftsViewer'
import LegalMatterViewer from './LegalMatterViewer'
import RecordViewer, { recordIcon } from './RecordViewer'

interface HuumePanelProps {
  state: Record<string, unknown>
  threadId: string
  lightMode?: boolean
  streaming?: boolean
  onStateUpdate: (offerId: string, plan: HuumePlan) => void
  onExecuted?: () => void
  /** Called after a record tab's × successfully closes it server-side, with
   * the updated working set the DELETE response already returned — the
   * caller merges it straight into `current_state.huume_records` rather
   * than refetching the whole thread. */
  onRecordClosed?: (records: HuumeRecordRef[]) => void
  /** Closes the panel WITHOUT touching `huume_mode` — that stays a separate
   * action on the ThreadHeader pill. Every message keeps routing through
   * Huume (tools, grounding, the panel-worthy output) whether or not the
   * panel is visible; hiding it costs nothing, unlike disabling the mode,
   * which silently drops the thread onto the generic assistant with no
   * indicator (the bug this replaced: the panel's × used to call
   * handleModeToggle('huume')). */
  onDismiss?: () => void
}

function tabLabel(a: HuumeArtifact): { icon: React.ReactNode; label: string } {
  switch (a.kind) {
    case 'offer': return { icon: <FileSignature size={12} />, label: 'Offer' }
    case 'plan': return { icon: <PlayCircle size={12} />, label: `Plan${a.plan.employee.first_name ? ` — ${a.plan.employee.first_name}` : ''}` }
    case 'action': return { icon: actionIcon(a.action.type, 12), label: a.action.type.replace(/_/g, ' ') }
    case 'handbook': return { icon: <BookOpen size={12} />, label: `Handbook (${a.pendingDrafts.length})` }
    case 'legal': return { icon: <Scale size={12} />, label: a.title ?? 'Legal' }
    case 'record': return { icon: recordIcon(a.recordType), label: a.label ?? a.recordType.replace(/_/g, ' ') }
  }
}

const STATUS_CHIP: Record<HuumeOffer['status'], string> = {
  accepted: 'Accepted', sent: 'Sent — awaiting response', rejected: 'Declined', draft: 'Draft',
}

/** Right-panel artifact viewer for a Huume thread — replaces the old
 * HuumePlanCard, which showed only a status chip, a raw offer UUID, and
 * Confirm/Cancel for whatever was staged. This renders the actual document
 * (offer letter, staged action, onboarding plan, handbook draft, legal
 * memo), with a passive status line for anything awaiting a decision —
 * the actionable Confirm/Cancel lives only in the chat strip
 * (HuumeActionCard) now, so there's exactly one place a click can fire it. */
export default function HuumePanel({ state, threadId, lightMode, streaming, onStateUpdate, onExecuted, onRecordClosed, onDismiss }: HuumePanelProps) {
  const { toast } = useToast()
  const huume = getHuumeState(state)
  const artifacts = useMemo(() => deriveHuumeArtifacts(huume), [huume])
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [closingRecordKey, setClosingRecordKey] = useState<string | null>(null)

  // The most-recently-opened record wins focus (the whole point of "show it
  // to me" is that the panel jumps to it) — `merge_open_records` appends on
  // the server, so the LAST entry is always the newest show_record call.
  // Declared before the proposed-action effect below so a simultaneous
  // staged action still wins if both change at once. Keyed on `opened_at`
  // (not just record_type/record_id) so re-asking Huume to show a record
  // that's already open — but not already last, or already focused — still
  // refocuses: a plain position-based key can be unchanged when the entry
  // was already last, which `opened_at` (a fresh nonce every call) is not.
  const lastRecord = huume.records?.[huume.records.length - 1]
  const recordKey = lastRecord ? `record:${lastRecord.record_type}:${lastRecord.record_id}` : null
  const recordFocusToken = lastRecord ? `${recordKey}:${lastRecord.opened_at ?? ''}` : null
  // Per-record `opened_at` last seen — NOT just the last-in-array's token.
  // Closing an unrelated background tab shrinks the array and can change
  // which record is now last, which would otherwise change `recordFocusToken`
  // and steal focus from whatever the user was actually viewing even though
  // nothing was newly shown. Only refocus when the now-last record's OWN
  // `opened_at` actually advanced since we last saw it — true for a genuine
  // new/re-shown record, false when it merely became last via a removal.
  const seenOpenedAtRef = useRef<Map<string, string>>(new Map())
  useEffect(() => {
    if (recordKey && lastRecord) {
      const previouslySeen = seenOpenedAtRef.current.get(recordKey)
      const currentOpenedAt = lastRecord.opened_at ?? ''
      if (previouslySeen !== currentOpenedAt) setSelectedKey(recordKey)
    }
    const next = new Map<string, string>()
    for (const r of huume.records ?? []) next.set(`record:${r.record_type}:${r.record_id}`, r.opened_at ?? '')
    seenOpenedAtRef.current = next
  }, [recordFocusToken, recordKey, huume.records])

  // A newly-staged proposed action — or a plan with steps awaiting
  // approval — must win over whatever tab the user happens to have open,
  // and over a stale open record (entries are never cleared except by an
  // explicit close, so an old show_record from days ago would otherwise
  // keep re-winning focus on every mount ahead of a plan that actually
  // needs review). Declared after the record effect above so it runs later
  // in the same commit and takes priority when both fire together (e.g. on
  // mount).
  const proposedPlanArtifact = artifacts.find((a) => a.kind === 'plan' && a.plan.status === 'proposed')
  const proposedTargetKey = huume.action?.status === 'proposed'
    ? defaultArtifactKey(artifacts, huume.action)
    : proposedPlanArtifact?.key ?? null
  useEffect(() => {
    if (proposedTargetKey) setSelectedKey(proposedTargetKey)
  }, [proposedTargetKey])

  const activeKey = artifacts.some((a) => a.key === selectedKey)
    ? selectedKey
    : defaultArtifactKey(artifacts, huume.action)
  const active = artifacts.find((a) => a.key === activeKey) ?? null

  const bg = lightMode ? 'bg-white' : 'bg-zinc-900'
  const border = lightMode ? 'border-zinc-200' : 'border-zinc-800'

  return (
    <div className={`flex w-full flex-1 min-w-0 flex-col ${bg}`}>
      <div className={`flex flex-wrap items-center gap-1.5 border-b px-3 py-2 ${border}`}>
        <span className={`text-xs font-medium uppercase tracking-wide ${lightMode ? 'text-zinc-500' : 'text-zinc-500'}`}>Huume</span>
        {huume.offer && (
          <span className="rounded border border-zinc-700/50 bg-zinc-800/40 px-1.5 py-0.5 text-[10px] text-zinc-400">
            {STATUS_CHIP[huume.offer.status] ?? huume.offer.status}
          </span>
        )}
        {(artifacts.length > 1 || artifacts.some((a) => a.kind === 'record')) && artifacts.map((a) => {
          const { icon, label } = tabLabel(a)
          const isActive = a.key === activeKey
          const closing = closingRecordKey === a.key
          return (
            <div
              key={a.key}
              className={`flex items-center gap-0.5 rounded text-[11px] font-medium capitalize ${
                isActive
                  ? 'bg-orange-600 text-white'
                  : lightMode ? 'text-zinc-600 hover:bg-zinc-100' : 'text-zinc-400 hover:bg-zinc-800'
              }`}
            >
              <button
                type="button"
                onClick={() => setSelectedKey(a.key)}
                className="flex items-center gap-1 rounded py-1 pl-2 pr-1"
              >
                {icon} <span className="max-w-[140px] truncate">{label}</span>
              </button>
              {a.kind === 'record' && (
                <button
                  type="button"
                  disabled={closing}
                  title="Close"
                  onClick={async (e) => {
                    e.stopPropagation()
                    setClosingRecordKey(a.key)
                    try {
                      const { records } = await closeHuumeRecord(threadId, a.recordType, a.recordId)
                      onRecordClosed?.(records)
                    } catch {
                      toast('Could not close that record — try again.', 'error')
                    } finally {
                      setClosingRecordKey(null)
                    }
                  }}
                  className={`rounded-r p-1 mr-0.5 disabled:opacity-50 ${
                    isActive ? 'hover:bg-orange-700' : lightMode ? 'hover:bg-zinc-200' : 'hover:bg-zinc-700'
                  }`}
                >
                  <X size={11} />
                </button>
              )}
            </div>
          )
        })}
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            title="Close panel"
            className={`ml-auto shrink-0 p-1 rounded transition-colors ${
              lightMode ? 'text-zinc-400 hover:text-zinc-700 hover:bg-zinc-100' : 'text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800'
            }`}
          >
            <X size={14} />
          </button>
        )}
      </div>

      <div className="flex flex-1 min-h-0 flex-col overflow-y-auto">
        {!active && (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 px-4 text-center">
            <Send size={20} className={lightMode ? 'text-zinc-300' : 'text-zinc-700'} />
            <p className={`text-sm ${lightMode ? 'text-zinc-500' : 'text-zinc-500'}`}>
              Ask Huume to draft an offer, stage an onboarding plan, work with Legal or Handbook
              Pilot, or show you a record — what it produces shows up here for review.
            </p>
          </div>
        )}
        {active?.kind === 'offer' && (
          <OfferLetterViewer
            key={active.key}
            offerId={active.offerId}
            offer={huume.offer?.offer_id === active.offerId ? huume.offer : undefined}
            lightMode={lightMode}
          />
        )}
        {active?.kind === 'plan' && (
          <PlanViewer
            key={active.key}
            offerId={active.offerId} plan={active.plan} threadId={threadId} lightMode={lightMode}
            onStateUpdate={onStateUpdate} streaming={streaming} onExecuted={onExecuted}
          />
        )}
        {active?.kind === 'action' && (
          <ActionDocViewer key={active.key} action={active.action} lightMode={lightMode} />
        )}
        {active?.kind === 'handbook' && (
          <HandbookDraftsViewer key={active.key} sessionId={active.sessionId} pendingDrafts={active.pendingDrafts} lightMode={lightMode} />
        )}
        {active?.kind === 'legal' && (
          <LegalMatterViewer key={active.key} matterId={active.matterId} lightMode={lightMode} streaming={streaming} />
        )}
        {active?.kind === 'record' && (
          <RecordViewer
            key={active.key} threadId={threadId} recordType={active.recordType} recordId={active.recordId}
            lightMode={lightMode} streaming={streaming}
          />
        )}
      </div>

      {huume.action?.status === 'proposed' && (
        <div className="flex items-center gap-1.5 border-t border-w-line px-3 py-2 text-[11px] text-w-dim">
          {actionIcon(huume.action.type)}
          <span className="truncate">Awaiting your confirmation in chat — {bannerLabel(huume.action)}</span>
        </div>
      )}
    </div>
  )
}
