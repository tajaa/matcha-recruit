import { Card } from '../ui'

type Props = {
  stepLabel: string
  title: string
  description?: string
  required?: boolean
  children: React.ReactNode
}

export function HandbookWizardCard({ stepLabel, title, description, required, children }: Props) {
  return (
    <Card className="mb-4">
      <p className="text-[11px] uppercase tracking-wider text-zinc-500 mb-1">{stepLabel}</p>
      <div className="flex items-center gap-2 mb-2">
        <h3 className="text-base font-semibold text-zinc-100">{title}</h3>
        {required && <span className="text-xs text-amber-500">Required</span>}
      </div>
      {description && <p className="text-xs text-zinc-500 mb-3">{description}</p>}
      {children}
    </Card>
  )
}
