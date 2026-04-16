import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Menu, X } from 'lucide-react'

interface Props {
  onPricingClick: () => void
}

const NAV_LINKS = [
  { to: '/matcha-work', label: 'Matcha Work' },
  { to: '/services', label: 'Consulting' },
]

export default function MarketingNav({ onPricingClick }: Props) {
  const [scrolled, setScrolled] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // Always show "over-hero" styling until scrolled OR menu is open
  const overHero = !scrolled && !menuOpen

  const textColor = overHero ? '#F5F2ED' : 'var(--color-ivory-ink)'

  const handleLinkClick = (action?: () => void) => {
    setMenuOpen(false)
    action?.()
  }

  return (
    <>
      <nav
        className="fixed left-0 right-0 z-50 transition-colors duration-300"
        style={{
          top: '44px',
          backgroundColor: overHero ? 'transparent' : 'rgba(245, 242, 237, 0.92)',
          backdropFilter: overHero ? 'none' : 'blur(10px)',
          WebkitBackdropFilter: overHero ? 'none' : 'blur(10px)',
          borderBottom: overHero ? '1px solid transparent' : '1px solid var(--color-ivory-line)',
        }}
      >
        <div className="max-w-[1440px] mx-auto flex items-center justify-between px-6 sm:px-10 h-16">
          <Link to="/" onClick={() => setMenuOpen(false)} className="flex items-center gap-2">
            <span
              className="text-2xl tracking-tight"
              style={{
                fontFamily: 'var(--font-display)',
                fontWeight: 500,
                color: textColor,
              }}
            >
              Matcha
            </span>
          </Link>

          <div className="hidden md:flex items-center gap-8">
            {NAV_LINKS.map(link => (
              <Link
                key={link.to}
                to={link.to}
                className="text-sm transition-opacity hover:opacity-60"
                style={{ color: textColor }}
              >
                {link.label}
              </Link>
            ))}
            <button
              onClick={onPricingClick}
              className="text-sm transition-opacity hover:opacity-60"
              style={{ color: textColor }}
            >
              Pricing
            </button>
          </div>

          <div className="flex items-center gap-4">
            <Link
              to="/login"
              className="hidden md:inline text-sm transition-opacity hover:opacity-60"
              style={{ color: textColor }}
            >
              Login
            </Link>
            <Link
              to="/contact"
              className="hidden sm:inline-flex items-center px-5 h-9 rounded-full text-sm font-medium transition-opacity hover:opacity-90"
              style={{
                backgroundColor: overHero ? '#F5F2ED' : 'var(--color-ivory-ink)',
                color: overHero ? 'var(--color-ivory-ink)' : '#F5F2ED',
              }}
            >
              Request a Demo
            </Link>
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className="md:hidden inline-flex items-center justify-center w-10 h-10 -mr-2"
              style={{ color: textColor }}
              aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            >
              {menuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>
      </nav>

      {menuOpen && (
        <div
          className="fixed inset-0 z-40 md:hidden"
          style={{ backgroundColor: 'var(--color-ivory-bg)' }}
        >
          <div className="pt-32 px-6 flex flex-col gap-1">
            {NAV_LINKS.map(link => (
              <Link
                key={link.to}
                to={link.to}
                onClick={() => handleLinkClick()}
                className="py-4 text-2xl border-b"
                style={{
                  fontFamily: 'var(--font-display)',
                  color: 'var(--color-ivory-ink)',
                  borderColor: 'var(--color-ivory-line)',
                }}
              >
                {link.label}
              </Link>
            ))}
            <button
              onClick={() => handleLinkClick(onPricingClick)}
              className="py-4 text-2xl text-left border-b"
              style={{
                fontFamily: 'var(--font-display)',
                color: 'var(--color-ivory-ink)',
                borderColor: 'var(--color-ivory-line)',
              }}
            >
              Pricing
            </button>
            <Link
              to="/login"
              onClick={() => setMenuOpen(false)}
              className="py-4 text-2xl border-b"
              style={{
                fontFamily: 'var(--font-display)',
                color: 'var(--color-ivory-ink)',
                borderColor: 'var(--color-ivory-line)',
              }}
            >
              Login
            </Link>
            <Link
              to="/contact"
              onClick={() => setMenuOpen(false)}
              className="mt-6 inline-flex items-center justify-center px-6 h-12 rounded-full text-base font-medium"
              style={{
                backgroundColor: 'var(--color-ivory-ink)',
                color: '#F5F2ED',
              }}
            >
              Request a Demo
            </Link>
          </div>
        </div>
      )}
    </>
  )
}
