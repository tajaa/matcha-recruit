import type { ReactNode } from 'react'
export function MetricStrip({ cols, subtle = false, className = '', children }: {
  cols: string; subtle?: boolean; className?: string; children: ReactNode
}) {
  const surface = subtle ? 'bg-white/[0.06] border border-white/[0.08]' : 'bg-white/10 border border-white/10'
  return <div className={`grid ${cols} gap-px ${surface} rounded-2xl overflow-hidden${className ? ' ' + className : ''}`}>{children}</div>
}
