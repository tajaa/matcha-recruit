import { useState } from 'react'
import { ArrowLeft, ArrowRight, MapPin, Palette, Sparkles, Users } from 'lucide-react'
import { Button, Modal } from './ui'

type GuideStep = {
  icon: typeof Palette
  eyebrow: string
  title: string
  body: string
  action?: 'create' | 'locals'
}

const STEPS: GuideStep[] = [
  {
    icon: Palette,
    eyebrow: '1 · Build the offer',
    title: 'Start with a campaign',
    body: 'Create a QR campaign for flyers and Locals, or choose a location campaign to reach nearby followers with a one-time push.',
    action: 'create',
  },
  {
    icon: Sparkles,
    eyebrow: '2 · Make it yours',
    title: 'Design the flyer',
    body: 'Open Design flyer to start from a template, swap palettes, add stickers or your logo, and fine-tune the canvas with drag, resize, and rotation controls.',
  },
  {
    icon: Users,
    eyebrow: '3 · Share with regulars',
    title: 'Post QR offers to Locals',
    body: 'Use Share campaign, then Post to Locals. Members see the flyer and can open the claim link without needing to find your campaign page first.',
    action: 'locals',
  },
  {
    icon: MapPin,
    eyebrow: '4 · Reach nearby',
    title: 'Push location offers',
    body: 'Location campaigns stay push-only. Send them once to followers with a fresh device location inside your configured radius, then track the result on Campaigns.',
  },
]

type BrandFeatureWizardProps = {
  open: boolean
  onClose: () => void
  onCreateCampaign: () => void
  onOpenLocals: () => void
}

export function BrandFeatureWizard({ open, onClose, onCreateCampaign, onOpenLocals }: BrandFeatureWizardProps) {
  const [stepIndex, setStepIndex] = useState(0)
  const step = STEPS[stepIndex]
  const Icon = step.icon
  const isLast = stepIndex === STEPS.length - 1

  function close() {
    setStepIndex(0)
    onClose()
  }

  function next() {
    if (isLast) close()
    else setStepIndex((current) => current + 1)
  }

  return (
    <Modal open={open} onClose={close} title="Campaigns, in four moves">
      <div className="space-y-5">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-tu-accent/15 text-tu-accent">
              <Icon className="h-5 w-5" />
            </span>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-tu-accent">{step.eyebrow}</p>
              <p className="mt-1 text-xs text-tu-faint">{stepIndex + 1} of {STEPS.length}</p>
            </div>
          </div>
          <div className="flex gap-1" aria-label="Wizard progress">
            {STEPS.map((item, index) => (
              <span key={item.title} className={`h-1.5 w-7 rounded-full ${index <= stepIndex ? 'bg-tu-accent' : 'bg-tu-panel2'}`} />
            ))}
          </div>
        </div>

        <div>
          <h2 className="text-xl font-bold">{step.title}</h2>
          <p className="mt-2 text-sm leading-6 text-tu-dim">{step.body}</p>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-tu-border pt-4">
          <Button variant="ghost" size="sm" onClick={close}>Skip guide</Button>
          <div className="flex gap-2">
            {stepIndex > 0 && (
              <Button variant="soft" size="sm" onClick={() => setStepIndex((current) => current - 1)}>
                <ArrowLeft className="h-3.5 w-3.5" /> Back
              </Button>
            )}
            {step.action === 'create' && <Button size="sm" onClick={onCreateCampaign}>Create campaign</Button>}
            {step.action === 'locals' && <Button size="sm" onClick={onOpenLocals}>Open Locals</Button>}
            <Button variant="soft" size="sm" onClick={next}>
              {isLast ? 'Finish' : 'Next'} {!isLast && <ArrowRight className="h-3.5 w-3.5" />}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  )
}
