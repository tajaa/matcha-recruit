import { useRef, useState, useEffect } from 'react'
import { motion, useInView, AnimatePresence } from 'framer-motion'
import { SCAN_LINE_BG, RADAR_DIMS, RADAR_VALUES } from './shared'

/* ── 9-Dimension Radar (Pre-Termination Intel) ────────────────── */
export function RadarChart() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { margin: '-80px' })
  const cx = 50, cy = 50, r = 35

  const [activeDim, setActiveDim] = useState<number | null>(null)
  const [rotation, setRotation] = useState(0)

  useEffect(() => {
    if (!inView) {
      setActiveDim(null)
      return
    }
    const interval = setInterval(() => {
      setActiveDim(prev => {
        if (prev === null) return 0
        return (prev + 1) % RADAR_DIMS.length
      })
    }, 2000)
    
    // Slow rotation
    let animationFrame: number
    let rot = 0
    const rotate = () => {
      rot += 0.05
      setRotation(rot)
      animationFrame = requestAnimationFrame(rotate)
    }
    animationFrame = requestAnimationFrame(rotate)
    
    return () => {
      clearInterval(interval)
      cancelAnimationFrame(animationFrame)
    }
  }, [inView])

  const toXY = (angle: number, radius: number) => ({
    x: cx + Math.cos(angle - Math.PI / 2) * radius,
    y: cy + Math.sin(angle - Math.PI / 2) * radius,
  })

  // We rotate the entire polygon and points visually by adjusting the angle,
  // but to keep labels upright we might want to rotate the SVG group instead,
  // or calculate the rotation in the angle. Let's rotate the SVG group for the radar
  // and counter-rotate the text labels.

  const polygon = RADAR_VALUES.map((v, i) => {
    const angle = (i / RADAR_DIMS.length) * Math.PI * 2
    const p = toXY(angle, r * v)
    return `${p.x},${p.y}`
  }).join(' ')

  const activeValue = activeDim !== null ? RADAR_VALUES[activeDim] : null
  const activeLabel = activeDim !== null ? RADAR_DIMS[activeDim] : null

  return (
    <div ref={ref} className="relative h-80 lg:h-96 flex items-center justify-center overflow-hidden bg-zinc-950 p-4"
      style={{ backgroundImage: SCAN_LINE_BG }}
    >
      {/* 3D Container for Radar */}
      <motion.div 
        className="relative w-full h-full flex items-center justify-center max-w-[360px]"
        initial={{ rotateX: 60, scale: 0.8, opacity: 0 }}
        animate={inView ? { rotateX: 55, scale: 1.1, opacity: 1 } : {}}
        transition={{ duration: 1.5, ease: "easeOut" }}
        style={{ transformStyle: 'preserve-3d', perspective: '1000px' }}
      >
        {/* Core Radar SVG */}
        <svg viewBox="0 0 100 100" className="absolute inset-0 w-full h-full drop-shadow-[0_20px_30px_rgba(0,0,0,0.8)] overflow-visible">
          
          <g style={{ transformOrigin: '50px 50px', transform: `rotate(${rotation}deg)` }}>
            {/* Concentric rings */}
            {[0.25, 0.5, 0.75, 1].map((scale, sIdx) => (
              <polygon
                key={scale}
                points={RADAR_DIMS.map((_, i) => {
                  const a = (i / RADAR_DIMS.length) * Math.PI * 2
                  const p = toXY(a, r * scale)
                  return `${p.x},${p.y}`
                }).join(' ')}
                fill="none"
                stroke={sIdx === 3 ? '#f59e0b' : '#3f3f46'}
                strokeWidth={sIdx === 3 ? 0.3 : 0.15}
                strokeDasharray={sIdx === 3 ? "none" : "1 1"}
                opacity={sIdx === 3 ? 0.5 : 1}
              />
            ))}

            {/* Sweep Gradient (Radar Scanner effect) */}
            <g style={{ transformOrigin: '50px 50px' }}>
              <animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="4s" repeatCount="indefinite" />
              <path d={`M 50 50 L 50 15 A 35 35 0 0 1 85 50 Z`} fill="url(#radarSweep)" opacity="0.4" />
            </g>

            {/* Axes */}
            {RADAR_DIMS.map((_, i) => {
              const a = (i / RADAR_DIMS.length) * Math.PI * 2
              const p = toXY(a, r)
              const isActive = activeDim === i
              return (
                <line 
                  key={i} 
                  x1={cx} y1={cy} 
                  x2={p.x} y2={p.y} 
                  stroke={isActive ? '#f59e0b' : '#3f3f46'} 
                  strokeWidth={isActive ? 0.4 : 0.2} 
                  opacity={isActive ? 1 : 0.5}
                />
              )
            })}

            {/* Data polygon */}
            <polygon
              points={polygon}
              fill="rgba(245,158,11,0.15)"
              stroke="#f59e0b"
              strokeWidth="0.6"
              strokeLinejoin="round"
              style={{
                filter: 'drop-shadow(0 0 4px rgba(245,158,11,0.5))'
              }}
            >
              <animate attributeName="stroke-opacity" values="1;0.6;1" dur="2s" repeatCount="indefinite" />
            </polygon>

            {/* Data points */}
            {RADAR_VALUES.map((v, i) => {
              const a = (i / RADAR_DIMS.length) * Math.PI * 2
              const p = toXY(a, r * v)
              const isActive = activeDim === i
              const isCritical = v > 0.7
              
              return (
                <g key={i}>
                  {/* Connecting line to center when active */}
                  {isActive && (
                    <line x1={cx} y1={cy} x2={p.x} y2={p.y} stroke={isCritical ? '#ef4444' : '#f59e0b'} strokeWidth="0.5" strokeDasharray="1 1" opacity="0.6" />
                  )}
                  <circle
                    cx={p.x}
                    cy={p.y}
                    r={isActive ? 2 : 1}
                    fill={isCritical ? '#ef4444' : '#f59e0b'}
                    style={{
                      transition: 'r 0.3s, fill 0.3s',
                      filter: isActive ? `drop-shadow(0 0 6px ${isCritical ? '#ef4444' : '#f59e0b'})` : 'none'
                    }}
                  />
                  {isActive && (
                    <circle cx={p.x} cy={p.y} r="3" fill="none" stroke={isCritical ? '#ef4444' : '#f59e0b'} strokeWidth="0.3">
                       <animate attributeName="r" values="2;5" dur="1s" repeatCount="indefinite" />
                       <animate attributeName="opacity" values="1;0" dur="1s" repeatCount="indefinite" />
                    </circle>
                  )}
                </g>
              )
            })}

            {/* Labels (counter-rotated so they stay upright) */}
            {RADAR_DIMS.map((label, i) => {
              const a = (i / RADAR_DIMS.length) * Math.PI * 2
              const p = toXY(a, r + 8)
              const isActive = activeDim === i
              const isCritical = RADAR_VALUES[i] > 0.7

              return (
                <g key={label} style={{ transformOrigin: `${p.x}px ${p.y}px`, transform: `rotate(${-rotation}deg)` }}>
                  <text
                    x={p.x}
                    y={p.y}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    className="font-[Orbitron] font-bold"
                    style={{
                      fontSize: isActive ? '3px' : '2.5px',
                      fill: isActive ? (isCritical ? '#ef4444' : '#f59e0b') : '#71717a',
                      transition: 'all 0.3s',
                      filter: isActive ? `drop-shadow(0 0 2px ${isCritical ? 'rgba(239,68,68,0.8)' : 'rgba(245,158,11,0.8)'})` : 'none'
                    }}
                  >
                    {label}
                  </text>
                  {isActive && (
                    <text
                      x={p.x}
                      y={p.y + 4}
                      textAnchor="middle"
                      dominantBaseline="middle"
                      className="font-mono"
                      style={{ fontSize: '2px', fill: isCritical ? '#ef4444' : '#fcd34d' }}
                    >
                      {(RADAR_VALUES[i] * 100).toFixed(0)}%
                    </text>
                  )}
                </g>
              )
            })}
          </g>

          <defs>
            <linearGradient id="radarSweep" x1="0%" y1="100%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="transparent" />
              <stop offset="80%" stopColor="rgba(245,158,11,0.1)" />
              <stop offset="100%" stopColor="rgba(245,158,11,0.8)" />
            </linearGradient>
          </defs>
        </svg>

        {/* 3D Vertical Scanning Laser */}
        <motion.div 
          className="absolute inset-x-0 h-1 bg-amber-500/80 pointer-events-none z-20"
          style={{ boxShadow: '0 0 20px #f59e0b, 0 0 40px #f59e0b', transform: 'translateZ(20px) rotateX(-55deg)' }}
          initial={{ top: '0%' }}
          animate={{ top: ['0%', '100%', '0%'] }}
          transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
        />

      </motion.div>

      {/* Target Assessment HUD */}
      <AnimatePresence mode="wait">
        {activeDim !== null && activeValue !== null && (
          <motion.div
            key={activeDim}
            className={`absolute right-4 lg:right-8 top-1/2 -translate-y-1/2 flex flex-col items-end z-30 p-3 rounded backdrop-blur-md border border-zinc-800/50 ${activeValue > 0.7 ? 'bg-red-950/20 shadow-[0_0_20px_rgba(239,68,68,0.1)]' : 'bg-zinc-950/60 shadow-[0_0_20px_rgba(0,0,0,0.5)]'}`}
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 10 }}
            transition={{ duration: 0.3 }}
          >
            <div className="text-xs text-zinc-500 uppercase tracking-widest font-bold mb-1">
              Dimension Scan
            </div>
            <div className={`text-[12px] font-[Orbitron] font-bold uppercase tracking-widest ${activeValue > 0.7 ? 'text-red-500 drop-shadow-[0_0_5px_rgba(239,68,68,0.8)]' : 'text-amber-500 drop-shadow-[0_0_5px_rgba(245,158,11,0.8)]'}`}>
              {activeLabel}
            </div>
            <div className="flex items-center gap-2 mt-2">
              <div className="w-16 h-1 bg-zinc-800 rounded-full overflow-hidden">
                <motion.div 
                  className={`h-full ${activeValue > 0.7 ? 'bg-red-500' : 'bg-amber-500'}`}
                  initial={{ width: 0 }}
                  animate={{ width: `${activeValue * 100}%` }}
                  transition={{ duration: 0.5, ease: "easeOut" }}
                />
              </div>
              <div className={`text-xs font-mono font-bold ${activeValue > 0.7 ? 'text-red-400' : 'text-amber-400'}`}>
                {(activeValue * 100).toFixed(1)}%
              </div>
            </div>
            {activeValue > 0.7 && (
              <div className="mt-2 text-xs text-red-300 font-mono bg-red-500/10 px-1.5 py-0.5 border border-red-500/30 rounded">
                ! HIGH EXPOSURE DETECTED
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Persistent UI Overlays */}
      <div className="absolute top-4 left-4 flex flex-col gap-1 z-30">
        <div className="text-xs text-zinc-500 uppercase tracking-widest font-bold">Pre-Termination Intel</div>
        <div className="text-xs text-amber-500 font-mono flex items-center gap-2">
          <span>{activeDim !== null ? 'ANALYZING RISK VECTOR...' : 'INITIALIZING SENSORS...'}</span>
          <span className="animate-pulse">▊</span>
        </div>
      </div>
      
      {/* Risk Score Summary */}
      <div className="absolute bottom-4 left-4 z-30 flex items-center gap-3 bg-zinc-950/80 p-2.5 rounded backdrop-blur-md border border-zinc-800/50">
        <div className="relative w-10 h-10 flex items-center justify-center">
          <svg viewBox="0 0 36 36" className="absolute inset-0 w-full h-full -rotate-90">
            <circle cx="18" cy="18" r="16" fill="none" stroke="#3f3f46" strokeWidth="2" />
            <motion.circle 
              cx="18" cy="18" r="16" 
              fill="none" 
              stroke="#ef4444" 
              strokeWidth="2" 
              strokeDasharray="100 100"
              initial={{ strokeDashoffset: 100 }}
              animate={inView ? { strokeDashoffset: 100 - 72 } : {}}
              transition={{ duration: 1.5, delay: 0.5, ease: "easeOut" }}
              style={{ filter: 'drop-shadow(0 0 4px rgba(239,68,68,0.8))' }}
            />
          </svg>
          <div className="text-[14px] font-[Orbitron] font-bold text-zinc-100">72</div>
        </div>
        <div className="flex flex-col">
          <div className="text-xs text-zinc-500 uppercase tracking-widest font-bold">Total Score</div>
          <div className="text-xs font-[Orbitron] font-bold tracking-widest text-red-500 drop-shadow-[0_0_5px_rgba(239,68,68,0.8)] mt-0.5">
            HIGH RISK
          </div>
        </div>
      </div>

      <div className="absolute top-4 right-4 flex items-center gap-2 z-30">
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 bg-amber-400" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500" />
        </span>
        <span className="text-xs uppercase font-bold tracking-widest text-amber-500 drop-shadow-[0_0_5px_rgba(245,158,11,0.8)]">
          Target Locked
        </span>
      </div>

    </div>
  )
}
