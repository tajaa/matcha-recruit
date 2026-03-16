import { lazy, Suspense } from 'react'
import { LinkButton } from '../components/ui'
import { AsciiHalftone } from '../components/AsciiHalftone'

const ParticleSphere = lazy(() => import('../components/ParticleSphere'))

export default function Landing() {
  return (
    <div className="relative min-h-screen bg-zinc-900 text-zinc-100 overflow-hidden">
      <AsciiHalftone />

      <div className="relative z-10 min-h-screen">
        {/* Nav */}
        <nav className="flex items-center justify-between px-8 py-4 border-b border-zinc-700/50">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2.5 pr-6 border-r border-zinc-700/50">
              <img src="/logo.svg" alt="Matcha" className="h-6 w-6" />
              <span className="text-sm font-bold tracking-[0.25em] font-[Orbitron] uppercase">
                Matcha
              </span>
            </div>
            <div className="hidden sm:flex items-center gap-2 text-xs tracking-[0.15em] text-zinc-500 font-[Space_Mono]">
              <span className="inline-block h-2 w-2 bg-emerald-500 rounded-sm" />
              ACTIVE MODULE // HERO
            </div>
          </div>
          <div className="flex items-center gap-6">
            <span className="hidden sm:inline text-xs tracking-[0.2em] text-zinc-400 font-[Space_Mono] uppercase hover:text-zinc-200 cursor-pointer transition-colors">
              Pricing
            </span>
            <LinkButton
              to="/login"
              variant="secondary"
              size="sm"
              className="tracking-[0.2em] font-[Space_Mono] uppercase border border-zinc-600"
            >
              Login
            </LinkButton>
          </div>
        </nav>

        {/* Hero */}
        <section className="relative max-w-7xl mx-auto px-8 min-h-[85vh] flex items-center">
          {/* System tag */}
          <div className="absolute top-8 left-8 text-[11px] tracking-[0.12em] text-zinc-600 font-[Space_Mono] border border-zinc-700/40 px-3 py-1.5 rounded-sm">
            SYSTEM CORE // OFFLINE MODE
          </div>

          {/* Left content */}
          <div className="relative z-10 max-w-xl">
            <h1 className="font-[Orbitron] text-5xl sm:text-6xl lg:text-7xl font-black uppercase tracking-tight leading-[0.95]">
              Workforce
            </h1>
            <h1 className="text-5xl sm:text-6xl lg:text-7xl italic font-light tracking-tight leading-[1.1] mt-1 font-[Space_Grotesk]">
              Intelligence.
            </h1>
            <p className="mt-8 text-lg sm:text-xl text-zinc-400 font-[Space_Grotesk] font-light">
              Increase your{' '}
              <span className="text-amber-500 font-normal">signal to noise ratio</span>.
            </p>
            <div className="mt-10">
              <LinkButton
                to="/login"
                variant="secondary"
                size="lg"
                className="tracking-[0.25em] font-[Space_Mono] uppercase border border-zinc-600 hover:border-zinc-400 px-10"
              >
                Initialize Account
              </LinkButton>
            </div>
          </div>

          {/* Particle Sphere */}
          <div className="absolute right-0 top-0 bottom-0 w-[60%] hidden lg:flex items-center justify-center">
            <Suspense
              fallback={
                <div className="text-zinc-600 font-[Space_Mono] text-[8px] uppercase tracking-[0.4em] animate-pulse">
                  Booting Neural Sphere...
                </div>
              }
            >
              <ParticleSphere className="w-full h-[70vh] opacity-80" />
            </Suspense>
          </div>
        </section>

        {/* Footer */}
        <footer className="border-t border-zinc-700/50 py-6 px-8">
          <div className="flex items-center justify-between max-w-7xl mx-auto">
            <p className="text-[10px] tracking-[0.15em] text-zinc-600 font-[Space_Mono] uppercase">
              &copy; {new Date().getFullYear()} Matcha Systems Inc.
              {import.meta.env.VITE_LANDING_BUILD_VERSION ? (
                <span className="ml-2 text-zinc-700">build {import.meta.env.VITE_LANDING_BUILD_VERSION}</span>
              ) : null}
            </p>
            <div className="flex gap-6">
              {['Terms', 'Privacy', 'Status'].map((link) => (
                <span
                  key={link}
                  className="text-[10px] tracking-[0.15em] text-zinc-600 font-[Space_Mono] uppercase hover:text-zinc-400 cursor-pointer transition-colors"
                >
                  {link}
                </span>
              ))}
            </div>
          </div>
        </footer>
      </div>
    </div>
  )
}
