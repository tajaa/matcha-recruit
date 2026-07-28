import type { HuumeAction } from '../../../types'
import { bannerLabel } from '../../../utils/huumeActionMeta'

interface ConfirmBarProps {
  action: HuumeAction
  lightMode?: boolean
  streaming?: boolean
  onSendChat?: (text: string) => void
}

/** id shown in the confirm bar's mono caption — the field that actually
 * identifies the staged record for each action type. */
function idOf(action: HuumeAction): string {
  switch (action.type) {
    case 'send_offer': return action.offer_id
    case 'discipline_draft': return action.confirm_id
    case 'ir_report': return action.confirm_id
    case 'er_case': return action.confirm_id
    case 'training_assign': return action.requirement_id
    case 'pto_decision': return action.request_id
  }
}

/** Docked footer for the Huume panel — the panel-variant Confirm/Cancel used
 * to live inline per-artifact (HuumeActionCard's old 'panel' variant); it's
 * now one bar under whatever document is showing, so approving an action
 * never depends on which tab happens to be selected. */
export default function ConfirmBar({ action, lightMode, streaming, onSendChat }: ConfirmBarProps) {
  const id = idOf(action)
  const border = lightMode ? 'border-zinc-200' : 'border-zinc-800'
  const bg = lightMode ? 'bg-zinc-50' : 'bg-zinc-950/40'

  return (
    <div className={`flex items-center gap-2 border-t px-3 py-2.5 ${border} ${bg}`}>
      <div className="min-w-0 flex-1">
        <div className={`text-xs font-medium ${lightMode ? 'text-zinc-800' : 'text-zinc-200'}`}>
          {bannerLabel(action)}
        </div>
        <div className="truncate font-mono text-[10px] opacity-60" title={id}>{id.slice(0, 8)}</div>
      </div>
      <button
        type="button"
        disabled={streaming || !onSendChat}
        onClick={() => onSendChat?.('confirm')}
        className="shrink-0 text-xs font-medium px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed text-white"
      >
        Confirm
      </button>
      <button
        type="button"
        disabled={streaming || !onSendChat}
        onClick={() => onSendChat?.('cancel')}
        className="shrink-0 text-xs font-medium px-3 py-1.5 rounded border border-orange-700 text-orange-500 hover:bg-orange-950/10 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        Cancel
      </button>
    </div>
  )
}
