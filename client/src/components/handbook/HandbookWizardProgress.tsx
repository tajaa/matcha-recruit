const STEPS = [
  'Business Profile',
  'State Scope',
  'Company Profile',
  'Policy Setup',
  'Review',
]

type Props = {
  currentStep: number
  draftStatus?: 'saved' | 'saving' | 'unsaved'
}

export function HandbookWizardProgress({ currentStep, draftStatus }: Props) {
  return (
    <div className="mb-6">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          {STEPS.map((label, i) => (
            <div key={label} className="flex items-center gap-2">
              <div
                className={`flex items-center justify-center w-7 h-7 rounded-full text-xs font-semibold ${
                  i < currentStep
                    ? 'bg-emerald-600 text-white'
                    : i === currentStep
                      ? 'bg-zinc-700 text-zinc-100 ring-2 ring-emerald-500'
                      : 'bg-zinc-800 text-zinc-500'
                }`}
              >
                {i < currentStep ? '\u2713' : i + 1}
              </div>
              <span
                className={`text-xs hidden sm:inline ${
                  i === currentStep ? 'text-zinc-200' : 'text-zinc-500'
                }`}
              >
                {label}
              </span>
              {i < STEPS.length - 1 && (
                <div className={`w-6 h-px ${i < currentStep ? 'bg-emerald-600' : 'bg-zinc-700'}`} />
              )}
            </div>
          ))}
        </div>
        {draftStatus && (
          <span className="text-[11px] text-zinc-500">
            {draftStatus === 'saving' ? 'Saving...' : draftStatus === 'saved' ? 'Draft saved' : 'Unsaved'}
          </span>
        )}
      </div>
    </div>
  )
}
