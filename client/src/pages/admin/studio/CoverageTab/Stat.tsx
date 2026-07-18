import { useEffect, useState } from 'react'
import { LABEL } from '../../../../components/ui'

// One cell of the KPI stat strip.
export function Stat({
  label, value, tone = 'text-zinc-100', hint, onClick, delay = 0,
}: {
  label: string; value: string; tone?: string; hint?: string; onClick?: () => void; delay?: number
}) {
  const [shown, setShown] = useState(false)
  useEffect(() => {
    const id = requestAnimationFrame(() => setShown(true))
    return () => cancelAnimationFrame(id)
  }, [])
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!onClick}
      title={hint}
      style={{ transitionDelay: `${delay}ms` }}
      className={`flex min-w-0 flex-1 flex-col items-start gap-1 px-4 py-3 text-left transition-opacity duration-300 motion-reduce:transition-none ${
        shown ? 'opacity-100' : 'opacity-0'
      } ${onClick ? 'cursor-pointer hover:bg-white/[0.02]' : 'cursor-default'}`}
    >
      <span className={LABEL}>{label}</span>
      <span className={`font-mono text-2xl font-semibold tabular-nums tracking-tight ${tone}`}>{value}</span>
    </button>
  )
}
