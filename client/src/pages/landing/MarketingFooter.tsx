import { Link } from 'react-router-dom'

const INK = 'var(--color-ivory-ink)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

export default function MarketingFooter() {
  return (
    <footer className="border-t py-16" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-6 sm:px-10">
        <div className="grid md:grid-cols-4 gap-10">
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
          <FooterCol title="Services" links={[
            { label: 'HR Consulting', to: '/services' },
            { label: 'GRC Consulting', to: '/services' },
            { label: 'Employee Relations', to: '/services' },
            { label: 'AI Integration', to: '/services' },
          ]} />
          <FooterCol title="Company" links={[
            { label: 'Matcha Work', to: '/matcha-work' },
            { label: 'Book a Consultation', to: '/login' },
            { label: 'Client Login', to: '/login' },
          ]} />
          <FooterCol title="Legal" links={[
            { label: 'Terms', to: '/terms' },
            { label: 'Privacy', to: '/privacy' },
            { label: 'Status', to: '/status' },
          ]} />
        </div>
        <div
          className="mt-14 pt-6 border-t text-xs flex flex-col sm:flex-row justify-between gap-3"
          style={{ borderColor: LINE, color: MUTED }}
        >
          <span>© {new Date().getFullYear()} Matcha, Inc. All rights reserved.</span>
          <span>Made with care.</span>
        </div>
      </div>
    </footer>
  )
}

function FooterCol({ title, links }: { title: string; links: { label: string; to: string }[] }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider mb-4" style={{ color: MUTED }}>{title}</div>
      <ul className="space-y-3">
        {links.map(link => (
          <li key={link.label}>
            <Link to={link.to} className="text-sm hover:opacity-60 transition-opacity" style={{ color: INK }}>
              {link.label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}
