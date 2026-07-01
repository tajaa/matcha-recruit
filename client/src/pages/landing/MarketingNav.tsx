import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Menu, X, ChevronDown } from 'lucide-react'

interface Props {
  onDemoClick?: () => void
}

// The four offerings — primary nav, in sales order.
const PRODUCT_LINKS = [
  { to: '/platform', label: 'Full Platform' },
  // { to: '/matcha-work', label: 'Matcha Work' }, // beta — hidden until launch
  { to: '/matcha-daily', label: 'Matcha Lite' },
  { to: '/compliance', label: 'Compliance', isNew: true },
  { to: '/brokers', label: 'Brokers', isNew: true },
  { to: '/services', label: 'Consulting' },
]

function NewBadge() {
  return (
    <span
      className="absolute -top-2.5 left-1/2 -translate-x-1/2 px-1 rounded-sm text-[7px] font-semibold uppercase tracking-wider leading-[1.3] whitespace-nowrap animate-pulse"
      style={{ backgroundColor: '#6ee7a8', color: '#0F0F0F' }}
    >
      New
    </span>
  )
}

// Content / non-offering — split into the Explore sub-nav.
const EXPLORE_LINKS = [
  { to: '/resources', label: 'Resources' },
  { to: '/blog', label: 'Blog' },
  { to: '/news', label: 'News' },
]

const TEXT_COLOR = '#F5F2ED'
const PANEL_BG = '#161513'

export default function MarketingNav({ onDemoClick }: Props) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [exploreOpen, setExploreOpen] = useState(false)

  const closeAll = () => {
    setMenuOpen(false)
    setExploreOpen(false)
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
          <Link to="/" onClick={closeAll} className="flex items-center gap-2">
            <span
              className="text-2xl tracking-tight"
              style={{
                fontFamily: 'var(--font-display)',
                fontWeight: 500,
                color: TEXT_COLOR,
              }}
            >
              MATCHA
            </span>
          </Link>

          <div className="hidden md:flex items-center gap-8">
            {PRODUCT_LINKS.map(link => (
              <Link
                key={link.to}
                to={link.to}
                className="relative text-sm transition-opacity hover:opacity-60"
                style={{ color: TEXT_COLOR }}
              >
                {link.label}
                {link.isNew && <NewBadge />}
              </Link>
            ))}

            {/* Explore sub-nav — Blog / Resources / News split out from offerings */}
            <div
              className="relative"
              onMouseEnter={() => setExploreOpen(true)}
              onMouseLeave={() => setExploreOpen(false)}
            >
              <button
                type="button"
                onClick={() => setExploreOpen(v => !v)}
                className="inline-flex items-center gap-1 text-sm transition-opacity hover:opacity-60"
                style={{ color: TEXT_COLOR }}
                aria-expanded={exploreOpen}
                aria-haspopup="true"
              >
                Explore
                <ChevronDown
                  className="w-3.5 h-3.5 transition-transform duration-200"
                  style={{ transform: exploreOpen ? 'rotate(180deg)' : 'none' }}
                />
              </button>

              {exploreOpen && (
                <div
                  className="absolute right-0 top-full pt-3"
                  // pt-3 keeps a hover bridge between trigger and panel
                >
                  <div
                    className="min-w-[160px] rounded-lg overflow-hidden py-1.5"
                    style={{
                      backgroundColor: PANEL_BG,
                      border: '1px solid rgba(245, 242, 237, 0.12)',
                      boxShadow: '0 20px 40px -12px rgba(0,0,0,0.55)',
                    }}
                  >
                    {EXPLORE_LINKS.map(link => (
                      <Link
                        key={link.to}
                        to={link.to}
                        onClick={closeAll}
                        className="block px-4 py-2.5 text-sm transition-colors hover:bg-white/[0.06]"
                        style={{ color: TEXT_COLOR }}
                      >
                        {link.label}
                      </Link>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center gap-4">
            <Link
              to="/login"
              className="hidden md:inline text-sm transition-opacity hover:opacity-60"
              style={{ color: TEXT_COLOR }}
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
              style={{ color: TEXT_COLOR }}
              aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            >
              {menuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>
      </nav>

      {menuOpen && (
        <div
          className="fixed inset-0 z-40 md:hidden overflow-y-auto"
          style={{ backgroundColor: '#0F0F0F' }}
        >
          <div className="pt-28 px-6 pb-12 flex flex-col gap-1">
            {PRODUCT_LINKS.map(link => (
              <Link
                key={link.to}
                to={link.to}
                onClick={closeAll}
                className="py-4 text-2xl border-b"
                style={{
                  fontFamily: 'var(--font-display)',
                  color: '#F5F2ED',
                  borderColor: 'rgba(245, 242, 237, 0.15)',
                }}
              >
                <span className="relative inline-block">
                  {link.label}
                  {link.isNew && <NewBadge />}
                </span>
              </Link>
            ))}

            {/* Explore sub-section */}
            <div
              className="mt-6 mb-2 text-[11px] uppercase tracking-[0.18em] font-mono"
              style={{ color: 'rgba(245, 242, 237, 0.45)' }}
            >
              Explore
            </div>
            {EXPLORE_LINKS.map(link => (
              <Link
                key={link.to}
                to={link.to}
                onClick={closeAll}
                className="py-3 text-lg border-b"
                style={{
                  color: 'rgba(245, 242, 237, 0.85)',
                  borderColor: 'rgba(245, 242, 237, 0.1)',
                }}
              >
                {link.label}
              </Link>
            ))}

            <Link
              to="/login"
              onClick={closeAll}
              className="mt-6 py-3 text-lg"
              style={{ color: '#F5F2ED' }}
            >
              Login
            </Link>
            <button
              onClick={() => { closeAll(); onDemoClick?.() }}
              className="mt-4 inline-flex items-center justify-center px-6 h-12 rounded-full text-base font-medium cursor-pointer"
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
