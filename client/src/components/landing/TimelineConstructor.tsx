import { useRef } from 'react'
import { useInView } from 'framer-motion'
import { SCAN_LINE_BG } from './shared'

/* ── Timeline Constructor (ER Copilot) ────────────────────────── */
export function TimelineConstructor() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })
  const nodes = [
    { label: 'Complaint Filed', status: 'complete' },
    { label: 'Docs Analyzed', status: 'complete' },
    { label: 'Discrepancy Found', status: 'alert' },
    { label: 'Report Generated', status: 'complete' },
  ]

  return (
    <div ref={ref} className="relative h-72 lg:h-80 flex items-center overflow-hidden px-4"
      style={{ backgroundImage: SCAN_LINE_BG }}
    >
      <div className="w-full">
        {/* Main timeline line */}
        <div className="relative mx-8">
          <div
            className="absolute top-1/2 left-0 h-px bg-gradient-to-r from-amber-500/60 via-amber-500/40 to-zinc-700 transition-all duration-1500"
            style={{
              width: inView ? '100%' : '0%',
              transitionDuration: '2s',
              transitionTimingFunction: 'cubic-bezier(0.16, 1, 0.3, 1)',
            }}
          />

          <div className="relative flex justify-between">
            {nodes.map((node, i) => (
              <div
                key={i}
                className="flex flex-col items-center gap-3 transition-all"
                style={{
                  opacity: inView ? 1 : 0,
                  transform: inView ? 'translateY(0)' : 'translateY(16px)',
                  transitionDuration: '600ms',
                  transitionDelay: `${i * 400 + 400}ms`,
                }}
              >
                <span className="text-[8px] text-zinc-500 uppercase text-center w-20">
                  {node.label}
                </span>
                <div className="relative">
                  <div
                    className={`h-4 w-4 rounded-full border-2 ${
                      node.status === 'alert'
                        ? 'border-amber-500 bg-amber-500/20'
                        : 'border-zinc-500 bg-zinc-800'
                    }`}
                  />
                  {node.status === 'alert' && (
                    <div className="absolute inset-0 rounded-full border-2 border-amber-500 animate-ping opacity-30" />
                  )}
                </div>
                <span
                  className="text-[7px] uppercase"
                  style={{ color: node.status === 'alert' ? '#f59e0b' : '#52525b' }}
                >
                  {node.status === 'alert' ? '! FLAGGED' : 'VERIFIED'}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Animated document scan */}
        <div
          className="mt-8 mx-8 flex gap-3 transition-opacity duration-700"
          style={{ opacity: inView ? 1 : 0, transitionDelay: '2s' }}
        >
          {['policy_doc.pdf', 'witness_stmt.docx', 'email_chain.eml'].map((doc, i) => (
            <div key={doc} className="flex items-center gap-1.5 px-2 py-1 border border-zinc-800 bg-zinc-900/80">
              <div className="h-1 w-1 rounded-full bg-amber-500" style={{ animation: `pulse 2s ${i * 0.4}s infinite` }} />
              <span className="text-[7px] text-zinc-500">{doc}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}