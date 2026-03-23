import { Card } from '../ui'

interface SignatureRingProps {
  rate: number
  hasPolicies: boolean
  title?: string
  label?: string
  emptyLabel?: string
}

export function SignatureRing({ rate, hasPolicies, title = 'Policy Signatures', label = 'Signed', emptyLabel = 'No data' }: SignatureRingProps) {
  const radius = 50
  const stroke = 8
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (rate / 100) * circumference

  const color =
    rate >= 80 ? 'text-emerald-500' : rate >= 50 ? 'text-amber-500' : 'text-red-500'

  return (
    <Card className="p-5 flex flex-col items-center">
      <h3 className="text-sm font-medium text-zinc-200 tracking-wide mb-4 self-start">{title}</h3>

      <div className="relative w-32 h-32">
        <svg viewBox="0 0 120 120" className="w-full h-full -rotate-90">
          <circle
            cx="60" cy="60" r={radius}
            fill="none" stroke="currentColor"
            strokeWidth={stroke}
            className="text-zinc-800"
          />
          <circle
            cx="60" cy="60" r={radius}
            fill="none" stroke="currentColor"
            strokeWidth={stroke}
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            className={`${color} transition-all duration-700`}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-semibold text-zinc-100">
            {hasPolicies ? `${Math.round(rate)}%` : '--'}
          </span>
          <span className="text-[10px] text-zinc-500">
            {hasPolicies ? label : emptyLabel}
          </span>
        </div>
      </div>

      {hasPolicies && (
        <div className="w-full mt-4">
          <div className="h-1.5 rounded-full bg-zinc-800">
            <div
              className={`h-1.5 rounded-full transition-all duration-700 ${
                rate >= 80 ? 'bg-emerald-500' : rate >= 50 ? 'bg-amber-500' : 'bg-red-500'
              }`}
              style={{ width: `${rate}%` }}
            />
          </div>
        </div>
      )}
    </Card>
  )
}
