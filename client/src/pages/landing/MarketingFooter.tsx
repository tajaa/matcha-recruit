import { useState } from 'react'
import { Link } from 'react-router-dom'
import { NewsletterHeroSection } from '../../components/landing/NewsletterHeroSection'
import { PricingContactModal } from '../../components/PricingContactModal'

const INK = 'var(--color-ivory-ink)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

type FooterLink =
  | { label: string; to: string }
  | { label: string; onClick: () => void }

export default function MarketingFooter() {
  const [consultationOpen, setConsultationOpen] = useState(false)

  return (
    <>
      {/* Cool newsletter band — renders on every page that uses the footer. */}
      <NewsletterHeroSection />
    <footer className="border-t py-16" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-6 sm:px-10">
        <div className="grid md:grid-cols-5 gap-10">
          <div>
            <span
              className="text-2xl tracking-tight"
              style={{ fontFamily: DISPLAY, fontWeight: 500, color: INK }}
            >
              Matcha
            </span>
            <p className="mt-4 text-sm max-w-xs" style={{ color: MUTED }}>
              Bespoke HR, GRC, employee relations, and AI integration consulting.
            </p>
          </div>
          <FooterCol title="Products" links={[
            { label: 'Matcha Lite', to: '/matcha-lite' },
          ]} />
          <FooterCol title="Explore" links={[
            { label: 'Resources', to: '/resources' },
            { label: 'Blog', to: '/blog' },
            { label: 'News', to: '/news' },
          ]} />
          <FooterCol title="Company" links={[
            { label: 'Book a Consultation', onClick: () => setConsultationOpen(true) },
            { label: 'Client Login', to: '/login' },
          ]} />
          <FooterCol title="Legal" links={[
            { label: 'Terms', to: '/terms' },
            { label: 'Privacy', to: '/privacy' },
          ]} />
        </div>
        <div
          className="mt-14 pt-6 border-t text-xs flex flex-col sm:flex-row justify-between gap-3"
          style={{ borderColor: LINE, color: MUTED }}
        >
          <span>
            © {new Date().getFullYear()} Matcha, Inc. All rights reserved.
            {import.meta.env.VITE_LANDING_BUILD_VERSION ? (
              <span className="ml-2 font-mono opacity-60">build {import.meta.env.VITE_LANDING_BUILD_VERSION}</span>
            ) : null}
          </span>
          <span>Made with care.</span>
        </div>
      </div>
      <PricingContactModal
        isOpen={consultationOpen}
        onClose={() => setConsultationOpen(false)}
        mode="consultation"
      />
    </footer>
    </>
  )
}

function FooterCol({ title, links }: { title: string; links: FooterLink[] }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider mb-4" style={{ color: MUTED }}>{title}</div>
      <ul className="space-y-3">
        {links.map(link => (
          <li key={link.label}>
            {'to' in link ? (
              <Link to={link.to} className="text-sm hover:opacity-60 transition-opacity" style={{ color: INK }}>
                {link.label}
              </Link>
            ) : (
              <button
                type="button"
                onClick={link.onClick}
                className="text-sm hover:opacity-60 transition-opacity text-left"
                style={{ color: INK }}
              >
                {link.label}
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
