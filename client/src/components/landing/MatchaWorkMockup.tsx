import { useRef, useState, useEffect } from 'react'
import { motion, useInView, AnimatePresence } from 'framer-motion'

const CANDIDATES = [
  { name: 'Maya Chen', role: 'Sr. Engineer @ Stripe', score: 94, skills: ['React', 'Go', 'K8s'], loc: 'SF', status: 'completed', interviewScore: 92 },
  { name: 'James Park', role: 'Staff Eng @ Airbnb', score: 91, skills: ['Python', 'AWS', 'ML'], loc: 'SF', status: 'completed', interviewScore: 87 },
  { name: 'Priya Sharma', role: 'SDE III @ Amazon', score: 88, skills: ['Java', 'Distributed', 'React'], loc: 'Seattle', status: 'sent', interviewScore: null },
  { name: 'Alex Rivera', role: 'Engineer @ Notion', score: 85, skills: ['TypeScript', 'Postgres'], loc: 'Remote', status: 'pending', interviewScore: null },
]

const fade = { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 }, exit: { opacity: 0, y: -4 } }

export function MatchaWorkMockup() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { margin: '-60px' })
  const [step, setStep] = useState(0)

  useEffect(() => {
    if (!inView) { setStep(0); return }
    const timers = [
      setTimeout(() => setStep(1), 600),
      setTimeout(() => setStep(2), 1800),
      setTimeout(() => setStep(3), 3200),
      setTimeout(() => setStep(4), 4800),
    ]
    return () => timers.forEach(clearTimeout)
  }, [inView])

  return (
    <div ref={ref} className="relative w-full max-w-5xl mx-auto rounded-xl overflow-hidden border border-zinc-700/50 bg-zinc-950 shadow-2xl flex flex-col md:flex-row h-[520px] font-sans">

      {/* Sidebar */}
      <div className="hidden md:flex flex-col w-56 border-r border-zinc-800/50 bg-zinc-900/40 p-4">
        <div className="flex items-center gap-2 mb-6">
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_8px_#10b981]" />
          <span className="text-[11px] font-bold tracking-widest text-zinc-200 uppercase">Matcha Work</span>
        </div>

        <div className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest mb-2">Projects</div>
        <div className="flex flex-col gap-1">
          <div className="px-3 py-2 rounded-md bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-300 flex items-center gap-2">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="19" y1="8" x2="19" y2="14"/><line x1="22" y1="11" x2="16" y2="11"/></svg>
            Sr. Engineer — SF
          </div>
          <div className="px-3 py-2 rounded-md text-xs text-zinc-500 flex items-center gap-2">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            Q3 Handbook
          </div>
          <div className="px-3 py-2 rounded-md text-xs text-zinc-500 flex items-center gap-2">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
            CA Compliance
          </div>
        </div>

        <div className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest mt-5 mb-2">Threads</div>
        <div className="flex flex-col gap-1">
          <div className="px-3 py-2 rounded-md text-xs text-zinc-500 flex items-center gap-2">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
            Overtime policy
          </div>
        </div>
      </div>

      {/* Main panel */}
      <div className="flex-1 flex flex-col bg-zinc-950/80">
        {/* Header */}
        <div className="h-12 border-b border-zinc-800/50 flex items-center px-5 justify-between bg-zinc-900/20">
          <div className="flex items-center gap-2.5">
            <span className="text-sm font-semibold text-zinc-200">Sr. Engineer — SF</span>
            <span className="px-1.5 py-0.5 rounded bg-emerald-500/15 text-[9px] text-emerald-400 border border-emerald-500/25 font-medium">Recruiting</span>
          </div>
          <div className="flex items-center gap-1.5">
            {['Posting', 'Candidates', 'Interviews', 'Shortlist'].map((t, i) => (
              <span key={t} className={`px-2 py-0.5 rounded text-[9px] font-medium transition-colors ${
                (step <= 1 && i === 0) || (step === 2 && i === 1) || (step === 3 && i === 2) || (step >= 4 && i === 3)
                  ? 'bg-zinc-800 text-zinc-200 border border-zinc-600'
                  : 'text-zinc-600'
              }`}>{t}</span>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 p-5 overflow-hidden">
          <AnimatePresence mode="wait">

            {/* Step 1: Job Posting */}
            {step >= 1 && step < 2 && (
              <motion.div key="posting" {...fade} className="space-y-3">
                <div className="p-4 rounded-lg border border-zinc-700/50 bg-zinc-900/50">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-bold text-zinc-100">Senior Software Engineer</h3>
                    <span className="px-2 py-0.5 rounded bg-emerald-500/15 text-[9px] text-emerald-400 border border-emerald-500/25">Finalized</span>
                  </div>
                  <div className="grid grid-cols-3 gap-3 text-[11px]">
                    <div><span className="text-zinc-500">Location</span><div className="text-zinc-300 mt-0.5">San Francisco, CA</div></div>
                    <div><span className="text-zinc-500">Salary</span><div className="text-zinc-300 mt-0.5">$185k — $220k</div></div>
                    <div><span className="text-zinc-500">Equity</span><div className="text-zinc-300 mt-0.5">0.05% — 0.12%</div></div>
                  </div>
                  <div className="flex gap-1.5 mt-3">
                    {['React', 'Go', 'Kubernetes', 'PostgreSQL'].map(s => (
                      <span key={s} className="px-2 py-0.5 rounded bg-zinc-800 text-[9px] text-zinc-400 border border-zinc-700/50">{s}</span>
                    ))}
                  </div>
                </div>
                <div className="text-[10px] text-zinc-600 flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />
                  AI analyzed role requirements — ready for candidates
                </div>
              </motion.div>
            )}

            {/* Step 2: Candidates */}
            {step >= 2 && step < 3 && (
              <motion.div key="candidates" {...fade} className="space-y-2">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] text-zinc-500 font-medium uppercase tracking-wider">4 candidates ranked by AI match</span>
                  <span className="text-[9px] text-emerald-500">Drop resumes to add more</span>
                </div>
                {CANDIDATES.map((c, i) => (
                  <motion.div
                    key={c.name}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.15 }}
                    className="flex items-center gap-3 p-2.5 rounded-lg border border-zinc-800/60 bg-zinc-900/30 hover:border-zinc-700 transition-colors"
                  >
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0 ${
                      c.score >= 90 ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30' : 'bg-zinc-800 text-zinc-400 border border-zinc-700'
                    }`}>{c.score}</div>
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium text-zinc-200 truncate">{c.name}</div>
                      <div className="text-[10px] text-zinc-500 truncate">{c.role}</div>
                    </div>
                    <div className="hidden sm:flex gap-1">
                      {c.skills.slice(0, 2).map(s => (
                        <span key={s} className="px-1.5 py-0.5 rounded bg-zinc-800/80 text-[8px] text-zinc-500">{s}</span>
                      ))}
                    </div>
                    <span className="text-[9px] text-zinc-600 shrink-0">{c.loc}</span>
                  </motion.div>
                ))}
              </motion.div>
            )}

            {/* Step 3: Interviews */}
            {step >= 3 && step < 4 && (
              <motion.div key="interviews" {...fade} className="space-y-2">
                <span className="text-[10px] text-zinc-500 font-medium uppercase tracking-wider">Voice interviews via Gemini</span>
                {CANDIDATES.map((c, i) => (
                  <motion.div
                    key={c.name}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: i * 0.1 }}
                    className="flex items-center justify-between p-2.5 rounded-lg border border-zinc-800/60 bg-zinc-900/30"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-7 h-7 rounded-full bg-zinc-800 flex items-center justify-center text-[10px] font-bold text-zinc-400">{c.name.split(' ').map(n => n[0]).join('')}</div>
                      <div>
                        <div className="text-xs text-zinc-200">{c.name}</div>
                        <div className="text-[10px] text-zinc-500">{c.role}</div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {c.interviewScore && (
                        <span className="text-[10px] font-mono text-emerald-400">{c.interviewScore}/100</span>
                      )}
                      <span className={`px-2 py-0.5 rounded text-[9px] font-medium ${
                        c.status === 'completed' ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/25'
                        : c.status === 'sent' ? 'bg-amber-500/15 text-amber-400 border border-amber-500/25'
                        : 'bg-zinc-800 text-zinc-500 border border-zinc-700'
                      }`}>{c.status === 'completed' ? 'Scored' : c.status === 'sent' ? 'In Progress' : 'Pending'}</span>
                    </div>
                  </motion.div>
                ))}
              </motion.div>
            )}

            {/* Step 4: Shortlist */}
            {step >= 4 && (
              <motion.div key="shortlist" {...fade} className="space-y-3">
                <span className="text-[10px] text-zinc-500 font-medium uppercase tracking-wider">AI shortlist recommendation</span>
                <div className="p-4 rounded-lg border border-emerald-500/30 bg-emerald-500/5">
                  <div className="flex items-center gap-3 mb-3">
                    <div className="w-10 h-10 rounded-full bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-sm font-bold text-emerald-400">94</div>
                    <div>
                      <div className="text-sm font-semibold text-zinc-100">Maya Chen</div>
                      <div className="text-[11px] text-zinc-400">Sr. Engineer @ Stripe</div>
                    </div>
                    <span className="ml-auto px-2.5 py-1 rounded bg-emerald-500/20 text-[10px] text-emerald-300 border border-emerald-500/30 font-medium">Top Pick</span>
                  </div>
                  <div className="text-[11px] text-zinc-400 leading-relaxed">
                    Interview score 92/100 — strong systems design, React expertise matches stack. 6 years experience with distributed systems at scale.
                  </div>
                  <div className="flex gap-2 mt-3">
                    <button className="text-[10px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 px-3 py-1.5 rounded font-bold uppercase tracking-wider">
                      Generate Offer
                    </button>
                    <button className="text-[10px] bg-zinc-800 text-zinc-300 border border-zinc-700 px-3 py-1.5 rounded font-bold uppercase tracking-wider">
                      View Full Profile
                    </button>
                  </div>
                </div>
                <div className="flex items-center gap-3 p-3 rounded-lg border border-zinc-800/60 bg-zinc-900/30">
                  <div className="w-8 h-8 rounded-full bg-zinc-800 flex items-center justify-center text-[10px] font-bold text-zinc-400">91</div>
                  <div>
                    <div className="text-xs text-zinc-300">James Park</div>
                    <div className="text-[10px] text-zinc-500">Staff Eng @ Airbnb — Interview: 87/100</div>
                  </div>
                </div>
              </motion.div>
            )}

          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}
