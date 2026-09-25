import { useState } from 'react'
import { Link } from 'react-router-dom'
import { NewsletterHeroSection } from '../../components/landing/NewsletterHeroSection'
import { PricingContactModal } from '../../components/marketing/PricingContactModal'

import { BOARD, BODY, MONO, PAPER, hexA } from '../../components/marketing/kit/theme'
import { display, mono } from '../../components/marketing/kit/styles'

// Board-dark footer in the marketing kit's type (same as /matcha-scheduling).
const INK = PAPER
const MUTED = hexA(PAPER, 0.55)
const LINE = hexA(PAPER, 0.1)

type FooterLink =
  | { label: string; to: string }
  | { label: string; onClick: () => void }

export default function MarketingFooter({
  newsletterVariant = 'board',
}: { newsletterVariant?: 'caramel' | 'matcha' | 'board' } = {}) {
  const [consultationOpen, setConsultationOpen] = useState(false)

  return (
    <>
      {/* Cool newsletter band — renders on every page that uses the footer. */}
      <NewsletterHeroSection variant={newsletterVariant} />
    <footer className="border-t py-16" style={{ borderColor: LINE, backgroundColor: BOARD.PAPER, color: INK, fontFamily: BODY }}>
      <div className="max-w-[1440px] mx-auto px-6 sm:px-10">
        <div className="grid md:grid-cols-5 gap-10">
          <div>
            <span
              style={{ ...display, fontWeight: 600, fontSize: 28, letterSpacing: '-0.03em', color: INK }}
            >
              Matcha
            </span>
            <p className="mt-4 text-sm max-w-xs" style={{ color: MUTED }}>
              Bespoke HR, GRC, employee relations, and AI integration consulting.
            </p>
          </div>
          <FooterCol title="Products" links={[
            { label: 'Scheduling', to: '/matcha-scheduling' },
            { label: 'Matcha Lite', to: '/matcha-lite' },
          ]} />
          <FooterCol title="Explore" links={[
            { label: 'Resources', to: '/resources' },
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
              <span className="ml-2 opacity-60" style={{ fontFamily: MONO }}>build {import.meta.env.VITE_LANDING_BUILD_VERSION}</span>
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
      <div className="mb-4" style={mono('10px', { color: MUTED })}>{title}</div>
      <ul className="space-y-3">
        {links.map(link => (
          <li key={link.label}>
            {'to' in link ? (
              <Link to={link.to} className="text-[14px] hover:opacity-60 transition-opacity" style={{ color: INK }}>
                {link.label}
              </Link>
            ) : (
              <button
                type="button"
                onClick={link.onClick}
                className="text-[14px] hover:opacity-60 transition-opacity text-left"
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
