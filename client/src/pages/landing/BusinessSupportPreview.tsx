import { useId, useState } from 'react'
import { ArrowRight } from 'lucide-react'
import { display, mono } from '../../components/marketing/kit/styles'
import { INK, INK_SOFT, PAPER, STAMP, hexA } from '../../components/marketing/kit/theme'

const EXAMPLES = [
  {
    id: 'hr', label: 'HR',
    challenge: '“We’re hiring. Our people processes need to catch up.”',
    title: 'A stronger start for every hire.',
    steps: ['Define the role & interview plan', 'Build the hiring workflow', 'Create the onboarding playbook'],
    link: 'Explore HR support',
  },
  {
    id: 'operations', label: 'Operations',
    challenge: '“The same information gets entered into three different tools.”',
    title: 'Less copying. Fewer handoffs.',
    steps: ['Map the workflow', 'Connect & automate the tools', 'Write the team playbook'],
    link: 'Explore operations support',
  },
  {
    id: 'technology', label: 'Technology',
    challenge: '“Our team needs a private AI assistant for our internal knowledge.”',
    title: 'Your knowledge. A tool that fits.',
    steps: ['Define data & access controls', 'Build the closed AI workflow', 'Test & train your team'],
    link: 'Explore technology solutions',
  },
] as const

/** Illustrative scopes make the service concrete without implying a live client project. */
export default function BusinessSupportPreview() {
  const [active, setActive] = useState(0)
  const panelId = useId()
  const example = EXAMPLES[active]

  return (
    <div className="relative min-w-0" style={{ color: INK }}>
      <div aria-hidden className="absolute -right-2 -top-2 bottom-3 left-3 border" style={{ backgroundColor: hexA(PAPER, 0.12), borderColor: hexA(PAPER, 0.16) }} />
      <div className="relative border p-5 sm:p-7" style={{ backgroundColor: PAPER, borderColor: hexA(INK, 0.12), boxShadow: `0 24px 60px -32px ${hexA('#000000', 0.5)}` }}>
        <div className="flex items-center justify-between gap-3">
          <span style={mono('10px', { color: INK_SOFT })}>Matcha / In practice</span>
          <span className="flex items-center gap-2 text-[11px]" style={{ color: INK_SOFT }}><span aria-hidden className="h-1 w-1 rounded-full" style={{ backgroundColor: STAMP }} />Illustrative example</span>
        </div>
        <div role="group" aria-label="Explore service examples" className="mt-6 flex gap-1 border-b pb-4" style={{ borderColor: hexA(INK, 0.15) }}>
          {EXAMPLES.map(({ id, label }, i) => (
            <button key={id} type="button" aria-pressed={i === active} aria-controls={panelId} onClick={() => setActive(i)}
              className="sched-focus min-h-10 min-w-0 flex-1 rounded-full px-2 text-[13px] sm:px-3 font-medium transition-colors hover:bg-[#18211B]/[0.06] motion-reduce:transition-none"
              style={{ backgroundColor: i === active ? INK : 'transparent', color: i === active ? PAPER : INK_SOFT, outlineColor: INK }}>
              {label}
            </button>
          ))}
        </div>
        <div id={panelId} aria-live="polite" aria-atomic="true" className="pt-6">
          <h2 className="min-h-[2.1em] max-w-[20ch]" style={{ ...display, fontSize: 'clamp(1.6rem, 2.2vw, 1.9rem)', lineHeight: 1.05 }}>{example.title}</h2>
          <p className="mb-5 mt-3 min-h-[4.5em] text-[15px] sm:min-h-[3em] leading-[1.5]" style={{ color: INK_SOFT }}>{example.challenge}</p>
          <div className="border-t pt-5" style={{ borderColor: hexA(INK, 0.15) }}>
            <div style={mono('10px', { color: STAMP })}>What we can put in place</div>
            <ol className="mt-4 space-y-3">
              {example.steps.map((step, i) => (
                <li key={step} className="flex items-start gap-3 text-[13px] leading-5">
                  <span className="mt-0.5 shrink-0" style={mono('10px', { color: STAMP })}>0{i + 1}</span>{step}
                </li>
              ))}
            </ol>
          </div>
          <a href={`#${example.id}`} className="sched-link sched-focus mt-5 inline-flex items-center gap-2 rounded text-[13px] font-medium" style={{ color: INK, outlineColor: INK }}>{example.link}<ArrowRight size={15} /></a>
        </div>
      </div>
    </div>
  )
}
