/**
 * The numbered "Locations → Employees → Done" progress rail used by the
 * onboarding wizards.
 *
 * IrOnboardingWizard and MatchaXOnboardingWizard had identical render bodies
 * and differed only in how they derived the active index: MatchaX has a
 * terminal `done` state that sits PAST the last listed step, and renders every
 * step complete when it is reached. So this takes `activeIndex` already
 * computed rather than a step key — pushing that derivation in here would mean
 * teaching a presentational component about each wizard's step union.
 */

export type WizardStep = { key: string; label: string }

type Props = {
  steps: WizardStep[]
  /** Index of the current step. Pass `steps.length` to render all complete. */
  activeIndex: number
}

export function WizardStepper({ steps, activeIndex }: Props) {
  return (
    <ol className="flex items-center gap-2 text-xs text-zinc-500">
      {steps.map((s, i) => {
        const done = i < activeIndex
        const active = i === activeIndex
        return (
          <li key={s.key} className="flex items-center gap-2">
            <span
              className={
                'w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-medium ' +
                (done
                  ? 'bg-emerald-700 text-white'
                  : active
                    ? 'bg-zinc-800 text-zinc-100 ring-1 ring-emerald-700'
                    : 'bg-zinc-900 text-zinc-600')
              }
            >
              {i + 1}
            </span>
            <span className={active ? 'text-zinc-200' : ''}>{s.label}</span>
            {i < steps.length - 1 && <span className="text-zinc-700">→</span>}
          </li>
        )
      })}
    </ol>
  )
}
