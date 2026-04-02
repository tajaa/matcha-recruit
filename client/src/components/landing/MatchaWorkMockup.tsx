import { useRef, useState, useEffect } from 'react'
import { motion, useInView } from 'framer-motion'

export function MatchaWorkMockup() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { margin: '-80px' })
  const [typingStep, setTypingStep] = useState(0)

  useEffect(() => {
    if (!inView) {
      setTypingStep(0)
      return
    }
    const t1 = setTimeout(() => setTypingStep(1), 800)
    const t2 = setTimeout(() => setTypingStep(2), 2000)
    const t3 = setTimeout(() => setTypingStep(3), 4000)
    return () => {
      clearTimeout(t1)
      clearTimeout(t2)
      clearTimeout(t3)
    }
  }, [inView])

  return (
    <div ref={ref} className="relative w-full max-w-4xl mx-auto rounded-xl overflow-hidden border border-zinc-700/50 bg-zinc-950 shadow-2xl flex flex-col md:flex-row h-[400px] font-sans">
      
      {/* Sidebar */}
      <div className="hidden md:flex flex-col w-64 border-r border-zinc-800/50 bg-zinc-900/40 p-4">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_8px_#10b981]" />
            <span className="text-[11px] font-bold tracking-widest text-zinc-200 uppercase">Matcha Work</span>
          </div>
          <div className="w-5 h-5 rounded flex items-center justify-center border border-zinc-700/50 text-zinc-400">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14"/></svg>
          </div>
        </div>
        
        <div className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest mb-3">Recent Threads</div>
        <div className="flex flex-col gap-1.5">
          <div className="px-3 py-2 rounded-md bg-zinc-800/60 text-xs text-zinc-200 border border-zinc-700/50 shadow-sm flex items-center gap-2">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-emerald-400"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
            Overtime Compliance CA
          </div>
          <div className="px-3 py-2 rounded-md text-xs text-zinc-400 hover:bg-zinc-800/30 transition-colors flex items-center gap-2">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-zinc-500"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            Offer Letter: SWE
          </div>
          <div className="px-3 py-2 rounded-md text-xs text-zinc-400 hover:bg-zinc-800/30 transition-colors flex items-center gap-2">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-zinc-500"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>
            Handbook Update Q3
          </div>
        </div>
      </div>
      
      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col bg-zinc-950/80 relative">
        {/* Header */}
        <div className="h-14 border-b border-zinc-800/50 flex items-center px-6 justify-between bg-zinc-900/20">
          <div className="flex items-center gap-3">
            <div className="text-sm font-semibold text-zinc-200">Overtime Compliance CA</div>
            <span className="px-1.5 py-0.5 rounded-full bg-zinc-800 text-[9px] text-zinc-400 border border-zinc-700">Project</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-2.5 py-1 rounded border border-emerald-500/20 flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              gemini-3-flash-preview
            </div>
          </div>
        </div>

        {/* Chat Messages */}
        <div className="flex-1 p-6 overflow-y-auto flex flex-col gap-6">
          
          <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={typingStep >= 1 ? { opacity: 1, y: 0 } : { opacity: 0, y: 10 }}
            className="flex justify-end"
          >
            <div className="bg-emerald-600/10 border border-emerald-500/20 text-zinc-200 text-sm px-4 py-3 rounded-2xl rounded-tr-sm max-w-[80%] shadow-sm">
              What are the overtime exemption requirements for salaried employees in California vs. federal FLSA?
            </div>
          </motion.div>

          <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={typingStep >= 2 ? { opacity: 1, y: 0 } : { opacity: 0, y: 10 }}
            className="flex justify-start gap-3"
          >
            <div className="w-6 h-6 rounded bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center shrink-0 mt-1">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/><line x1="8" y1="16" x2="8" y2="16"/><line x1="16" y1="16" x2="16" y2="16"/></svg>
            </div>
            
            <div className="bg-zinc-800/40 border border-zinc-700/50 text-zinc-300 text-sm px-5 py-4 rounded-2xl rounded-tl-sm max-w-[85%] leading-relaxed shadow-sm">
              {typingStep === 2 && (
                <div className="flex items-center gap-2 text-zinc-400 font-mono text-xs">
                  <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse" /> Analyzing regulations...
                </div>
              )}
              {typingStep >= 3 && (
                <div className="space-y-3">
                  <p>Analyzing federal FLSA § 13(a)(1) against CA Labor Code § 515...</p>
                  
                  <div className="grid grid-cols-2 gap-3 mt-3">
                    <div className="p-3 bg-zinc-900/50 rounded border border-zinc-700/50">
                      <div className="text-[10px] uppercase tracking-widest text-zinc-500 mb-1">Federal FLSA</div>
                      <div className="font-mono text-zinc-300">$35,568/yr</div>
                      <div className="text-xs text-zinc-500 mt-1">Primary duty test</div>
                    </div>
                    <div className="p-3 bg-emerald-900/20 rounded border border-emerald-500/30">
                      <div className="text-[10px] uppercase tracking-widest text-emerald-500/80 mb-1">California</div>
                      <div className="font-mono text-emerald-400">$66,560/yr</div>
                      <div className="text-xs text-emerald-500/70 mt-1">&gt;50% time on exempt duties</div>
                    </div>
                  </div>

                  <p className="pt-2">California applies a stricter salary threshold and duties test.</p>
                  
                  <div className="mt-3 p-3 bg-emerald-500/10 border-l-2 border-emerald-500 rounded-r">
                    <div className="text-emerald-500 text-[10px] uppercase tracking-widest font-bold mb-1">Recommendation</div>
                    <div className="text-zinc-300">Apply the CA standard for all CA-based employees to ensure compliance.</div>
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        </div>

        {/* Input Area */}
        <div className="p-5 border-t border-zinc-800/50 bg-zinc-900/30">
          <div className="flex items-center gap-3 bg-zinc-950 border border-zinc-700/50 hover:border-zinc-600 transition-colors rounded-xl px-4 py-3 shadow-inner">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-zinc-500"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
            <div className="flex-1 text-sm text-zinc-500">Message Matcha...</div>
            <div className="w-8 h-8 rounded-lg bg-emerald-500 flex items-center justify-center shadow-[0_0_10px_rgba(16,185,129,0.3)]">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
              </svg>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
