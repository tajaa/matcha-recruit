import { useRef, useState, useEffect } from 'react'
import { motion, useInView, AnimatePresence } from 'framer-motion'
import { SCAN_LINE_BG, PATTERN_INCIDENTS } from './shared'

/* ── Pattern Grid (Incident Reports) ──────────────────────────── */
export function PatternGrid() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { margin: '-80px' })
  const rows = 8
  const cols = 12
  const epicenter = 42 // row 3, col 6
  const epicRow = Math.floor(epicenter / cols)
  const epicCol = epicenter % cols

  // We'll dynamically determine incidents to cluster around epicenter
  const incidentSet = new Set([
    epicenter, epicenter - 1, epicenter + 1, 
    epicenter - cols, epicenter - cols + 1,
    epicenter + cols, epicenter + cols - 1,
    epicenter + cols * 2, epicenter + cols * 2 - 1,
    epicenter - cols * 2 + 2, epicenter - 2
  ])

  const [scanLine, setScanLine] = useState(-5)
  const [pulse, setPulse] = useState(0)

  useEffect(() => {
    if (!inView) {
      setScanLine(-5)
      return
    }
    const interval = setInterval(() => {
      setScanLine(prev => {
        if (prev > cols + 5) {
          setPulse(p => p + 1)
          return -2
        }
        return prev + 1
      })
    }, 250)
    return () => clearInterval(interval)
  }, [inView])

  return (
    <div ref={ref} className="relative h-80 lg:h-96 overflow-hidden bg-zinc-950 flex flex-col items-center justify-center p-4"
      style={{ backgroundImage: SCAN_LINE_BG, perspective: '1200px' }}
    >
      {/* 3D Isometric Container */}
      <motion.div 
        className="relative flex items-center justify-center w-full max-w-[360px]"
        initial={{ rotateX: 65, rotateZ: -35, scale: 0.8, y: 50, opacity: 0 }}
        animate={inView ? { rotateX: 55, rotateZ: -35, scale: 1.1, y: 0, opacity: 1 } : {}}
        transition={{ duration: 1.5, ease: "easeOut" }}
        style={{ transformStyle: 'preserve-3d' }}
      >
        
        {/* Base Floor Grid */}
        <div 
          className="absolute inset-[-40px] border border-amber-500/20 bg-zinc-950/80 backdrop-blur-sm"
          style={{ 
            backgroundImage: 'linear-gradient(rgba(245,158,11,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(245,158,11,0.1) 1px, transparent 1px)',
            backgroundSize: '30px 30px',
            transform: 'translateZ(-1px)',
            boxShadow: '0 0 40px rgba(0,0,0,0.8), inset 0 0 30px rgba(245,158,11,0.05)'
          }} 
        />

        {/* The Grid of Nodes */}
        <div 
          className="grid gap-2 relative z-10" 
          style={{ gridTemplateColumns: `repeat(${cols}, 1fr)`, transformStyle: 'preserve-3d' }}
        >
          {Array.from({ length: rows * cols }, (_, i) => {
            const row = Math.floor(i / cols)
            const col = i % cols
            const distToEpicenter = Math.sqrt((row - epicRow) ** 2 + (col - epicCol) ** 2)
            const isIncident = incidentSet.has(i)
            
            // Interaction with scan line
            const distToScan = Math.abs(col - scanLine)
            const isScanning = distToScan < 1.5

            // Determine height and color
            let h = 4 // Base height
            let color = '#3f3f46' // zinc-700
            let bg = 'rgba(63, 63, 70, 0.4)'
            let shadow = 'none'
            let opacity = 0.5

            if (isIncident) {
              h = 24 + Math.random() * 8
              color = '#f59e0b' // amber-500
              bg = 'rgba(245, 158, 11, 0.8)'
              shadow = '0 0 15px rgba(245,158,11,0.6)'
              opacity = 0.9
            }

            if (isScanning && !isIncident) {
              h = 8
              color = '#fbbf24' // amber-400
              bg = 'rgba(251, 191, 36, 0.6)'
              opacity = 0.8
            } else if (isScanning && isIncident) {
              h += 10
              color = '#ef4444' // red-500 for a split second
              bg = 'rgba(239, 68, 68, 0.9)'
              shadow = '0 0 25px rgba(239,68,68,0.8)'
            }

            // Ripple effect on completed scan
            const rippleDist = Math.abs(distToEpicenter - (pulse * 3 % 15))
            if (rippleDist < 1 && !isIncident && !isScanning) {
              h = 12
              color = '#d97706' // amber-600
              bg = 'rgba(217, 119, 6, 0.5)'
            }

            return (
              <div
                key={i}
                className="relative w-4 h-4 flex items-center justify-center transition-all duration-300"
                style={{ transformStyle: 'preserve-3d' }}
              >
                {/* 3D Pillar */}
                <div 
                  className="absolute bottom-0 w-3 border-t border-l border-r transition-all duration-300 origin-bottom"
                  style={{
                    height: `${h}px`,
                    backgroundColor: bg,
                    borderColor: color,
                    boxShadow: shadow,
                    transform: 'rotateX(-90deg) translateZ(0px)',
                    opacity: opacity,
                  }}
                >
                  {/* Top Cap */}
                  <div 
                    className="absolute top-0 left-0 right-0 h-3 border border-transparent transition-all duration-300" 
                    style={{ 
                      backgroundColor: color, 
                      transform: 'translateY(-100%) rotateX(90deg)', 
                      transformOrigin: 'bottom',
                      boxShadow: isIncident ? 'inset 0 0 5px rgba(255,255,255,0.5)' : 'none'
                    }} 
                  />
                </div>
              </div>
            )
          })}
        </div>

        {/* Scanning Laser Beam */}
        <motion.div 
          className="absolute top-[-20px] bottom-[-20px] w-1 bg-amber-400 z-20 pointer-events-none"
          style={{ 
            boxShadow: '0 0 30px #f59e0b, 0 0 60px #f59e0b',
            transform: 'translateZ(15px)',
            left: `${(scanLine / cols) * 100}%`
          }}
          transition={{ duration: 0.25, ease: "linear" }}
        />
        
        {/* Ripple Rings around Epicenter */}
        {[0, 1, 2].map(ring => (
          <motion.div
            key={ring}
            className="absolute rounded-full border-2 border-amber-500/40 pointer-events-none z-0"
            style={{
              width: '40px',
              height: '40px',
              left: `${(epicCol / (cols - 1)) * 100}%`,
              top: `${(epicRow / (rows - 1)) * 100}%`,
              x: '-50%',
              y: '-50%',
              transform: 'translateZ(1px)',
              boxShadow: '0 0 20px rgba(245,158,11,0.2), inset 0 0 20px rgba(245,158,11,0.2)'
            }}
            animate={{
              scale: [1, 5 + ring * 2],
              opacity: [0.8, 0],
              borderWidth: ['2px', '8px']
            }}
            transition={{
              duration: 3,
              repeat: Infinity,
              delay: ring * 1,
              ease: "easeOut"
            }}
          />
        ))}
      </motion.div>

      {/* Target Lock UI */}
      <AnimatePresence>
        {scanLine === epicCol + 1 && (
          <motion.div
            className="absolute top-1/4 right-10 flex flex-col items-end z-30"
            initial={{ opacity: 0, x: 20, scale: 0.9 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9, transition: { duration: 0.2 } }}
          >
            <svg width="40" height="40" viewBox="0 0 100 100" className="text-red-500 mb-2 drop-shadow-[0_0_8px_rgba(239,68,68,0.8)]">
              <path d="M 10 10 L 30 10 M 10 10 L 10 30 M 90 10 L 70 10 M 90 10 L 90 30 M 10 90 L 30 90 M 10 90 L 10 70 M 90 90 L 70 90 M 90 90 L 90 70" fill="none" stroke="currentColor" strokeWidth="4" />
              <circle cx="50" cy="50" r="25" fill="none" stroke="currentColor" strokeWidth="2" strokeDasharray="4 4" className="animate-[spin_4s_linear_infinite]" />
              <circle cx="50" cy="50" r="4" fill="currentColor" className="animate-pulse" />
            </svg>
            <div className="text-[10px] text-red-400 font-[Orbitron] font-bold tracking-widest uppercase bg-zinc-950/80 px-2 py-1 border border-red-500/30 rounded backdrop-blur-sm">
              Cluster Lock
            </div>
            <div className="text-[8px] font-mono text-red-300/80 mt-1 text-right">
              LAT: 34.05 // LNG: -118.24<br/>
              SEVERITY: CRITICAL
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* HUD Overlays */}
      <div className="absolute top-4 left-4 flex flex-col gap-1 z-30">
        <div className="text-[8px] text-zinc-500 uppercase tracking-widest font-bold">Pattern Detection Grid</div>
        <div className="text-[10px] text-amber-500 font-mono flex items-center gap-2">
          <span>{scanLine >= 0 && scanLine < cols ? `SCANNING SECTOR ${scanLine.toString().padStart(2, '0')}...` : 'RECALIBRATING...'}</span>
          {scanLine >= 0 && scanLine < cols && <span className="animate-pulse">▊</span>}
        </div>
      </div>
      
      <div className="absolute bottom-4 left-4 z-30 bg-zinc-950/80 p-2.5 rounded backdrop-blur-md border border-zinc-800/50 shadow-[0_5px_15px_rgba(0,0,0,0.5)]">
        <div className="text-[8px] text-zinc-500 uppercase tracking-widest mb-1.5 font-bold">Anomaly Stats</div>
        <div className="flex items-center gap-4">
          <div>
            <div className="text-[14px] font-[Orbitron] font-bold text-amber-500">{incidentSet.size}</div>
            <div className="text-[7px] text-zinc-400 uppercase">Incidents</div>
          </div>
          <div className="w-px h-6 bg-zinc-800" />
          <div>
            <div className="text-[14px] font-[Orbitron] font-bold text-red-500">1</div>
            <div className="text-[7px] text-zinc-400 uppercase">Cluster</div>
          </div>
          <div className="w-px h-6 bg-zinc-800" />
          <div>
            <div className="text-[10px] font-mono font-bold text-emerald-400 mt-1">98.4%</div>
            <div className="text-[7px] text-zinc-400 uppercase mt-0.5">Confidence</div>
          </div>
        </div>
      </div>
    </div>
  )
}
