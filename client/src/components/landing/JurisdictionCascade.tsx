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
    <div ref={ref} className="relative h-[400px] lg:h-[460px] overflow-hidden bg-zinc-950 flex flex-col items-center justify-center" style={{ backgroundImage: WIRE_MESH_BG, backgroundSize: WIRE_MESH_SIZE, perspective: '1000px' }}>

      {/* Core Isometric Container */}
      <motion.div
        className="relative w-full max-w-[460px]"
        initial={{ rotateX: 60, rotateZ: -20, y: 50, opacity: 0 }}
        animate={inView ? { rotateX: 60, rotateZ: -20, y: 10, opacity: 1 } : {}}
        transition={{ duration: 1.2, ease: "easeOut" }}
        style={{ transformStyle: 'preserve-3d' }}
      >

        {/* Background data streams */}
        <div className="absolute top-0 bottom-0 left-10 w-px bg-zinc-700/30" style={{ transform: 'translateZ(-80px)' }} />
        <div className="absolute top-0 bottom-0 right-10 w-px bg-zinc-700/30" style={{ transform: 'translateZ(-80px)' }} />

        <motion.div
          className="absolute left-10 w-px h-20 bg-gradient-to-b from-transparent via-zinc-500 to-transparent"
          style={{ transform: 'translateZ(-80px)' }}
          animate={{ top: ['-20%', '120%'] }}
          transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
        />
        <motion.div
          className="absolute right-10 w-px h-20 bg-gradient-to-b from-transparent via-zinc-500 to-transparent"
          style={{ transform: 'translateZ(-80px)' }}
          animate={{ top: ['-20%', '120%'] }}
          transition={{ duration: 2.5, repeat: Infinity, ease: "linear", delay: 1 }}
        />

        {tiers.map((tier, tIdx) => (
          <motion.div
            key={tier.id}
            className="relative w-full flex flex-col items-center mb-8 last:mb-0"
            style={{
              transform: `translateZ(${tIdx * 40}px)`,
              transformStyle: 'preserve-3d'
            }}
            initial={{ opacity: 0, y: -20 }}
            animate={inView ? { opacity: 1, y: 0 } : {}}
            transition={{ delay: tIdx * 0.2 + 0.4, duration: 0.8 }}
          >
            {/* Glass Pane Background */}
            <div
              className="absolute inset-0 bg-zinc-900/60 border border-zinc-700/40 rounded-lg scale-105"
              style={{
                boxShadow: '0 10px 30px -10px rgba(0,0,0,0.8)',
                transform: 'translateZ(-1px)'
              }}
            />

            {/* Scanning Line Effect */}
            {activeItem?.tier === tIdx && (
              <motion.div
                className="absolute inset-x-0 h-[2px] bg-zinc-400/60 z-20"
                initial={{ top: '0%', opacity: 0 }}
                animate={{ top: '100%', opacity: [0, 1, 1, 0] }}
                transition={{ duration: 2, ease: "linear" }}
              />
            )}

            <div className="relative z-10 w-full px-4 py-4 flex flex-col items-center">
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
                          ? 'border-amber-500/60 bg-amber-500/10 text-zinc-100'
                          : 'border-zinc-700/50 bg-zinc-900/80 text-zinc-500'
                      }`}
                      style={{
                        transform: isActive ? 'translateZ(15px) scale(1.1)' : 'translateZ(0px) scale(1)',
                      }}
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
            </div>
          </motion.div>
        ))}
      </motion.div>

      {/* Floating Data Nodes (Particles) */}
      {inView && Array.from({ length: 8 }).map((_, i) => (
        <motion.div
          key={`particle-${i}`}
          className="absolute w-1 h-1 bg-zinc-500/30 rounded-full"
          initial={{
            x: Math.random() * 300 - 150,
            y: Math.random() * 300 - 150,
            opacity: 0,
            scale: 0
          }}
          animate={{
            y: [null, Math.random() * 300 - 150],
            opacity: [0, 1, 0],
            scale: [0, 1.5, 0]
          }}
          transition={{
            duration: 3 + Math.random() * 4,
            repeat: Infinity,
            delay: Math.random() * 2
          }}
        />
      ))}

      {/* HUD Overlays */}
      <div className="absolute bottom-4 left-4 flex flex-col gap-1">
        <div className="text-[10px] text-zinc-500 uppercase tracking-widest">Query Layer</div>
        <div className="text-xs text-zinc-300 font-mono flex items-center gap-2">
          <span>{activeItem ? `[${tiers[activeItem.tier].level}] SELECT * FROM rules` : 'AWAITING QUERY...'}</span>
          {activeItem && <span className="animate-pulse">▊</span>}
        </div>
      </div>

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
