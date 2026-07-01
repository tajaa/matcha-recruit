import { useRef, useState, useEffect } from 'react'
import { motion, useInView } from 'framer-motion'
import { WIRE_MESH_BG, WIRE_MESH_SIZE } from './shared'

/* ── Jurisdiction Cascade (Compliance Engine) ─────────────────── */
export function JurisdictionCascade() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { margin: '-80px' })

  const tiers = [
    { id: 'fed', level: 'FEDERAL', items: ['FLSA', 'OSHA', 'FMLA', 'ADA', 'EEOC'] },
    { id: 'state', level: 'STATE', items: ['CA FEHA', 'NY WARN', 'TX TWC', 'FL SB', 'WA PFML'] },
    { id: 'local', level: 'LOCAL', items: ['SF HCSO', 'NYC ESL', 'LA MWO', 'SEA PSL', 'CHI FWW'] },
  ]

  const [activeItem, setActiveItem] = useState<{ tier: number, itemIndex: number } | null>({ tier: 0, itemIndex: 2 })

  useEffect(() => {
    if (!inView) return
    const interval = setInterval(() => {
      setActiveItem({
        tier: Math.floor(Math.random() * tiers.length),
        itemIndex: Math.floor(Math.random() * 5)
      })
    }, 2500)
    return () => clearInterval(interval)
  }, [inView, tiers.length])

  return (
    <div ref={ref} className="relative h-[400px] lg:h-[460px] overflow-hidden bg-zinc-950 flex flex-col items-center justify-center px-6" style={{ backgroundImage: WIRE_MESH_BG, backgroundSize: WIRE_MESH_SIZE }}>

      {/* Floating Data Nodes (Particles) — kept subtle, behind the cards */}
      {inView && Array.from({ length: 6 }).map((_, i) => (
        <motion.div
          key={`particle-${i}`}
          className="absolute w-1 h-1 bg-zinc-500/20 rounded-full pointer-events-none"
          style={{ zIndex: 0 }}
          initial={{
            x: Math.random() * 300 - 150,
            y: Math.random() * 300 - 150,
            opacity: 0,
            scale: 0
          }}
          animate={{
            y: [null, Math.random() * 300 - 150],
            opacity: [0, 0.6, 0],
            scale: [0, 1.2, 0]
          }}
          transition={{
            duration: 3 + Math.random() * 4,
            repeat: Infinity,
            delay: Math.random() * 2
          }}
        />
      ))}

      {/* Flat, narrowing stack — Federal is widest (broadest scope), Local is
          narrowest (most specific), so the hierarchy reads at a glance
          instead of relying on a hard-to-parse isometric tilt. */}
      <motion.div
        className="relative z-10 w-full max-w-[460px] flex flex-col items-center gap-5"
        initial={{ opacity: 0, y: 20 }}
        animate={inView ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.8, ease: 'easeOut' }}
      >
        {tiers.map((tier, tIdx) => (
          <motion.div
            key={tier.id}
            className="relative rounded-lg border border-zinc-700/40 bg-zinc-900/70 px-4 py-4 flex flex-col items-center overflow-hidden"
            style={{
              width: `${100 - tIdx * 9}%`,
              boxShadow: '0 10px 30px -10px rgba(0,0,0,0.7)',
            }}
            initial={{ opacity: 0, y: -16 }}
            animate={inView ? { opacity: 1, y: 0 } : {}}
            transition={{ delay: tIdx * 0.15 + 0.3, duration: 0.6 }}
          >
            {/* Scanning line, only over the currently active tier */}
            {activeItem?.tier === tIdx && (
              <motion.div
                className="absolute inset-x-0 h-[2px] bg-zinc-400/50 z-20"
                initial={{ top: '0%', opacity: 0 }}
                animate={{ top: '100%', opacity: [0, 1, 1, 0] }}
                transition={{ duration: 1.8, ease: 'linear' }}
              />
            )}

            <div className="flex items-center gap-2 mb-3">
              <div className={`h-1.5 w-1.5 rounded-full ${activeItem?.tier === tIdx ? 'bg-amber-500 animate-pulse' : 'bg-zinc-700'}`} />
              <span className="text-sm font-[Orbitron] font-bold tracking-widest uppercase text-zinc-400">
                {tier.level}
              </span>
            </div>

            <div className="flex gap-2 flex-wrap justify-center">
              {tier.items.map((item, iIdx) => {
                const isActive = activeItem?.tier === tIdx && activeItem?.itemIndex === iIdx
                return (
                  <motion.div
                    key={item}
                    className={`relative px-3 py-1.5 text-xs font-mono border rounded transition-all duration-300 ${
                      isActive
                        ? 'border-amber-500/60 bg-amber-500/10 text-zinc-100 scale-110'
                        : 'border-zinc-700/50 bg-zinc-900/80 text-zinc-500'
                    }`}
                  >
                    {item}
                    {isActive && (
                      <motion.div
                        className="absolute inset-0 border border-amber-500/50 rounded"
                        initial={{ opacity: 1, scale: 1 }}
                        animate={{ opacity: 0, scale: 1.5 }}
                        transition={{ duration: 1, repeat: Infinity }}
                      />
                    )}
                  </motion.div>
                )
              })}
            </div>
          </motion.div>
        ))}
      </motion.div>

      {/* HUD — status only. No query/engine internals surfaced here. */}
      <div className="absolute top-4 right-4 flex items-center gap-2">
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-500 opacity-75" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500" />
        </span>
        <span className="text-[10px] text-zinc-500 uppercase font-bold tracking-widest">Live Engine</span>
      </div>
    </div>
  )
}
