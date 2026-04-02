import { useRef, useState, useEffect } from 'react'
import { useInView } from 'framer-motion'
import { SCAN_LINE_BG } from './shared'

/* ── Typing Terminal (Matcha Work) ────────────────────────────── */
export function TerminalTyping() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })
  const [queryIdx, setQueryIdx] = useState(0)
  const [responseIdx, setResponseIdx] = useState(0)
  const t3Ref = useRef<ReturnType<typeof setInterval> | null>(null)
  const query = '> What are the overtime exemption requirements for salaried employees in California vs. federal FLSA?'
  const response = 'Analyzing federal FLSA § 13(a)(1) against CA Labor Code § 515... California applies a stricter salary threshold ($66,560/yr vs federal $35,568). The duties test also diverges: CA requires >50% time on exempt duties while federal uses the primary duty test. Recommendation: Apply CA standard for all CA-based employees.'

  useEffect(() => {
    if (!inView) return
    const t1 = setInterval(() => {
      setQueryIdx(prev => {
        if (prev >= query.length) { clearInterval(t1); return prev }
        return prev + 1
      })
    }, 35)
    const t2 = setTimeout(() => {
      t3Ref.current = setInterval(() => {
        setResponseIdx(prev => {
          if (prev >= response.length) { clearInterval(t3Ref.current!); t3Ref.current = null; return prev }
          return prev + 2
        })
      }, 15)
    }, query.length * 35 + 500)
    return () => { clearInterval(t1); clearTimeout(t2); if (t3Ref.current) clearInterval(t3Ref.current) }
  }, [inView])

  return (
    <div ref={ref} className="max-w-2xl mx-auto border border-zinc-800 bg-zinc-950/80 overflow-hidden" style={{ backgroundImage: SCAN_LINE_BG }}>
      <div className="flex items-center gap-2 px-4 py-2 border-b border-zinc-800 bg-zinc-900/50">
        <span className="h-2 w-2 rounded-full bg-red-500/50" />
        <span className="h-2 w-2 rounded-full bg-amber-500/50" />
        <span className="h-2 w-2 rounded-full bg-emerald-500/50" />
        <span className="ml-2 text-[8px] text-zinc-600 uppercase">matcha-work // compliance-query</span>
      </div>
      <div className="p-5 min-h-[180px]">
        <p className="text-xs text-emerald-400 leading-relaxed">
          {query.slice(0, queryIdx)}
          {queryIdx < query.length && <span className="animate-pulse">▊</span>}
        </p>
        {queryIdx >= query.length && responseIdx > 0 && (
          <p className="text-xs text-zinc-400 leading-relaxed mt-4">
            {response.slice(0, responseIdx)}
            {responseIdx < response.length && <span className="animate-pulse text-amber-500">▊</span>}
          </p>
        )}
      </div>
    </div>
  )
}