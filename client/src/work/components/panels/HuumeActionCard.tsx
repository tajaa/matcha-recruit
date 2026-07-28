import { AlertTriangle } from 'lucide-react'
import type { HuumeAction } from '../../types'
import { DONE_LABELS, bannerLabel, actionIcon } from '../../utils/huumeActionMeta'

interface HuumeActionCardProps {
  action: HuumeAction
  lightMode?: boolean
  /** Disables Confirm/Cancel while a turn is streaming — the staged state may
   * be about to change under the buttons. */
  streaming?: boolean
  /** Sends the literal chat text through the thread's normal send path.
   * Confirm/cancel are chat-only tools by design (services/huume/actions.py
   * evaluate_huume_action): the click still produces a separate user turn,
   * so the backend's structural two-turn confirm rule is fully preserved.
   * No REST twin exists for this. */
  onSendChat?: (text: string) => void
}

/** Slim chat-bottom strip between the message list and composer (visible on
 * mobile too). The full staged-action review now lives in the Huume right
 * panel (HuumePanel/ConfirmBar + ActionDocViewer/OfferLetterViewer) — this
 * component only ever renders the banner. */
export default function HuumeActionCard({ action, lightMode, streaming, onSendChat }: HuumeActionCardProps) {
  const cardBg = lightMode ? 'bg-orange-50 border-orange-200 text-orange-900' : 'bg-orange-950/30 border-orange-900/50 text-orange-100'
  const chipRed = lightMode ? 'bg-red-50 text-red-700 border-red-300' : 'bg-red-950/40 text-red-300 border-red-800'

  if (action.status === 'cancelled') return null

  const doneLabel = DONE_LABELS[action.type]?.[action.status]
  if (doneLabel) return null // done state has its own chip in the panel; the banner just clears

  if (action.status === 'failed') {
    return (
      <div className={`mx-3 mt-2 flex items-center gap-1.5 text-[11px] px-2 py-1.5 rounded border w-fit ${chipRed}`}>
        <AlertTriangle size={12} /> The last action failed — ask Huume what happened.
      </div>
    )
  }

  // status === 'proposed' — awaiting confirmation.
  return (
    <div className={`mx-3 mt-2 flex items-center gap-2 rounded border px-2.5 py-1.5 ${cardBg}`}>
      {actionIcon(action.type)}
      <span className="flex-1 truncate text-[11px] font-medium">{bannerLabel(action)}</span>
      <button
        type="button"
        disabled={streaming || !onSendChat}
        onClick={() => onSendChat?.('confirm')}
        className="text-[11px] font-medium px-2 py-1 rounded bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed text-white"
      >
        Confirm
      </button>
      <button
        type="button"
        disabled={streaming || !onSendChat}
        onClick={() => onSendChat?.('cancel')}
        className="text-[11px] font-medium px-2 py-1 rounded border border-orange-700 text-orange-300 hover:bg-orange-950/40 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        Cancel
      </button>
    </div>
  )
}
