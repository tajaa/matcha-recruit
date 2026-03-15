import { LinkButton } from '../components/ui'
import { AsciiHalftone } from '../components/AsciiHalftone'

const cities = [
  { name: 'TORONTO', x: '72%', y: '12%' },
  { name: 'CHICAGO', x: '63%', y: '15%' },
  { name: 'NY', x: '78%', y: '18%' },
  { name: 'SF', x: '52%', y: '24%' },
  { name: 'LA', x: '54%', y: '32%' },
  { name: 'AUSTIN', x: '65%', y: '30%' },
  { name: 'MIAMI', x: '76%', y: '34%' },
  { name: 'MEXICO CITY', x: '62%', y: '44%' },
  { name: 'BOG', x: '80%', y: '56%' },
  { name: 'LIMA', x: '72%', y: '70%' },
  { name: 'SAO', x: '82%', y: '66%' },
  { name: 'BUENOS AIRES', x: '76%', y: '78%' },
]

function Globe() {
  return (
    <div className="absolute inset-0 overflow-hidden">
      {/* Concentric ellipses for wireframe sphere */}
      {[100, 90, 78, 64, 48, 30].map((size, i) => (
        <div
          key={`h-${i}`}
          className="globe-ring"
          style={{
            width: `${size}%`,
            height: `${size}%`,
            left: `${50 - size / 2 + 15}%`,
            top: `${50 - size / 2}%`,
          }}
        />
      ))}
      {/* Vertical arcs */}
      {[20, 35, 50, 65, 80].map((left, i) => (
        <div
          key={`v-${i}`}
          className="globe-ring"
          style={{
            width: '60%',
            height: '96%',
            left: `${left}%`,
            top: '2%',
            transform: `rotateY(${60 - i * 15}deg)`,
          }}
        />
      ))}
      {/* Meridian lines */}
      {[30, 45, 60, 75].map((top, i) => (
        <div
          key={`m-${i}`}
          className="absolute border-t border-zinc-700/10"
          style={{ width: '80%', left: '25%', top: `${top}%` }}
        />
      ))}
      {/* City dots + labels */}
      {cities.map((city) => (
        <div
          key={city.name}
          className="absolute"
          style={{ left: city.x, top: city.y }}
        >
          <div className="relative dot-ping h-2 w-2 rounded-full bg-amber-500" />
          <span className="absolute left-3 top-[-3px] text-[10px] tracking-[0.2em] text-zinc-500 font-[Space_Mono] whitespace-nowrap">
            {city.name}
          </span>
        </div>
      ))}
    </div>
  )
}

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

          {/* Globe */}
          <div className="absolute right-0 top-0 bottom-0 w-[65%] hidden md:block">
            <Globe />
          </div>
        </section>

        {/* Footer */}
        <footer className="border-t border-zinc-700/50 py-6 px-8">
          <div className="flex items-center justify-between max-w-7xl mx-auto">
            <p className="text-[10px] tracking-[0.15em] text-zinc-600 font-[Space_Mono] uppercase">
              &copy; {new Date().getFullYear()} Matcha Systems Inc.
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
