import { Plus } from 'lucide-react'
import { EYEBROW, WRAP } from './shared'

// Keep every answer true of the shipped product — this is the section people
// screenshot when they compare us to the big builders.
const faqs: [string, string][] = [
  [
    'Do I need any other apps or plugins?',
    'No. The site builder, store, checkout, bookings, newsletters, forms, reviews, blog, domains and email are all built by Gummfit. There’s no app store, because there’s nothing to add on.',
  ],
  [
    'How do payments work?',
    'Connect a Stripe account in a few minutes and payouts go straight to you. Payments are built into checkout, so there’s no separate payment app to install. Card processing is billed by Stripe; Gummfit’s per-sale fee depends on your plan.',
  ],
  [
    'Can I use my own domain?',
    'Yes. Register a new domain through Gummfit or connect one you already own, then add private email mailboxes on it.',
  ],
  [
    'Do I need to know how to code or design?',
    'No. Describe your business and our AI drafts a starting site. From there you can change anything in the visual editor.',
  ],
  [
    'Can I cancel anytime?',
    'Yes. Change or cancel your plan from your billing settings whenever you like — no contracts.',
  ],
]

export default function Faq() {
  return (
    <section id="faq" className={`scroll-mt-24 grid gap-10 border-t border-white/10 py-24 sm:py-32 lg:grid-cols-[0.8fr_1.2fr] lg:gap-20 ${WRAP}`}>
      <div>
        <p className={`${EYEBROW} text-[#d4ff72]`}>Questions</p>
        <h2 className="mt-4 text-4xl font-semibold leading-[0.97] tracking-[-0.065em] text-[#f8f7f0] sm:text-5xl">The short answers.</h2>
      </div>
      <div className="border-t border-white/10">
        {faqs.map(([question, answer]) => (
          <details key={question} className="group border-b border-white/10 py-5">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-lg font-semibold tracking-[-0.03em] text-[#f3f1e7] [&::-webkit-details-marker]:hidden">
              {question}
              <Plus className="h-5 w-5 shrink-0 text-[#d4ff72] motion-safe:transition-transform group-open:rotate-45" />
            </summary>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-[#afb3a7]">{answer}</p>
          </details>
        ))}
      </div>
    </section>
  )
}
