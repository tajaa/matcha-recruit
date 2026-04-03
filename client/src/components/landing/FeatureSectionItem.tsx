import { useRef } from 'react'
import { motion, useScroll, useTransform, useMotionValue, useMotionTemplate } from 'framer-motion'
import { DOT_GRID_BG } from './shared'
import { GlitchText } from '../GlitchText'

export interface Section {
  category: string
  accent: string
  title: string
  desc: string
  graphic: React.ComponentType
}

export function FeatureSectionItem({ section, idx }: { section: Section, idx: number }) {
  const reversed = idx % 2 === 1
  const Graphic = section.graphic
  const containerRef = useRef<HTMLDivElement>(null)
  
  // Parallax scroll effect
  const { scrollYProgress } = useScroll({
    target: containerRef,
    offset: ["start end", "end start"]
  })
  
  const yText = useTransform(scrollYProgress, [0, 1], [40, -40])
  const yGraphic = useTransform(scrollYProgress, [0, 1], [-40, 40])
  
  // Mouse spotlight & 3D tilt effect
  const mouseX = useMotionValue(0)
  const mouseY = useMotionValue(0)
  
  const handleMouseMove = ({ currentTarget, clientX, clientY }: React.MouseEvent) => {
    const { left, top } = currentTarget.getBoundingClientRect()
    mouseX.set(clientX - left)
    mouseY.set(clientY - top)
  }

  const rotateX = useTransform(mouseY, [0, 400], [5, -5])
  const rotateY = useTransform(mouseX, [0, 600], [-5, 5])

  return (
    <motion.section
      ref={containerRef}
      id={idx === 0 ? 'features' : undefined}
      initial={{ opacity: 0 }}
      whileInView={{ opacity: 1 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.8 }}
      onMouseMove={handleMouseMove}
      className="relative border-t border-zinc-700/40 py-16 sm:py-24 px-4 sm:px-8 overflow-x-hidden group"
    >
      {/* Interactive Spotlight */}
      <motion.div
        className="pointer-events-none absolute -inset-px opacity-0 transition duration-300 group-hover:opacity-100 z-0"
        style={{
          background: useMotionTemplate`
            radial-gradient(
              650px circle at ${mouseX}px ${mouseY}px,
              ${section.accent}15,
              transparent 80%
            )
          `
        }}
      />

      <div
        className="absolute inset-0 opacity-[0.04] pointer-events-none"
        style={{ backgroundImage: DOT_GRID_BG, backgroundSize: '24px 24px' }}
      />

      <div className="relative z-10 max-w-7xl mx-auto grid lg:grid-cols-2 gap-12 lg:gap-20 items-center">
        {/* Text with Parallax */}
        <motion.div
          style={{ y: yText }}
          className={reversed ? 'lg:order-2' : ''}
        >
          <div className="flex items-center gap-2 mb-5">
            <span className="h-1.5 w-1.5 rounded-full shadow-md" style={{ backgroundColor: section.accent, boxShadow: `0 0 10px ${section.accent}` }} />
            <span className="text-xs tracking-[0.3em] uppercase text-zinc-500">
              {section.category}
            </span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-bold uppercase tracking-wide text-zinc-100 mb-5 flex items-center gap-3">
            <GlitchText text={section.title} className="inline-block drop-shadow-lg" />
          </h2>
          <p className="text-base text-zinc-400 leading-relaxed max-w-md">
            {section.desc}
          </p>
        </motion.div>

        {/* Graphic with Parallax & 3D Tilt */}
        <motion.div
          style={{ y: yGraphic, perspective: 1000 }}
          className={reversed ? 'lg:order-1' : ''}
        >
          <motion.div
            style={{ rotateX, rotateY, boxShadow: `0 25px 50px -12px rgba(0,0,0,0.5)` }}
            transition={{ type: "spring", stiffness: 300, damping: 20 }}
            className="relative border border-zinc-800/60 bg-zinc-950/40 overflow-hidden rounded-xl group-hover:border-zinc-700/80 transition-colors duration-500"
          >
            {/* Inner Glow on Hover */}
            <motion.div
              className="absolute inset-0 opacity-0 group-hover:opacity-100 pointer-events-none mix-blend-overlay transition-opacity duration-500 z-10"
              style={{
                background: useMotionTemplate`
                  radial-gradient(
                    400px circle at ${mouseX}px ${mouseY}px,
                    ${section.accent}30,
                    transparent 80%
                  )
                `
              }}
            />
            <div className="relative z-0">
              <Graphic />
            </div>
          </motion.div>
        </motion.div>
      </div>
    </motion.section>
  )
}