import { Link } from 'react-router-dom';

export function ForCandidates() {
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
        <Link to="/" className="flex items-center gap-3 group">
          <div className="w-2 h-2 rounded-full bg-matcha-500 shadow-[0_0_10px_rgba(34,197,94,0.8)] group-hover:scale-125 transition-transform" />
          <span className="text-xs tracking-[0.3em] uppercase text-matcha-500 font-medium">
            Matcha
          </span>
        </Link>

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
      <main className="relative z-10 container mx-auto px-4 sm:px-8 py-20 max-w-4xl">
        <div className="space-y-16">
          <div className="space-y-6">
            <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-white">
              For Candidates
            </h1>
            <p className="text-zinc-400 text-lg leading-relaxed max-w-2xl">
              With 15 years in hiring and 5,000+ people placed, we know where fit actually matters.
              If you are open to opportunities and want to be considered for roles we are actively recruiting for, you can apply here.
            </p>
            <div>
              <Link
                to="/register"
                className="inline-flex items-center justify-center px-8 py-3 text-xs font-medium tracking-widest uppercase bg-matcha-500 text-black hover:bg-matcha-400 transition-colors"
              >
                Apply Now
              </Link>
            </div>
          </div>

          <div className="border-t border-zinc-800 pt-16">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-12">
              <div className="space-y-4">
                <h2 className="text-sm tracking-[0.2em] uppercase text-matcha-500">
                  Our Philosophy
                </h2>
                <ul className="space-y-4">
                  <li className="flex gap-4 items-start">
                    <span className="w-1.5 h-1.5 rounded-full bg-zinc-700 mt-2 shrink-0" />
                    <span className="text-zinc-300">Not everyone is a fit and that’s okay</span>
                  </li>
                  <li className="flex gap-4 items-start">
                    <span className="w-1.5 h-1.5 rounded-full bg-zinc-700 mt-2 shrink-0" />
                    <span className="text-zinc-300">We review applications thoughtfully</span>
                  </li>
                  <li className="flex gap-4 items-start">
                    <span className="w-1.5 h-1.5 rounded-full bg-zinc-700 mt-2 shrink-0" />
                    <span className="text-zinc-300">If there is alignment, we will reach out</span>
                  </li>
                  <li className="flex gap-4 items-start">
                    <span className="w-1.5 h-1.5 rounded-full bg-zinc-700 mt-2 shrink-0" />
                    <span className="text-zinc-300">This is not a mass application platform</span>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
