import { Link, useLocation } from 'react-router-dom'
import { LinkButton } from '../../components/ui'

interface Props {
  onPricingClick: () => void
}

const NAV_LINKS = [
  { to: '/matcha-work', label: 'Matcha Work' },
  { to: '/services', label: 'Services' },
]

export default function LandingNav({ onPricingClick }: Props) {
  const { pathname } = useLocation()

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 flex items-center justify-center px-6 pt-5">
      <div
        className="flex items-center justify-between w-full max-w-6xl px-6 py-3 rounded-full border border-zinc-700/30"
        style={{
          background: 'rgba(24, 24, 27, 0.6)',
          backdropFilter: 'blur(16px) saturate(1.4)',
          WebkitBackdropFilter: 'blur(16px) saturate(1.4)',
          boxShadow: '0 0 20px rgba(0,0,0,0.3), inset 0 0.5px 0 rgba(255,255,255,0.05)',
        }}
      >
        <Link to="/" className="flex items-center gap-2.5">
          <img src="/logo.svg" alt="Matcha" className="h-5 w-5" />
          <span className="text-sm font-[Orbitron] font-bold tracking-[0.25em] uppercase text-zinc-100">
            Matcha
          </span>
        </Link>
        <div className="hidden sm:flex items-center gap-1.5">
          <span className="relative flex h-1.5 w-1.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60" />
            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
          </span>
          <span className="text-[10px] text-zinc-500 uppercase">
            Systems Online
          </span>
        </div>
        <div className="flex items-center gap-5">
          {NAV_LINKS.map(link => (
            <Link
              key={link.to}
              to={link.to}
              className={`hidden sm:inline text-[11px] uppercase transition-colors duration-300 ${
                pathname === link.to ? 'text-emerald-400' : 'text-zinc-400 hover:text-emerald-400'
              }`}
            >
              {link.label}
            </Link>
          ))}
          <a
            href="#about"
            className="hidden sm:inline text-[11px] text-zinc-400 uppercase hover:text-emerald-400 cursor-pointer transition-colors duration-300"
          >
            About
          </a>
          <span
            onClick={onPricingClick}
            className="hidden sm:inline text-[11px] text-zinc-400 uppercase hover:text-emerald-400 cursor-pointer transition-colors duration-300"
          >
            Pricing
          </span>
          <LinkButton
            to="/login"
            variant="ghost"
            size="sm"
            className="uppercase text-zinc-300 hover:text-emerald-400 border border-zinc-600/50 hover:border-emerald-500/40 rounded-full px-5 transition-all duration-300"
          >
            Login
          </LinkButton>
        </div>
      </div>
    </nav>
  )
}
