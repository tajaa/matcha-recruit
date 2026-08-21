import { useEffect, useMemo, useState } from 'react'
import {
  ArrowLeft,
  ArrowRight,
  Boxes,
  Check,
  ClipboardCheck,
  HelpCircle,
  Package,
  Receipt,
  Sparkles,
  X,
  type LucideIcon,
} from 'lucide-react'
import { Button, Modal, WizardStepper } from '../../../components/ui'
import type { WizardStep } from '../../../components/ui/WizardStepper'

export type InventorySectionHelp = {
  title: string
  summary: string
  bullets: readonly string[]
}

export const INVENTORY_HELP = {
  overview: {
    title: 'Inventory at a glance',
    summary: 'These cards summarize the current operating picture for the selected location filter.',
    bullets: [
      'Tracked items are the active stock records in this view.',
      'On-hand value uses current quantity multiplied by unit cost where both are available.',
      'Needs attention includes unknown, low, and out-of-stock counts. Open orders are queued actions waiting for a decision.',
    ],
  },
  stockHealth: {
    title: 'Stock health',
    summary: 'This bar shows whether each item has a usable count and whether it is above its low-stock threshold.',
    bullets: [
      'Healthy means the count is above the configured threshold.',
      'Low means the count is at or below the threshold; Out means zero or less.',
      'Unknown means the item has never had a physical or system count entered.',
    ],
  },
  movementFlow: {
    title: 'Recent movement flow',
    summary: 'The movement ledger is the audit trail for receipts, usage, sales, stockouts, and count adjustments.',
    bullets: [
      'Increases usually come from receiving a delivery or a positive adjustment.',
      'Out and sale movements explain depletion from team activity and POS imports.',
      'The dashboard shows the latest entries; open an item for its complete ledger.',
    ],
  },
  attention: {
    title: 'Needs attention',
    summary: 'A prioritized list of items that need a count, a replenishment decision, or a follow-up.',
    bullets: [
      'Out-of-stock items appear before low-stock items.',
      'Unknown counts are included because the system cannot assess their risk yet.',
      'Select an item to set a count, review its history, or archive it.',
    ],
  },
  reorder: {
    title: 'Reorder intelligence',
    summary: 'These suggestions estimate usage from recent movement history and translate it into days of cover.',
    bullets: [
      'Suggestions use up to 90 days of recorded movement history.',
      'Confidence increases as the item accumulates consistent usage data.',
      'Treat the suggested quantity as a decision aid, then approve or adjust the order in the queue.',
    ],
  },
  orders: {
    title: 'Order queue',
    summary: 'Orders staged from stock signals or manually queued requests live here until they are approved, received, or cancelled.',
    bullets: [
      'Approve an order when it is ready to place with a supplier.',
      'Receive records the delivery and closes a matching open order.',
      'Cancel removes an order that is no longer needed without changing stock.',
    ],
  },
  catalog: {
    title: 'Inventory catalog',
    summary: 'The catalog is the source list for everything your team counts, receives, uses, and sells through inventory.',
    bullets: [
      'Click a row to open the item detail and movement ledger.',
      'Location-scoped items stay separate from company-wide stock.',
      'Items can be created manually or automatically from channel activity.',
    ],
  },
  addItem: {
    title: 'Add an item',
    summary: 'Use this form for a stock item you want to track before the next receipt or channel event creates it.',
    bullets: [
      'Give the item a clear name your team will recognize.',
      'Choose a location when the stock belongs to one store or site.',
      'Set a count and threshold from the item detail after adding it.',
    ],
  },
  mappings: {
    title: 'Sales mappings',
    summary: 'Mappings connect names from a POS export to the inventory units they deplete.',
    bullets: [
      'Map a sold product to one or more stock units and set units per sale.',
      'Mappings are reused on future imports so the review gets faster over time.',
      'Review mappings before committing a sales import because they change expected stock.',
    ],
  },
  detailCount: {
    title: 'Set count',
    summary: 'Set count records the latest physical or manager-verified quantity for this item.',
    bullets: [
      'Use zero when the item is confirmed out of stock; leave it blank when it is not checked.',
      'Saving creates an adjustment movement so the change remains auditable.',
      'The next count replaces this item’s current on-hand quantity.',
    ],
  },
  detailExpected: {
    title: 'Expected vs last count',
    summary: 'This comparison explains what the ledger predicts versus the last physical baseline.',
    bullets: [
      'Expected includes receipts and recorded depletion since the baseline.',
      'The breakdown separates received, sold, manually used, and stockout movements.',
      'A difference is a prompt to investigate, not an automatic correction.',
    ],
  },
  detailLedger: {
    title: 'Movement ledger',
    summary: 'Every quantity-changing event for this item is listed here in chronological order.',
    bullets: [
      'Use the narrative and movement kind to understand why the count changed.',
      'Receipts, sales, usage, stockouts, and adjustments are kept as separate events.',
      'This ledger is the record to review before making another adjustment.',
    ],
  },
  audit: {
    title: 'Inventory audit',
    summary: 'The audit sheet lets a manager count multiple items in one pass and save only the rows they touched.',
    bullets: [
      'System count is the latest quantity known to the ledger.',
      'Counted is the physical number you enter; blank rows are not changed.',
      'When sales intake is enabled, Expected and Variance show the theoretical gap before you save.',
    ],
  },
} satisfies Record<string, InventorySectionHelp>

