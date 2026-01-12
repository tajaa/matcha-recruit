import { useState, useEffect, lazy, Suspense } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, CheckCircle2, Zap, Radio } from 'lucide-react';

// Lazy load Three.js-heavy component
const ParticleSphere = lazy(() => import('../components/ParticleSphere'));

export function Landing() {
  const [currentTime, setCurrentTime] = useState(new Date());
  const [stats] = useState({
    interviews: 1247,
    responseTime: '< 1s',
    matchRate: 94.7,
  });

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const formatTime = (date: Date) => {
    return date.toISOString().slice(11, 19);
  };

  const formatDate = (date: Date) => {
    return date.toISOString().slice(0, 10);
  };

  return (
    <div className="bg-[#fbfbfb] text-zinc-900 font-mono selection:bg-zinc-200 selection:text-zinc-900 overflow-hidden">
      {/* Fixed Background Elements */}
      <div className="fixed inset-0 z-0 pointer-events-none">
        <div
          className="absolute inset-[-100%] opacity-[0.03] animate-drift"
          style={{
            backgroundImage: `
              linear-gradient(to right, #000 1px, transparent 1px),
              linear-gradient(to bottom, #000 1px, transparent 1px)
            `,
            backgroundSize: '80px 80px',
          }}
        />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,transparent_0%,#fbfbfb_85%)]" />
      </div>

      {/* Navigation */}
      <header className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 py-6 bg-white/70 backdrop-blur-md border-b border-zinc-200/50">
        <div className="flex items-center gap-3">
          <div className="w-2.5 h-2.5 rounded-full bg-zinc-900 animate-pulse shadow-[0_0_15px_rgba(24,24,27,0.5)]" />
          <span className="text-xs tracking-[0.3em] uppercase text-zinc-900 font-bold">
            Matcha
          </span>
        </div>

        <nav className="flex items-center gap-6">
          <Link
            to="/login"
            className="text-[10px] tracking-[0.2em] uppercase text-zinc-500 hover:text-zinc-900 transition-colors font-medium"
          >
            Login
          </Link>
          <Link
            to="/register"
            className="text-[10px] tracking-[0.2em] uppercase text-zinc-600 border border-zinc-200 px-6 py-2.5 hover:border-zinc-900 hover:text-zinc-900 transition-all bg-white hover:shadow-sm rounded-sm"
          >
            Initialize
          </Link>
        </nav>
      </header>

      {/* HERO SECTION */}
      <section className="relative z-10 min-h-screen flex items-center justify-center pt-20 px-4 sm:px-8">
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_minmax(400px,600px)_1fr] gap-12 items-center w-full max-w-7xl">
          {/* Left - Title */}
          <div className="flex flex-col justify-center lg:text-left text-center">

            <div className="inline-flex items-center gap-2 mb-8 mx-auto lg:mx-0 px-3 py-1 rounded-full bg-zinc-100 border border-zinc-200 w-fit">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-zinc-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-zinc-500"></span>
              </span>
              <span className="text-[9px] tracking-[0.2em] uppercase text-zinc-600 font-semibold">System V2.0 Live</span>
            </div>

            <div className="space-y-6">
              <h1 className="text-5xl sm:text-7xl lg:text-8xl font-bold tracking-[-0.03em] text-zinc-900 leading-[0.9]">
                MATCHA
              </h1>
              <p className="text-xs tracking-[0.3em] uppercase text-zinc-500 font-medium">
                Autonomous Recruiting Engine
              </p>
            </div>

            <div className="mt-16 space-y-4 hidden lg:block">
              {['THOUGHTFUL CANDIDATE SCREENING', 'COMMUNICATION & FIT SIGNALS', 'CURATED SHORTLISTS, NOT RESUME PILES'].map((item, i) => (
                <div key={i} className="flex items-center gap-4 text-[10px] tracking-widest text-zinc-500 font-medium group">
                  <span className="w-6 h-px bg-zinc-300 group-hover:w-10 group-hover:bg-zinc-600 transition-all duration-500" />
                  <span className="group-hover:text-zinc-800 transition-colors">{item}</span>
                </div>
              ))}

              <div className="pt-10 space-y-8">
                <p className="text-zinc-500 text-sm leading-relaxed max-w-sm font-sans">
                  We've automated the first 3 rounds of interviewing. 15 years in hiring condensed into one powerful AI agent.
                </p>
              </div>
            </div>
          </div>

          {/* Center - Sphere */}
          <div className="relative flex items-center justify-center py-12 lg:py-0 group">
            <div className="absolute inset-0 bg-gradient-to-b from-zinc-200/20 to-transparent rounded-full blur-3xl opacity-0 group-hover:opacity-100 transition-opacity duration-1000" />

            <Suspense fallback={<div className="w-full h-[300px] sm:h-[400px] lg:h-[500px] bg-zinc-100 rounded-full animate-pulse" />}>
              <div className="transition-all duration-700 hover:scale-105">
                <ParticleSphere className="w-full h-[300px] sm:h-[400px] lg:h-[500px]" />
              </div>
            </Suspense>

            {/* Coordinates overlay with glass effect */}
            <div className="absolute bottom-8 left-1/2 -translate-x-1/2 lg:translate-x-0 lg:left-8 px-4 py-2 bg-white/80 backdrop-blur-sm border border-zinc-200/50 rounded text-[9px] tracking-widest text-zinc-500 shadow-sm flex gap-4">
              <div>LAT: 37.7749</div>
              <div className="w-px h-3 bg-zinc-300"></div>
              <div>LNG: -122.4194</div>
            </div>
          </div>

          {/* Right - Timestamp */}
          <div className="flex flex-col items-end justify-center hidden lg:flex">
            <div className="text-right space-y-8">
              <div className="group">
                <div className="text-[9px] tracking-[0.2em] text-zinc-400 mb-2 group-hover:text-zinc-600 transition-colors">
                  UTC TIME
                </div>
                <div className="text-3xl tracking-widest text-zinc-900 tabular-nums font-light">
                  {formatTime(currentTime)}
                </div>
              </div>

              <div className="group">
                <div className="text-[9px] tracking-[0.2em] text-zinc-400 mb-2 group-hover:text-zinc-600 transition-colors">
                  DATE
                </div>
                <div className="text-sm tracking-widest text-zinc-500 tabular-nums">
                  {formatDate(currentTime)}
                </div>
              </div>

              <div className="pt-8 border-t border-zinc-200 w-full flex justify-end">
                <div>
                  <div className="text-[9px] tracking-[0.2em] text-zinc-400 mb-2 text-right">
                    SYSTEM STATUS
                  </div>
                  <div className="flex items-center justify-end gap-2 px-3 py-1.5 bg-zinc-50 border border-zinc-200 rounded-full">
                    <span className="w-1.5 h-1.5 rounded-full bg-zinc-500 animate-pulse" />
                    <span className="text-[10px] tracking-widest text-zinc-700 font-semibold">
                      OPERATIONAL
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Mobile CTA */}
        <div className="absolute bottom-12 left-0 right-0 flex justify-center lg:hidden z-20">
          <Link
            to="/register"
            className="text-xs tracking-[0.2em] uppercase bg-zinc-900 text-white px-8 py-4 hover:bg-zinc-800 transition-colors font-medium shadow-lg hover:shadow-xl hover:-translate-y-1 transform duration-300"
          >
            Initialize System
          </Link>
        </div>
      </section>

      {/* PROBLEM SECTION */}
      <section className="relative z-10 py-32 px-4 sm:px-8 border-y border-zinc-200 bg-white">
        <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-24 items-start">
          <div className="space-y-8 sticky top-32">
            <div className="inline-block">
              <h2 className="text-xs tracking-[0.3em] uppercase text-zinc-400 mb-2">Diagnosis</h2>
              <div className="h-px w-full bg-zinc-300"></div>
            </div>
            <h3 className="text-4xl sm:text-5xl font-bold tracking-tight text-zinc-900 leading-tight">
              Recruiting is overwhelmed by <span className="text-zinc-500 decoration-4 underline-offset-4 line-through decoration-zinc-200">noise</span>.
            </h3>
            <p className="text-zinc-500 leading-relaxed text-lg max-w-md font-sans border-l-2 border-zinc-200 pl-6">
              Great candidates get lost in keyword filters. Hiring managers drown in resume piles. The human element is ignored until it's too late.
            </p>
          </div>

          <div className="grid gap-6">
            {[
              { id: '01', title: 'Resume Fatigue', desc: 'Hundreds of applications. Hours of reviewing. Most aren\'t even close to what you need.' },
              { id: '02', title: 'Ghosting & Delays', desc: 'Slow manual screening leads to top talent accepting other offers before you even speak.' },
              { id: '03', title: 'Poor Signal', desc: 'Resumes don\'t show soft skills, cultural fit, or problem-solving ability.' }
            ].map((item) => (
              <div key={item.id} className="group p-10 border border-zinc-100 bg-zinc-50/50 hover:bg-white hover:border-zinc-300 hover:shadow-[0_20px_40px_-15px_rgba(0,0,0,0.05)] transition-all duration-500 rounded-sm relative overflow-hidden">
                <div className="absolute top-0 right-0 p-6 opacity-10 group-hover:opacity-20 transition-opacity">
                  <span className="text-6xl font-black text-zinc-300">{item.id}</span>
                </div>
                <div className="w-10 h-10 rounded-full bg-white border border-zinc-200 shadow-sm flex items-center justify-center mb-6 group-hover:border-zinc-800 group-hover:text-zinc-900 transition-colors text-zinc-400">
                  <Radio className="w-4 h-4" />
                </div>
                <h4 className="text-xl font-bold text-zinc-900 mb-3 group-hover:text-zinc-700 transition-colors">{item.title}</h4>
                <p className="text-zinc-500 text-sm leading-relaxed font-sans">
                  {item.desc}
                </p>
                <div className="absolute bottom-0 left-0 w-full h-1 bg-zinc-900 transform scale-x-0 group-hover:scale-x-100 transition-transform duration-500 origin-left"></div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* SOLUTION SECTION */}
      <section className="relative z-10 py-32 px-4 sm:px-8 bg-[#f8fafc]">
        {/* Grid overlay for this section */}
        <div className="absolute inset-0 opacity-[0.02]"
          style={{
            backgroundImage: `radial-gradient(#000 1px, transparent 1px)`,
            backgroundSize: '24px 24px'
          }}
        />

        <div className="max-w-7xl mx-auto relative z-10">
          <div className="mb-20 text-center md:text-left">
            <h2 className="text-xs tracking-[0.3em] uppercase text-zinc-500 font-bold mb-6">The Solution</h2>
            <h3 className="text-4xl sm:text-5xl font-bold tracking-tight text-zinc-900 max-w-3xl leading-tight">
              Signal over noise. <br />
              <span className="text-zinc-400 font-light">Autonomous, meaningful screening.</span>
            </h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="bg-white p-10 border border-zinc-200 shadow-sm hover:shadow-xl hover:-translate-y-2 transition-all duration-300 rounded-xl group">
              <div className="w-14 h-14 bg-zinc-50 rounded-2xl flex items-center justify-center text-zinc-600 mb-8 group-hover:scale-110 transition-transform duration-300">
                <Zap className="w-6 h-6" />
              </div>
              <h4 className="text-xl font-bold text-zinc-900 mb-4">Conversational AI</h4>
              <p className="text-zinc-500 text-sm leading-relaxed font-sans">
                Matcha engages candidates in real-time interviews, adapting to their responses to dig deeper into their experience.
              </p>
            </div>

            <div className="bg-white p-10 border border-zinc-200 shadow-sm hover:shadow-xl hover:-translate-y-2 transition-all duration-300 rounded-xl group">
              <div className="w-14 h-14 bg-zinc-50 rounded-2xl flex items-center justify-center text-zinc-600 mb-8 group-hover:scale-110 transition-transform duration-300">
                <CheckCircle2 className="w-6 h-6" />
              </div>
              <h4 className="text-xl font-bold text-zinc-900 mb-4">Multi-Dimensional Analysis</h4>
              <p className="text-zinc-500 text-sm leading-relaxed font-sans">
                We evaluate technical skills, communication clarity, and cultural add simultaneously.
              </p>
            </div>

            <div className="bg-white p-10 border border-zinc-200 shadow-sm hover:shadow-xl hover:-translate-y-2 transition-all duration-300 rounded-xl group">
              <div className="w-14 h-14 bg-zinc-50 rounded-2xl flex items-center justify-center text-zinc-600 mb-8 group-hover:scale-110 transition-transform duration-300">
                <ArrowRight className="w-6 h-6" />
              </div>
              <h4 className="text-xl font-bold text-zinc-900 mb-4">Curated Shortlists</h4>
              <p className="text-zinc-500 text-sm leading-relaxed font-sans">
                You receive a ranked list of candidates who are actually a fit, with detailed notes on why.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* FOOTER STATS */}
      <section className="relative z-10 py-16 px-4 sm:px-8 border-t border-zinc-200 bg-white">
        <div className="flex flex-wrap items-center justify-between max-w-7xl mx-auto gap-12">
          <div className="flex flex-col gap-2 group cursor-default">
            <span className="text-[10px] tracking-[0.2em] text-zinc-400 uppercase group-hover:text-zinc-600 transition-colors">
              Total Interviews Processed
            </span>
            <span className="text-4xl tracking-tight text-zinc-900 tabular-nums font-bold">
              {stats.interviews.toLocaleString()}
            </span>
          </div>

          <div className="flex flex-col gap-2 group cursor-default">
            <span className="text-[10px] tracking-[0.2em] text-zinc-400 uppercase group-hover:text-zinc-600 transition-colors">
              Avg. Response Time
            </span>
            <span className="text-4xl tracking-tight text-zinc-900 font-bold">
              {stats.responseTime}
            </span>
          </div>

          <div className="flex flex-col gap-2 group cursor-default">
            <span className="text-[10px] tracking-[0.2em] text-zinc-400 uppercase group-hover:text-zinc-600 transition-colors">
              Placement Match Rate
            </span>
            <span className="text-4xl tracking-tight text-zinc-900 tabular-nums font-bold">
              {stats.matchRate}%
            </span>
          </div>

          <div className="flex flex-col gap-3">
            <span className="text-[10px] tracking-[0.2em] text-zinc-400 uppercase">
              System Status
            </span>
            <div className="flex items-center gap-2">
              <div className="relative">
                <div className="w-2 h-2 rounded-full bg-zinc-500 z-10 relative"></div>
                <div className="absolute inset-0 bg-zinc-500 rounded-full animate-ping opacity-75"></div>
              </div>
              <span className="text-xs tracking-[0.15em] text-zinc-600 uppercase font-bold">
                Online
              </span>
            </div>
          </div>
        </div>
      </section>

      <footer className="relative z-10 py-12 text-center border-t border-zinc-100 bg-zinc-50">
        <div className="flex items-center justify-center gap-8 mb-8">
          <Link to="#" className="text-[10px] tracking-[0.2em] uppercase text-zinc-400 hover:text-zinc-900 transition-colors">Privacy</Link>
          <Link to="#" className="text-[10px] tracking-[0.2em] uppercase text-zinc-400 hover:text-zinc-900 transition-colors">Terms</Link>
          <Link to="#" className="text-[10px] tracking-[0.2em] uppercase text-zinc-400 hover:text-zinc-900 transition-colors">Contact</Link>
        </div>
        <p className="text-[10px] tracking-widest text-zinc-400">
          © 2024 MATCHA RECRUITING. SYSTEM V2.0.
        </p>
      </footer>
    </div>
  );
}

export default Landing;
