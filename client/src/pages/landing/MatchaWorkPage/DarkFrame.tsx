// ---------------------------------------------------------------------------
// Pillar visual (lightweight dark mock, no looping animation)
// ---------------------------------------------------------------------------

export function DarkFrame({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="w-full h-full flex flex-col relative" style={{ backgroundColor: '#0e0d0b', color: '#d4d4d4' }}>
      <div
        className="absolute inset-0 pointer-events-none opacity-[0.08]"
        style={{
          backgroundImage:
            'linear-gradient(rgba(255,255,255,0.15) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.15) 1px, transparent 1px)',
          backgroundSize: '20px 20px',
        }}
      />
      <div
        className="relative flex items-center justify-between px-4 py-2.5 border-b shrink-0"
        style={{ borderColor: 'rgba(255,255,255,0.08)' }}
      >
        <span className="text-[11px] font-medium tracking-wide font-mono uppercase" style={{ color: '#e4ded2' }}>
          {label}
        </span>
        <span
          className="text-[8.5px] uppercase tracking-wider px-1.5 py-[1px] rounded font-mono"
          style={{ color: '#86efac', border: '1px solid rgba(134,239,172,0.4)' }}
        >
          Live
        </span>
      </div>
      <div className="relative flex-1 min-h-0">{children}</div>
    </div>
  )
}