export function InventoryHelpButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-w-line px-2 py-1 text-[10px] font-medium text-w-dim transition-colors hover:border-w-accent/40 hover:bg-w-surface2 hover:text-w-text"
      aria-label="Explain this section"
    >
      <HelpCircle size={12} />
      <span>Explain</span>
    </button>
  )
}

export function InventoryHelpModal({ help, onClose }: { help: InventorySectionHelp | null; onClose: () => void }) {
  return (
    <Modal open={help !== null} onClose={onClose} bare>
      {help && (
        <div className="w-full max-w-md overflow-hidden rounded-2xl border border-w-line bg-w-surface shadow-2xl">
          <div className="flex items-center justify-between border-b border-w-line px-5 py-4">
            <div className="flex items-center gap-2 text-sm font-medium text-w-text">
              <HelpCircle className="h-4 w-4 text-w-accent" />
              {help.title}
            </div>
            <button type="button" onClick={onClose} className="rounded-md p-1.5 text-w-dim hover:bg-w-surface2 hover:text-w-text" aria-label="Close explanation">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="px-5 py-5">
            <p className="text-sm leading-6 text-w-dim">{help.summary}</p>
            <ul className="mt-4 space-y-2.5 text-sm text-w-text">
              {help.bullets.map((bullet) => (
                <li key={bullet} className="flex gap-2.5">
                  <Check className="mt-0.5 h-4 w-4 shrink-0 text-w-accent" />
                  <span>{bullet}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="flex justify-end border-t border-w-line px-5 py-3">
            <Button size="sm" onClick={onClose}>Close</Button>
          </div>
        </div>
      )}
    </Modal>
  )
}

type GuideAction = 'audit' | 'receive'

type GuideStep = {
  key: string
  label: string
  title: string
  description: string
  icon: LucideIcon
  bullets: string[]
  action?: GuideAction
  actionLabel?: string
}

const GUIDE_STEPS: GuideStep[] = [
  {
    key: 'catalog',
    label: 'Catalog',
    title: 'Start with the stock you actually manage',
    description: 'Create one item for each supply, ingredient, product, or asset your team needs to count and replenish.',
    icon: Boxes,
    bullets: ['Use names your team will recognize in a channel.', 'Assign a store location when stock is not shared.', 'Items can also appear automatically from channel activity.'],
  },
  {
    key: 'count',
    label: 'Count',
    title: 'Establish a reliable baseline',
    description: 'A first physical count gives the ledger a trustworthy starting point and makes low-stock signals useful.',
    icon: ClipboardCheck,
    bullets: ['Leave untouched rows alone during an audit.', 'Set thresholds for items that need an early reorder warning.', 'You can dictate counts, then review before saving.'],
    action: 'audit',
    actionLabel: 'Open audit sheet',
  },
  {
    key: 'receive',
    label: 'Receive',
    title: 'Record deliveries before stock hits the shelf',
    description: 'Upload an invoice or packing slip, match each line, and commit the receipt to the movement ledger.',
    icon: Receipt,
    bullets: ['Review every parsed line before recording it.', 'Match an open order when the delivery fulfills one.', 'New items can be created from an unmatched delivery line.'],
    action: 'receive',
    actionLabel: 'Record a delivery',
  },
  {
    key: 'act',
    label: 'Act',
    title: 'Work from signals, not guesswork',
    description: 'Use health, movement, attention, and reorder panels to decide what needs a count or order next.',
    icon: Sparkles,
    bullets: ['Review unknown and out-of-stock items first.', 'Use days of cover as a starting point for reorder decisions.', 'Every adjustment remains visible in the item ledger.'],
  },
]

export const INVENTORY_GUIDE_STORAGE_KEY = 'matcha-inventory-guide-v1'

function guideWasSeen(companyKey: string) {
  const key = `${INVENTORY_GUIDE_STORAGE_KEY}:${companyKey}`
  try {
    return localStorage.getItem(key) === '1' || sessionStorage.getItem(key) === '1'
  } catch {
    return false
  }
}

function markGuideSeen(companyKey: string) {
  const key = `${INVENTORY_GUIDE_STORAGE_KEY}:${companyKey}`
  try { localStorage.setItem(key, '1') } catch { /* storage may be blocked */ }
  try { sessionStorage.setItem(key, '1') } catch { /* storage may be blocked */ }
}

export default function InventoryGuideWizard({
  open,
  companyKey,
  onClose,
  onAction,
}: {
  open: boolean
  companyKey: string
  onClose: () => void
  onAction: (action: GuideAction) => void
}) {
  const [step, setStep] = useState(0)
  const [autoDismissed, setAutoDismissed] = useState(false)
  const steps = useMemo<WizardStep[]>(() => GUIDE_STEPS.map(({ key, label }) => ({ key, label })), [])
  const current = GUIDE_STEPS[step]
  const StepIcon = current.icon
  const shouldAutoOpen = !guideWasSeen(companyKey)

  useEffect(() => {
    if (shouldAutoOpen) markGuideSeen(companyKey)
  }, [companyKey, shouldAutoOpen])

  function close() {
    setAutoDismissed(true)
    onClose()
  }

  function handleAction(action: GuideAction) {
    close()
    onAction(action)
  }

  return (
    <Modal open={open || (shouldAutoOpen && !autoDismissed)} onClose={close} bare>
      <div className="max-h-[calc(100dvh-2rem)] w-full max-w-2xl overflow-y-auto rounded-2xl border border-w-line bg-w-surface shadow-2xl">
        <div className="flex items-center justify-between border-b border-w-line px-5 py-4 sm:px-6">
          <div className="flex items-center gap-2 text-sm font-medium text-w-text">
            <Package className="h-4 w-4 text-w-accent" />
            Inventory quick start
          </div>
          <button type="button" onClick={close} className="rounded-md p-1.5 text-w-dim hover:bg-w-surface2 hover:text-w-text" aria-label="Close inventory guide">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="overflow-x-auto border-b border-w-line px-5 py-4 sm:px-6">
          <WizardStepper steps={steps} activeIndex={step} />
        </div>
        <div className="grid gap-5 px-5 py-6 sm:grid-cols-[auto_1fr] sm:px-6 sm:py-7">
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl border border-w-accent/20 bg-w-accent/10 text-w-accent sm:h-20 sm:w-20">
            <StepIcon className="h-8 w-8" />
          </div>
          <div className="min-w-0">
            <p className="text-[10px] font-medium uppercase tracking-[0.16em] text-w-accent">Step {step + 1} of {GUIDE_STEPS.length}</p>
            <h2 className="mt-1 text-xl font-semibold text-w-text">{current.title}</h2>
            <p className="mt-2 text-sm leading-6 text-w-dim">{current.description}</p>
            <ul className="mt-4 space-y-2 text-sm text-w-text">
              {current.bullets.map((bullet) => (
                <li key={bullet} className="flex gap-2.5"><Check className="mt-0.5 h-4 w-4 shrink-0 text-w-accent" /><span>{bullet}</span></li>
              ))}
            </ul>
            {current.action && current.actionLabel && (
              <Button variant="secondary" size="sm" className="mt-5" onClick={() => handleAction(current.action!)}>
                {current.action === 'audit' ? <ClipboardCheck className="h-3.5 w-3.5" /> : <Receipt className="h-3.5 w-3.5" />}
                {current.actionLabel}
              </Button>
            )}
          </div>
        </div>
        <div className="flex items-center justify-between border-t border-w-line px-5 py-4 sm:px-6">
          <button type="button" onClick={close} className="text-sm text-w-dim hover:text-w-text">Skip guide</button>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => setStep((value) => Math.max(0, value - 1))} disabled={step === 0}>
              <ArrowLeft className="h-3.5 w-3.5" /> Back
            </Button>
            {step < GUIDE_STEPS.length - 1 ? (
              <Button size="sm" onClick={() => setStep((value) => value + 1)}>Next <ArrowRight className="h-3.5 w-3.5" /></Button>
            ) : (
              <Button size="sm" onClick={close}>Finish guide</Button>
            )}
          </div>
        </div>
      </div>
    </Modal>
  )
}
