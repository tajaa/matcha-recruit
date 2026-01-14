import { useState, useEffect, lazy, Suspense } from "react";
import { Link } from "react-router-dom";

// Lazy load Three.js-heavy component
const ParticleSphere = lazy(() => import("../components/ParticleSphere"));

export function Landing() {
  const [currentTime, setCurrentTime] = useState(new Date());
  const [stats] = useState({
    interviews: 1247,
    responseTime: "< 1s",
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
    <div className="bg-zinc-50 text-zinc-900 font-mono selection:bg-zinc-200 selection:text-zinc-900">
      {/* Fixed Background Elements */}
      <div className="fixed inset-0 z-0 pointer-events-none">
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage: `
              linear-gradient(to right, #000 1px, transparent 1px),
              linear-gradient(to bottom, #000 1px, transparent 1px)
            `,
            backgroundSize: "60px 60px",
          }}
        />
      </div>

      {/* Navigation */}
      <header className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-4 sm:px-8 py-6 bg-white/80 backdrop-blur-md border-b border-zinc-200">
        <Link to="/" className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-matcha-500 animate-pulse shadow-[0_0_10px_rgba(34,197,94,0.4)]" />
          <span className="text-xs tracking-[0.3em] uppercase text-zinc-900 font-medium">
            Matcha
          </span>
        </Link>

        <nav className="flex items-center gap-6">
          <Link
            to="/blog"
            className="text-[10px] tracking-[0.2em] uppercase text-zinc-500 hover:text-matcha-600 transition-colors"
          >
            Blog
          </Link>
          <Link
            to="/login"
            className="text-[10px] tracking-[0.2em] uppercase text-zinc-500 hover:text-matcha-600 transition-colors"
          >
            Login
          </Link>
          <Link
            to="/register"
            className="text-[10px] tracking-[0.2em] uppercase text-zinc-600 border border-zinc-300 px-5 py-2 hover:border-matcha-500 hover:text-matcha-600 transition-all bg-white"
          >
            Initialize
          </Link>
        </nav>
      </header>

      {/* HERO SECTION */}
      <section className="relative z-10 min-h-screen flex items-center justify-center pt-20 px-4 sm:px-8 border-b border-zinc-800/50">
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_minmax(400px,500px)_1fr] gap-8 items-center w-full max-w-7xl">
          {/* Left - Title */}
          <div className="flex flex-col justify-center lg:text-left text-center">
            <div className="space-y-4">
              <h1 className="text-4xl sm:text-6xl lg:text-7xl font-bold tracking-[-0.02em] text-gray-600">
                MATCHA
              </h1>
              <p className="text-xs tracking-[0.3em] uppercase text-zinc-500">
                AI-Powered Recruiting
              </p>
            </div>

            <div className="mt-12 space-y-3 hidden lg:block">
              <div className="flex items-center gap-3 text-[10px] tracking-widest text-zinc-600">
                <span className="w-2 h-px bg-zinc-700" />
                <span>THOUGHTFUL CANDIDATE SCREENING</span>
              </div>
              <div className="flex items-center gap-3 text-[10px] tracking-widest text-zinc-600">
                <span className="w-2 h-px bg-zinc-700" />
                <span>COMMUNICATION & FIT SIGNALS</span>
              </div>
              <div className="flex items-center gap-3 text-[10px] tracking-widest text-zinc-600">
                <span className="w-2 h-px bg-zinc-700" />
                <span>CURATED SHORTLISTS, NOT RESUME PILES</span>
              </div>

              <div className="pt-8 space-y-6">
                <p className="text-zinc-500 text-sm leading-relaxed max-w-md">
                  15 years in hiring. More than 5,000 people placed. We've built
                  the tool we always wanted.
                </p>

                <div className="flex flex-col sm:flex-row gap-4">
                  <Link
                    to="/for-candidates"
                    className="inline-flex items-center justify-center px-6 py-2.5 text-xs font-medium tracking-widest uppercase text-matcha-500 border border-matcha-500/50 hover:bg-matcha-500/10 transition-colors"
                  >
                    For Candidates
                  </Link>
                  <Link
                    to="/work-with-us"
                    className="inline-flex items-center justify-center px-6 py-2.5 text-xs font-medium tracking-widest uppercase text-zinc-400 border border-zinc-700 hover:text-white hover:border-zinc-500 transition-colors"
                  >
                    Work with us
                  </Link>
                </div>
              </div>
            </div>
          </div>

          {/* Center - Sphere */}
          <div className="relative flex items-center justify-center py-12 lg:py-0">
            <Suspense
              fallback={
                <div className="w-full h-[300px] sm:h-[400px] lg:h-[500px] bg-zinc-950" />
              }
            >
              <ParticleSphere className="w-full h-[300px] sm:h-[400px] lg:h-[500px]" />
            </Suspense>

            {/* Coordinates overlay */}
            <div className="absolute bottom-4 left-4 text-[9px] tracking-widest text-zinc-600">
              <div>LAT: 37.7749</div>
              <div>LNG: -122.4194</div>
            </div>
          </div>

          {/* Right - Timestamp */}
          <div className="flex flex-col items-end justify-center hidden lg:flex">
            <div className="text-right space-y-6">
              <div>
                <div className="text-[9px] tracking-[0.2em] text-zinc-600 mb-1">
                  UTC TIME
                </div>
                <div className="text-2xl tracking-wider text-zinc-300 tabular-nums">
                  {formatTime(currentTime)}
                </div>
              </div>

              <div>
                <div className="text-[9px] tracking-[0.2em] text-zinc-600 mb-1">
                  DATE
                </div>
                <div className="text-sm tracking-wider text-zinc-400 tabular-nums">
                  {formatDate(currentTime)}
                </div>
              </div>

              <div className="pt-4 border-t border-zinc-800">
                <div className="text-[9px] tracking-[0.2em] text-zinc-600 mb-1">
                  SYSTEM STATUS
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-1.5 h-1.5 rounded-full bg-matcha-500 animate-pulse" />
                  <span className="text-xs tracking-widest text-matcha-500">
                    OPERATIONAL
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Mobile CTA */}
        <div className="absolute bottom-8 left-0 right-0 flex justify-center lg:hidden">
          <Link
            to="/register"
            className="text-xs tracking-[0.2em] uppercase bg-matcha-500 text-black px-8 py-3 hover:bg-matcha-400 transition-colors font-medium"
          >
            Start Interview
          </Link>
        </div>
      </section>

      {/* PROBLEM SECTION */}
      <section className="relative z-10 py-24 px-4 sm:px-8 border-b border-zinc-200 bg-white/50">
        <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-16 items-start">
          <div className="space-y-6 sticky top-24">
            <h2 className="text-sm tracking-[0.2em] uppercase text-matcha-500">
              The Problem
            </h2>
            <h3 className="text-3xl sm:text-4xl font-bold tracking-tight text-zinc-900 leading-tight">
              Recruiting is overwhelmed by noise.
            </h3>
            <p className="text-zinc-500 leading-relaxed max-w-md">
              Great candidates get lost in keyword filters. Hiring managers
              drown in resume piles. The human element—fit, communication,
              potential—is ignored until it's too late.
            </p>
          </div>
          <div className="grid gap-6">
            <div className="p-8 border border-zinc-200 bg-white hover:border-matcha-500/50 hover:shadow-sm transition-all group">
              <div className="flex items-start gap-6">
                <div className="w-10 h-10 border border-zinc-200 flex items-center justify-center group-hover:border-matcha-500 group-hover:bg-matcha-50 transition-colors shrink-0">
                  <span className="text-[10px] tracking-wider text-zinc-400 group-hover:text-matcha-600 transition-colors">
                    01
                  </span>
                </div>
                <div>
                  <h4 className="text-base font-semibold text-zinc-900 mb-2">
                    Resume Fatigue
                  </h4>
                  <p className="text-zinc-500 text-sm leading-relaxed">
                    Hundreds of applications. Hours of reviewing. Most aren't even
                    close to what you need.
                  </p>
                </div>
              </div>
            </div>
            <div className="p-8 border border-zinc-200 bg-white hover:border-matcha-500/50 hover:shadow-sm transition-all group">
              <div className="flex items-start gap-6">
                <div className="w-10 h-10 border border-zinc-200 flex items-center justify-center group-hover:border-matcha-500 group-hover:bg-matcha-50 transition-colors shrink-0">
                  <span className="text-[10px] tracking-wider text-zinc-400 group-hover:text-matcha-600 transition-colors">
                    02
                  </span>
                </div>
                <div>
                  <h4 className="text-base font-semibold text-zinc-900 mb-2">
                    Ghosting & Delays
                  </h4>
                  <p className="text-zinc-500 text-sm leading-relaxed">
                    Slow manual screening leads to top talent accepting other offers
                    before you even speak.
                  </p>
                </div>
              </div>
            </div>
            <div className="p-8 border border-zinc-200 bg-white hover:border-matcha-500/50 hover:shadow-sm transition-all group">
              <div className="flex items-start gap-6">
                <div className="w-10 h-10 border border-zinc-200 flex items-center justify-center group-hover:border-matcha-500 group-hover:bg-matcha-50 transition-colors shrink-0">
                  <span className="text-[10px] tracking-wider text-zinc-400 group-hover:text-matcha-600 transition-colors">
                    03
                  </span>
                </div>
                <div>
                  <h4 className="text-base font-semibold text-zinc-900 mb-2">
                    Poor Signal
                  </h4>
                  <p className="text-zinc-500 text-sm leading-relaxed">
                    Resumes don't show soft skills, cultural fit, or problem-solving
                    ability.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* SOLUTION SECTION */}
      <section className="relative z-10 py-24 px-4 sm:px-8 border-b border-zinc-200">
        <div className="max-w-7xl mx-auto">
          <div className="mb-16">
            <h2 className="text-sm tracking-[0.2em] uppercase text-matcha-500 mb-6">
              The Solution
            </h2>
            <h3 className="text-3xl sm:text-4xl font-bold tracking-tight text-zinc-900 max-w-2xl leading-tight">
              Signal over noise. <br />
              <span className="text-zinc-400">
                Autonomous, meaningful screening.
              </span>
            </h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-px bg-zinc-200 border border-zinc-200">
            <div className="bg-white p-8 sm:p-12 hover:bg-zinc-50 transition-colors group">
              <div className="w-10 h-10 border border-zinc-200 flex items-center justify-center mb-6 group-hover:border-matcha-500 group-hover:bg-matcha-50 transition-colors">
                <svg
                  className="w-5 h-5 text-zinc-400 group-hover:text-matcha-600 transition-colors"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"
                  />
                </svg>
              </div>
              <h4 className="text-base font-semibold text-zinc-900 mb-3">
                Conversational AI
              </h4>
              <p className="text-zinc-500 text-sm leading-relaxed">
                Matcha engages candidates in real-time interviews, adapting to
                their responses to dig deeper into their experience.
              </p>
            </div>

            <div className="bg-white p-8 sm:p-12 hover:bg-zinc-50 transition-colors group">
              <div className="w-10 h-10 border border-zinc-200 flex items-center justify-center mb-6 group-hover:border-matcha-500 group-hover:bg-matcha-50 transition-colors">
                <svg
                  className="w-5 h-5 text-zinc-400 group-hover:text-matcha-600 transition-colors"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
                  />
                </svg>
              </div>
              <h4 className="text-base font-semibold text-zinc-900 mb-3">
                Multi-Dimensional Analysis
              </h4>
              <p className="text-zinc-500 text-sm leading-relaxed">
                We evaluate technical skills, communication clarity, and
                cultural add simultaneously.
              </p>
            </div>

            <div className="bg-white p-8 sm:p-12 hover:bg-zinc-50 transition-colors group">
              <div className="w-10 h-10 border border-zinc-200 flex items-center justify-center mb-6 group-hover:border-matcha-500 group-hover:bg-matcha-50 transition-colors">
                <svg
                  className="w-5 h-5 text-zinc-400 group-hover:text-matcha-600 transition-colors"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
              </div>
              <h4 className="text-base font-semibold text-zinc-900 mb-3">
                Curated Shortlists
              </h4>
              <p className="text-zinc-500 text-sm leading-relaxed">
                You receive a ranked list of candidates who are actually a fit,
                with detailed notes on why.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* FOOTER STATS */}
      <section className="relative z-10 border-t border-zinc-200 bg-zinc-100/50">
        <div className="max-w-7xl mx-auto">
          <div className="grid grid-cols-2 md:grid-cols-4 divide-x divide-zinc-200">
            <div className="p-6 sm:p-8">
              <span className="text-[9px] tracking-[0.2em] text-zinc-400 uppercase block mb-2">
                Interviews
              </span>
              <span className="text-2xl sm:text-3xl font-light text-zinc-900 tabular-nums">
                {stats.interviews.toLocaleString()}
              </span>
            </div>

            <div className="p-6 sm:p-8">
              <span className="text-[9px] tracking-[0.2em] text-zinc-400 uppercase block mb-2">
                Response Time
              </span>
              <span className="text-2xl sm:text-3xl font-light text-zinc-900">
                {stats.responseTime}
              </span>
            </div>

            <div className="p-6 sm:p-8">
              <span className="text-[9px] tracking-[0.2em] text-zinc-400 uppercase block mb-2">
                Match Rate
              </span>
              <span className="text-2xl sm:text-3xl font-light text-zinc-900 tabular-nums">
                {stats.matchRate}%
              </span>
            </div>

            <div className="p-6 sm:p-8">
              <span className="text-[9px] tracking-[0.2em] text-zinc-400 uppercase block mb-2">
                Status
              </span>
              <div className="flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-matcha-500 animate-pulse" />
                <span className="text-sm sm:text-base font-light text-matcha-600 uppercase tracking-wider">
                  Live
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <footer className="relative z-10 py-6 border-t border-zinc-200 bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-8 flex flex-col sm:flex-row items-center justify-between gap-4">
          <span className="text-[9px] tracking-[0.3em] text-zinc-400 uppercase">
            © {new Date().getFullYear()} Matcha Recruit
          </span>
          <div className="flex items-center gap-6">
            <Link
              to="/blog"
              className="text-[9px] tracking-[0.2em] text-zinc-400 hover:text-matcha-600 uppercase transition-colors"
            >
              Blog
            </Link>
            <Link
              to="/careers"
              className="text-[9px] tracking-[0.2em] text-zinc-400 hover:text-matcha-600 uppercase transition-colors"
            >
              Careers
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
export default Landing;
