import type { Palette } from './types'

export function RootNode({ p }: { p: Palette }) {
  return (
    <div
      className="rounded-md px-3.5 py-2 flex items-center gap-2"
      style={{
        backgroundColor: 'rgba(20,20,16,0.95)',
        border: `1px solid ${p.amber}26`,
        boxShadow: `0 0 8px ${p.amber}10`,
      }}
    >
      <div className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: p.amber, boxShadow: `0 0 6px ${p.amber}` }} />
      <span className="font-mono text-[10px] font-semibold tracking-wide uppercase" style={{ color: '#e4ded2' }}>
        SB 553 audit
      </span>
      <span className="font-mono text-[9px]" style={{ color: '#6a737d' }}>·</span>
      <span className="font-mono text-[9px]" style={{ color: '#9a8a70' }}>5 components</span>
    </div>
  )
}
