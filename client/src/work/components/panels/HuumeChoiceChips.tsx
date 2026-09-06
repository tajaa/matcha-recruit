import type { HuumeChoice } from '../../types'

interface HuumeChoiceChipsProps {
  choice: HuumeChoice
  /** True while a turn is streaming — the question may be about to be
   * answered/replaced under the buttons. */
  disabled: boolean
  /** Sends the picked text through the thread's normal send path, exactly
   * like HuumeActionCard's Confirm/Cancel: the click produces an ordinary
   * user turn, so nothing about the backend's turn structure changes. */
  onPick: (text: string) => void
}

/** Clickable shortcuts for a question whose answer is a finite choice
 * ("Which location?", "Which week template?"). Typing the answer stays
 * equally valid — these chips only save the manager the keystrokes. */
export default function HuumeChoiceChips({ choice, disabled, onPick }: HuumeChoiceChipsProps) {
  if (!choice.options?.length) return null
  const labelId = 'huume-choice-question'

  return (
    <div role="group" aria-labelledby={labelId} className="mx-3 flex flex-col gap-1.5">
      <span id={labelId} className="text-[11px] text-zinc-400">{choice.question}</span>
      <div className="flex flex-wrap gap-1.5">
        {choice.options.map((option, index) => (
          <button
            key={`${option.label}-${index}`}
            type="button"
            disabled={disabled}
            onClick={() => onPick(option.send ?? option.label)}
            className="rounded-lg border border-emerald-500/30 bg-emerald-500/[0.08] px-2.5 py-1.5 text-left text-[11px] font-medium text-emerald-200 hover:bg-emerald-500/[0.14] disabled:cursor-not-allowed disabled:opacity-40"
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  )
}
