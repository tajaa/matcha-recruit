import { Link } from 'react-router-dom'
import { Check } from 'lucide-react'
import { useMatchaLitePricing } from '../../api/matchaLitePricing'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const DISPLAY = 'var(--font-display)'

const LITE_FEATURES = [
  'Incident reporting & investigation workflows',
  'Employee records',
  'Progressive discipline',
]

export default function SignupPicker() {
  const pricing = useMatchaLitePricing()
  const blockPriceDollars = (pricing?.effective_price_per_block_cents ?? 5000) / 100
  const blockSize = pricing?.block_size ?? 10

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-4 py-16" style={{ backgroundColor: BG, color: INK }}>
      <Link to="/" className="mb-12 text-center">
        <span className="text-3xl tracking-tight" style={{ fontFamily: DISPLAY, fontWeight: 500, color: INK }}>
          Matcha
        </span>
      </Link>

      <div className="w-full max-w-sm">
        <h1
          className="text-4xl sm:text-5xl tracking-tight text-center mb-3"
          style={{ fontFamily: DISPLAY, fontWeight: 500, color: INK }}
        >
          Get started
        </h1>
        <p className="text-center text-sm mb-10" style={{ color: MUTED }}>
          Pick the plan that fits. You can upgrade any time.
        </p>

        <div className="grid grid-cols-1 gap-4">
          {/* Matcha Lite tier */}
          <div
            className="rounded-2xl p-8 flex flex-col"
            style={{ border: `1px solid ${INK}`, backgroundColor: INK, color: BG }}
          >
            <div className="mb-6">
              <span
                className="inline-block text-[10px] tracking-wider uppercase px-2 py-1 rounded mb-4"
                style={{ border: '1px solid rgba(255,255,255,0.25)', color: 'rgba(255,255,255,0.6)' }}
              >
                Lite
              </span>
              <h2 className="text-2xl mb-1" style={{ fontFamily: DISPLAY, fontWeight: 500, color: BG }}>
                Matcha Lite
              </h2>
              <p className="text-sm" style={{ color: 'rgba(255,255,255,0.6)' }}>
                Incident reporting, HR records &amp; discipline.
              </p>
            </div>

            <div className="mb-6">
              <span className="text-3xl font-semibold" style={{ color: BG, fontFamily: DISPLAY }}>${blockPriceDollars}</span>
              <span className="text-sm ml-2" style={{ color: 'rgba(255,255,255,0.6)' }}>/month per {blockSize} employees</span>
            </div>

            <ul className="flex flex-col gap-3 mb-8 flex-1">
              {LITE_FEATURES.map(f => (
                <li key={f} className="flex items-start gap-2 text-sm" style={{ color: BG }}>
                  <Check className="w-4 h-4 mt-0.5 shrink-0" style={{ color: BG, opacity: 0.6 }} />
                  {f}
                </li>
              ))}
            </ul>

            <Link
              to="/lite/signup"
              className="w-full h-12 rounded-full text-sm font-medium flex items-center justify-center transition-opacity hover:opacity-80"
              style={{ backgroundColor: BG, color: INK }}
            >
              Get started →
            </Link>
          </div>
        </div>

        <p className="mt-8 text-xs text-center" style={{ color: MUTED }}>
          Already have an account?{' '}
          <Link to="/login" className="underline" style={{ color: INK }}>
            Sign in
          </Link>
          {' · '}
          Need the full platform?{' '}
          <Link to="/" className="underline" style={{ color: INK }}>
            Talk to us
          </Link>
        </p>
      </div>
    </div>
  )
}
