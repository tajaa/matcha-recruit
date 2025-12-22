import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ParticleSphere } from '../components';

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
    <div className="min-h-screen bg-zinc-950 text-white overflow-hidden relative font-mono selection:bg-matcha-500 selection:text-black">
      {/* Subtle grid background */}
      <div className="absolute inset-0 z-0 pointer-events-none">
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage: `
              linear-gradient(to right, #22c55e 1px, transparent 1px),
              linear-gradient(to bottom, #22c55e 1px, transparent 1px)
            `,
            backgroundSize: '60px 60px',
          }}
        />
        {/* Radial vignette */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_0%,#09090b_70%)]" />
      </div>

      {/* Header */}
      <header className="relative z-10 flex items-center justify-between px-4 sm:px-8 py-6">
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-matcha-500 animate-pulse shadow-[0_0_10px_rgba(34,197,94,0.8)]" />
          <span className="text-xs tracking-[0.3em] uppercase text-matcha-500 font-medium">
            Matcha
          </span>
        </div>

        <nav className="flex items-center gap-6">
          <Link
            to="/login"
            className="text-[10px] tracking-[0.2em] uppercase text-zinc-500 hover:text-matcha-400 transition-colors"
          >
            Login
          </Link>
          <Link
            to="/register"
            className="text-[10px] tracking-[0.2em] uppercase text-zinc-400 border border-zinc-700 px-5 py-2 hover:border-matcha-500 hover:text-matcha-400 transition-all"
          >
            Initialize
          </Link>
        </nav>
      </header>

      {/* Main Content */}
      <main className="relative z-10 flex items-center justify-center min-h-[calc(100vh-180px)] px-4 sm:px-8">
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_minmax(400px,500px)_1fr] gap-8 items-center w-full max-w-7xl">
          {/* Left - Title */}
          <div className="flex flex-col justify-center lg:text-left text-center">
            <div className="space-y-4">
              <h1 className="text-4xl sm:text-6xl lg:text-7xl font-bold tracking-[-0.02em] text-white">
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
                  Currently in private beta. We are working closely with a small number of candidates and teams.
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
          <div className="relative flex items-center justify-center">
            <ParticleSphere className="w-full h-[400px] lg:h-[500px]" />

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
      </main>

      {/* CTA Section - Mobile only */}
      <div className="lg:hidden relative z-10 flex justify-center pb-8">
        <Link
          to="/register"
          className="text-xs tracking-[0.2em] uppercase bg-matcha-500 text-black px-8 py-3 hover:bg-matcha-400 transition-colors font-medium"
        >
          Start Interview
        </Link>
      </div>

      {/* Bottom Stats Bar */}
      <footer className="absolute bottom-0 left-0 right-0 z-10 border-t border-zinc-800/50 bg-zinc-950/80 backdrop-blur-sm">
        <div className="flex items-center justify-between px-4 sm:px-8 py-4 max-w-7xl mx-auto">
          <div className="flex items-center gap-4 sm:gap-8 lg:gap-16">
            {/* Interviews */}
            <div className="flex items-center gap-2 sm:gap-4">
              <span className="text-[9px] tracking-[0.2em] text-zinc-600 uppercase hidden sm:inline">
                Interviews
              </span>
              <span className="text-sm tracking-wider text-white tabular-nums">
                {stats.interviews.toLocaleString()}
              </span>
            </div>

            {/* Divider */}
            <div className="h-4 w-px bg-zinc-800 hidden sm:block" />

            {/* Response Time */}
            <div className="hidden sm:flex items-center gap-4">
              <span className="text-[9px] tracking-[0.2em] text-zinc-600 uppercase">
                Response Time
              </span>
              <span className="text-sm tracking-wider text-white">
                {stats.responseTime}
              </span>
            </div>

            {/* Divider */}
            <div className="h-4 w-px bg-zinc-800 hidden md:block" />

            {/* Match Rate */}
            <div className="hidden md:flex items-center gap-4">
              <span className="text-[9px] tracking-[0.2em] text-zinc-600 uppercase">
                Match Rate
              </span>
              <span className="text-sm tracking-wider text-white tabular-nums">
                {stats.matchRate}%
              </span>
            </div>
          </div>

          {/* Status */}
          <div className="flex items-center gap-4">
            <span className="text-[9px] tracking-[0.2em] text-zinc-600 uppercase hidden sm:inline">
              Status
            </span>
            <div className="flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-matcha-500 animate-pulse shadow-[0_0_6px_rgba(34,197,94,0.6)]" />
              <span className="text-[10px] tracking-[0.15em] text-matcha-500 uppercase font-medium">
                Active
              </span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
