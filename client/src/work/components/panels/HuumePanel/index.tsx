import { useEffect, useMemo, useState } from 'react'
import { FileSignature, PlayCircle, BookOpen, Scale, Send } from 'lucide-react'
import type { HuumeOffer, HuumePlan } from '../../../types'
import { getHuumeState, deriveHuumeArtifacts, defaultArtifactKey, type HuumeArtifact } from '../../../utils/huumeState'
import { actionIcon } from '../../../utils/huumeActionMeta'
import ConfirmBar from './ConfirmBar'
import OfferLetterViewer from './OfferLetterViewer'
import ActionDocViewer from './ActionDocViewer'
import PlanViewer from './PlanViewer'
import HandbookDraftsViewer from './HandbookDraftsViewer'
import LegalMatterViewer from './LegalMatterViewer'

interface HuumePanelProps {
  state: Record<string, unknown>
  threadId: string
  lightMode?: boolean
  streaming?: boolean
  onStateUpdate: (offerId: string, plan: HuumePlan) => void
  onSendChat?: (text: string) => void
  onExecuted?: () => void
}

function tabLabel(a: HuumeArtifact): { icon: React.ReactNode; label: string } {
  switch (a.kind) {
    case 'offer': return { icon: <FileSignature size={12} />, label: 'Offer' }
    case 'plan': return { icon: <PlayCircle size={12} />, label: `Plan${a.plan.employee.first_name ? ` — ${a.plan.employee.first_name}` : ''}` }
    case 'action': return { icon: actionIcon(a.action.type, 12), label: a.action.type.replace(/_/g, ' ') }
    case 'handbook': return { icon: <BookOpen size={12} />, label: `Handbook (${a.pendingDrafts.length})` }
    case 'legal': return { icon: <Scale size={12} />, label: a.title ?? 'Legal' }
  }
}

const STATUS_CHIP: Record<HuumeOffer['status'], string> = {
  accepted: 'Accepted', sent: 'Sent — awaiting response', rejected: 'Declined', draft: 'Draft',
}

/** Right-panel artifact viewer for a Huume thread — replaces the old
 * HuumePlanCard, which showed only a status chip, a raw offer UUID, and
 * Confirm/Cancel for whatever was staged. This renders the actual document
 * (offer letter, staged action, onboarding plan, handbook draft, legal
 * memo) with one docked confirm bar for whatever needs a decision. */
export default function HuumePanel({ state, threadId, lightMode, streaming, onStateUpdate, onSendChat, onExecuted }: HuumePanelProps) {
  const huume = getHuumeState(state)
  const artifacts = useMemo(() => deriveHuumeArtifacts(huume), [huume])
  const [selectedKey, setSelectedKey] = useState<string | null>(null)

  // A newly-staged proposed action must win over whatever tab the user
  // happens to have open — otherwise the ConfirmBar can ask the user to
  // confirm/cancel a document the visible tab isn't even showing. Only
  // fires when the *target* of the proposal changes (new id), so freely
  // navigating tabs while the SAME proposal is still pending is untouched.
  const proposedTargetKey = huume.action?.status === 'proposed' ? defaultArtifactKey(artifacts, huume.action) : null
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
        {artifacts.length > 1 && artifacts.map((a) => {
          const { icon, label } = tabLabel(a)
          const isActive = a.key === activeKey
          return (
            <button
              key={a.key}
              type="button"
              onClick={() => setSelectedKey(a.key)}
              className={`flex items-center gap-1 rounded px-2 py-1 text-[11px] font-medium capitalize ${
                isActive
                  ? 'bg-orange-600 text-white'
                  : lightMode ? 'text-zinc-600 hover:bg-zinc-100' : 'text-zinc-400 hover:bg-zinc-800'
              }`}
            >
              {icon} {label}
            </button>
          )
        })}
      </div>

      <div className="flex flex-1 min-h-0 flex-col overflow-y-auto">
        {!active && (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 px-4 text-center">
            <Send size={20} className={lightMode ? 'text-zinc-300' : 'text-zinc-700'} />
            <p className={`text-sm ${lightMode ? 'text-zinc-500' : 'text-zinc-500'}`}>
              Ask Huume to draft an offer, stage an onboarding plan, or work with Legal or Handbook
              Pilot — what it produces shows up here for review.
            </p>
          </div>
        )}
        {active?.kind === 'offer' && (
          <OfferLetterViewer
            offerId={active.offerId}
            offer={huume.offer?.offer_id === active.offerId ? huume.offer : undefined}
            lightMode={lightMode}
          />
        )}
        {active?.kind === 'plan' && (
          <PlanViewer
            offerId={active.offerId} plan={active.plan} threadId={threadId} lightMode={lightMode}
            onStateUpdate={onStateUpdate} streaming={streaming} onExecuted={onExecuted}
          />
        )}
        {active?.kind === 'action' && (
          <ActionDocViewer action={active.action} lightMode={lightMode} />
        )}
        {active?.kind === 'handbook' && (
          <HandbookDraftsViewer sessionId={active.sessionId} pendingDrafts={active.pendingDrafts} lightMode={lightMode} />
        )}
        {active?.kind === 'legal' && (
          <LegalMatterViewer matterId={active.matterId} lightMode={lightMode} />
        )}
      </div>

      {huume.action?.status === 'proposed' && (
        <ConfirmBar action={huume.action} lightMode={lightMode} streaming={streaming} onSendChat={onSendChat} />
      )}
    </div>
  )
}
