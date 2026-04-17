import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Menu, X } from 'lucide-react'

interface Props {
  onPricingClick: () => void
  onDemoClick: () => void
}

const NAV_LINKS = [
  { to: '/', label: 'Platform' },
  { to: '/matcha-work', label: 'Matcha Work' },
  { to: '/services', label: 'Consulting' },
]

export default function MarketingNav({ onPricingClick, onDemoClick }: Props) {
  const [menuOpen, setMenuOpen] = useState(false)

  const textColor = '#F5F2ED'

  const handleLinkClick = (action?: () => void) => {
    setMenuOpen(false)
    action?.()
  }

  return (
    <>
      <nav
        className="fixed left-0 right-0 z-50 transition-colors duration-300"
        style={{
          top: 0,
          backgroundColor: '#0F0F0F',
          borderBottom: '1px solid rgba(245, 242, 237, 0.12)',
        }}
      >
        <div className="max-w-[1440px] mx-auto flex items-center justify-between px-6 sm:px-10 h-12">
          <Link to="/" onClick={() => setMenuOpen(false)} className="flex items-center gap-2">
            <span
              className="text-2xl tracking-tight"
              style={{
                fontFamily: 'var(--font-display)',
                fontWeight: 500,
                color: textColor,
              }}
            >
              MATCHA
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
            <button
              onClick={onDemoClick}
              className="hidden sm:inline-flex items-center px-5 h-9 rounded-full text-sm font-medium transition-opacity hover:opacity-90 cursor-pointer"
              style={{
                backgroundColor: '#F5F2ED',
                color: '#0F0F0F',
              }}
            >
              Request a Demo
            </button>
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
          style={{ backgroundColor: '#0F0F0F' }}
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
                  color: '#F5F2ED',
                  borderColor: 'rgba(245, 242, 237, 0.15)',
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
                color: '#F5F2ED',
                borderColor: 'rgba(245, 242, 237, 0.15)',
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
                color: '#F5F2ED',
                borderColor: 'rgba(245, 242, 237, 0.15)',
              }}
            >
              Login
            </Link>
            <button
              onClick={() => { setMenuOpen(false); onDemoClick() }}
              className="mt-6 inline-flex items-center justify-center px-6 h-12 rounded-full text-base font-medium cursor-pointer"
              style={{
                backgroundColor: '#F5F2ED',
                color: '#0F0F0F',
              }}
            >
              Request a Demo
            </button>
          </div>
        </div>
      )}
    </>
  )
}
