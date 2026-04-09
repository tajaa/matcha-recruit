import { useRef, useState, useEffect } from 'react'
import { motion, useInView } from 'framer-motion'
import { SCAN_LINE_BG } from './shared'

/* ── Monte Carlo Distribution (Risk Assessment) ──────────────── */
export function MonteCarloDistribution() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { margin: '-80px' })
  const [iterations, setIterations] = useState(0)

  const barCount = 28
  const heights = Array.from({ length: barCount }, (_, i) => {
    // Log-normal distribution to show fat tail risk
    const x = (i / barCount) * 5 + 0.2
    const mu = 0
    const sigma = 0.8
    const val = (1 / (x * sigma * Math.sqrt(2 * Math.PI))) * Math.exp(-Math.pow(Math.log(x) - mu, 2) / (2 * sigma * sigma)) * 100
    // Emphasize the fat tail visually
    return val + (i > barCount * 0.5 ? (i / barCount) * 5 : 0)
  })
  const maxH = Math.max(...heights)

  useEffect(() => {
    if (!inView) {
      setIterations(0)
      return
    }
    let current = 0
    const target = 10000
    const interval = setInterval(() => {
      current += Math.floor(Math.random() * 400 + 200)
      if (current >= target) {
        setIterations(target)
        clearInterval(interval)
      } else {
        setIterations(current)
      }
    }, 50)
    return () => clearInterval(interval)
  }, [inView])

  const progress = iterations / 10000

  return (
    <div ref={ref} className="relative h-72 lg:h-80 overflow-hidden bg-zinc-950 flex items-center justify-center" style={{ backgroundImage: SCAN_LINE_BG }}>
      
      {/* 3D Container */}
      <motion.div 
        className="relative w-full sm:w-[120%] h-full flex items-end justify-center pb-12 gap-0.5 sm:gap-1.5"
        initial={{ rotateX: 45, rotateZ: -10, scale: 1.1, y: 40 }}
        animate={inView ? { rotateX: 15, rotateZ: 0, scale: 1, y: 10 } : {}}
        transition={{ duration: 1.5, ease: [0.16, 1, 0.3, 1] }}
        style={{ transformStyle: 'preserve-3d', perspective: '1000px' }}
      >
        {/* Background Grid */}
        <div 
          className="absolute inset-x-0 bottom-10 h-64 border-b border-emerald-500/20"
          style={{ 
            transform: 'rotateX(70deg) translateZ(-50px)', 
            backgroundImage: 'linear-gradient(rgba(16,185,129,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(16,185,129,0.1) 1px, transparent 1px)',
            backgroundSize: '20px 20px',
          }} 
        />

        {heights.map((h, i) => {
          // Add some jitter based on progress so it looks like it's building up
          const jitter = progress < 1 ? (Math.random() * 20 - 10) * (1 - progress) : 0
          const finalPct = Math.max(0, Math.min(100, (h / maxH) * 70 * progress + jitter))
          
          const isTail = i > barCount * 0.75
          const isWarning = i > barCount * 0.6 && !isTail
          
          let hue = 150 // emerald
          if (isTail) hue = 0 // red
          else if (isWarning) hue = 38 // amber
          
          const color = `hsl(${hue}, 70%, 50%)`
          const bg = `hsl(${hue}, 70%, ${isTail ? 45 : 30}%)`

          return (
            <div
              key={i}
              className="relative w-3 sm:w-4 h-full flex flex-col justify-end items-center z-10"
              style={{ transformStyle: 'preserve-3d' }}
            >
              {/* 3D Bar */}
              <motion.div
                className="w-full relative border-t border-l border-r opacity-90 transition-all duration-75"
                style={{
                  height: `${finalPct}%`,
                  backgroundColor: bg,
                  borderColor: color,
                  boxShadow: `0 0 15px ${color}40`,
                  transform: 'translateZ(10px)'
                }}
              >
                {/* Glowing Top Cap */}
                <div 
                  className="absolute top-0 left-0 right-0 h-1" 
                  style={{ backgroundColor: color, transform: 'translateY(-100%) rotateX(90deg)', transformOrigin: 'bottom' }} 
                />
              </motion.div>

              {/* Base shadow */}
              <div 
                className="absolute bottom-0 w-full h-4 rounded-full blur-md"
                style={{ backgroundColor: color, opacity: 0.4, transform: 'translateZ(0px)' }}
              />
            </div>
          )
        })}

        {/* Scan line sweeping across */}
        {inView && (
          <motion.div 
            className="absolute top-0 bottom-10 w-32 bg-gradient-to-r from-transparent via-emerald-400/20 to-transparent blur-md z-20 pointer-events-none"
            initial={{ left: '-20%' }}
            animate={{ left: '120%' }}
            transition={{ duration: 3, repeat: Infinity, ease: "linear", delay: 1 }}
            style={{ transform: 'translateZ(30px)' }}
          />
        )}
      </motion.div>

      {/* Threshold line (2D overlay) */}
      <motion.div
        className="absolute left-0 right-0 border-t border-dashed z-20 pointer-events-none"
        style={{
          top: '38%',
          borderColor: 'rgba(239,68,68,0.5)',
        }}
        initial={{ opacity: 0, x: -50 }}
        animate={inView ? { opacity: 1, x: 0 } : {}}
        transition={{ delay: 1.5, duration: 1 }}
      >
        <div className="absolute right-4 -top-4 flex items-center gap-2">
          <span className="text-[11px] text-red-400 uppercase font-bold tracking-widest drop-shadow-[0_0_5px_rgba(239,68,68,0.8)]">
            Critical Threshold
          </span>
          <span className="relative flex h-1.5 w-1.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-red-500" />
          </span>
        </div>
      </motion.div>

      {/* HUD Overlays */}
      <div className="absolute top-4 left-4 flex flex-col gap-1 z-30">
        <div className="text-xs text-zinc-500 uppercase tracking-widest font-bold">Monte Carlo Engine</div>
        <div className="text-xs text-emerald-400 font-mono">
          ITERATIONS: {iterations.toLocaleString().padStart(6, '0')} / 10,000
        </div>
        {progress === 1 && (
          <motion.div 
            initial={{ opacity: 0 }} 
            animate={{ opacity: 1 }} 
            className="text-[11px] text-emerald-500 mt-1 uppercase tracking-widest"
          >
            [ Simulation Complete ]
          </motion.div>
        )}
      </div>

      <div className="absolute bottom-4 left-4 flex flex-col gap-1.5 z-30 bg-zinc-950/80 p-2 rounded backdrop-blur-md border border-zinc-800/50">
        <div className="flex items-center gap-2 text-[11px] font-mono">
          <span className="w-1.5 h-1.5 bg-emerald-500 border border-emerald-400 shadow-[0_0_5px_rgba(16,185,129,0.5)]" />
          <span className="text-zinc-400 w-6">P50:</span> <span className="text-zinc-200">$142,000</span>
        </div>
        <div className="flex items-center gap-2 text-[11px] font-mono">
          <span className="w-1.5 h-1.5 bg-amber-500 border border-amber-400 shadow-[0_0_5px_rgba(245,158,11,0.5)]" />
          <span className="text-zinc-400 w-6">P90:</span> <span className="text-zinc-200">$890,000</span>
        </div>
        <div className="flex items-center gap-2 text-[11px] font-mono">
          <span className="w-1.5 h-1.5 bg-red-500 border border-red-400 shadow-[0_0_5px_rgba(239,68,68,0.5)]" />
          <span className="text-zinc-400 w-6">P99:</span> <span className="text-zinc-200">$2.4M</span>
        </div>
      </div>
      
      <div className="absolute bottom-2 right-4 text-xs text-zinc-600 font-mono">
        ANNUAL LOSS EXPOSURE →
      </div>
    </div>
  )
}