import { useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  ArrowLeft, ArrowRight, BarChart3, BookOpen, Check,
  ClipboardCheck, Inbox, ListChecks, Map, Upload, X,
} from 'lucide-react'
import { Button, Modal, WizardStepper } from '../../../components/ui'
import type { WizardStep } from '../../../components/ui/WizardStepper'

export const SALES_INTAKE_WIZARD_STORAGE_KEY = 'matcha-sales-intake-wizard-v1'

type Action = 'mappings' | 'import' | 'audit'

type Props = {
  open: boolean
  companyKey: string
  onClose: () => void
  onAction: (action: Action) => void
}

type GuideStep = {
  key: string
  label: string
  title: string
  description: string
  icon: ReactNode
  bullets: string[]
  action?: Action
  actionLabel?: string
}

const GUIDE_STEPS: GuideStep[] = [
  {
    key: 'overview',
    label: 'Overview',
    title: 'Turn POS exports into a real stock expectation',
    description: 'Sales intake connects what your POS sold to the inventory ledger, so the Audit sheet can show what should be on hand before you count it.',
    icon: <BarChart3 className="h-10 w-10 text-emerald-300" />,
    bullets: [
      'Sales reduce current quantity as machine-recorded depletion.',
      'Physical counts remain the correction and baseline source of truth.',
      'Start with one location and one recent export for a clean first run.',
    ],
  },
  {
    key: 'catalog',
    label: 'Catalog',
    title: 'Make sure your stock catalog is ready',
    description: 'The sold name from the POS must point to an inventory item. Create stock items first when the export contains something new.',
    icon: <ListChecks className="h-10 w-10 text-emerald-300" />,
    bullets: [
      'Use one inventory item per tracked stock unit, such as cookies or cups.',
      'Choose the store location when the item is store-specific.',
      'Set unit cost if you want dollar-valued variance on audits.',
    ],
    action: 'mappings',
    actionLabel: 'Open mappings',
  },
  {
    key: 'mapping',
    label: 'Mappings',
    title: 'Map every sold name to stock units',
    description: 'Mappings are remembered across imports. Direct mappings support pack conversion now; recipe mappings can be added later without changing the export format.',
    icon: <Map className="h-10 w-10 text-emerald-300" />,
    bullets: [
      'Cookie 6-pack → cookies at 6 stock units per sale.',
      'Ignore non-stock lines once so they are never asked again.',
      'Review fuzzy suggestions before they affect inventory.',
    ],
    action: 'mappings',
    actionLabel: 'Manage mappings',
  },
  {
    key: 'import',
    label: 'Import',
    title: 'Upload, review, then commit',
    description: 'Parsing never changes inventory. Review each line, map or ignore it, and commit only when the depletion looks right.',
    icon: <Upload className="h-10 w-10 text-emerald-300" />,
    bullets: [
      'CSV is deterministic; PDF and image exports are best-effort.',
      'Negative quantities are preserved for refunds and returns.',
      'A duplicate business date shows a warning before any second import.',
    ],
    action: 'import',
    actionLabel: 'Import a sales file',
  },
  {
    key: 'audit',
    label: 'Audit',
    title: 'Close the loop with a physical count',
    description: 'After sales are committed, Expected is the theoretical on-hand and Variance is counted minus expected. Save a count to establish the next baseline.',
    icon: <ClipboardCheck className="h-10 w-10 text-emerald-300" />,
    bullets: [
      'Negative variance means fewer units than the ledger expects.',
      'Unit cost adds dollar impact to each line and the report summary.',
      'The item detail view explains received, sold, used, and stockouts since baseline.',
    ],
    action: 'audit',
    actionLabel: 'Open audit sheet',
  },
  {
    key: 'mailbox',
    label: 'Mailbox',
    title: 'Automate nightly exports when ready',
    description: 'A platform-managed Gmail intake can poll registered POS senders. This is optional and disabled until an administrator configures the mailbox and scheduler.',
    icon: <Inbox className="h-10 w-10 text-emerald-300" />,
    bullets: [
      'Register one sender to one company and optional store location.',
      'Fully mapped files can commit automatically with Gmail provenance.',
      'Unmapped files become drafts for review; unknown senders stay unread.',
    ],
  },
]

function readSeen(companyKey: string): boolean {
  const key = `${SALES_INTAKE_WIZARD_STORAGE_KEY}:${companyKey}`
  try {
    return localStorage.getItem(key) === '1' || sessionStorage.getItem(key) === '1'
  } catch {
    return false
  }
}

function markSeen(companyKey: string) {
  const key = `${SALES_INTAKE_WIZARD_STORAGE_KEY}:${companyKey}`
  try { localStorage.setItem(key, '1') } catch { /* storage may be blocked */ }
  try { sessionStorage.setItem(key, '1') } catch { /* storage may be blocked */ }
}

export default function SalesIntakeWizard({ open, companyKey, onClose, onAction }: Props) {
  const [step, setStep] = useState(0)
  const [autoOpen, setAutoOpen] = useState(false)
  const steps = useMemo<WizardStep[]>(
    () => GUIDE_STEPS.map(({ key, label }) => ({ key, label })),
    [],
  )
  const current = GUIDE_STEPS[step]

  useEffect(() => {
    if (!readSeen(companyKey)) {
      setAutoOpen(true)
      markSeen(companyKey)
    }
  }, [companyKey])

  const visible = open || autoOpen

  function close() {
    setAutoOpen(false)
    onClose()
  }

  function handleAction(action: Action) {
    close()
    onAction(action)
  }

  return (
    <Modal open={visible} onClose={close} bare>
      <div className="w-full max-w-2xl overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-950 shadow-2xl">
        <div className="flex items-center justify-between border-b border-zinc-800 px-6 py-4">
          <div className="flex items-center gap-2 text-sm font-medium text-zinc-100">
            <BookOpen className="h-4 w-4 text-emerald-300" />
            Sales intake guide
          </div>
          <button type="button" onClick={close} className="rounded-lg p-1.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200" aria-label="Close guide">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="border-b border-zinc-800 px-6 py-4">
          <WizardStepper steps={steps} activeIndex={step} />
        </div>

        <div className="grid gap-6 px-6 py-7 sm:grid-cols-[auto_1fr] sm:items-start">
          <div className="flex h-20 w-20 items-center justify-center rounded-2xl border border-emerald-500/20 bg-emerald-500/[0.08]">
            {current.icon}
          </div>
          <div className="min-w-0">
            <p className="text-xs font-medium uppercase tracking-[0.16em] text-emerald-300">Step {step + 1} of {GUIDE_STEPS.length}</p>
            <h2 className="mt-1 text-xl font-semibold text-zinc-100">{current.title}</h2>
            <p className="mt-2 text-sm leading-6 text-zinc-400">{current.description}</p>
            <ul className="mt-4 space-y-2 text-sm text-zinc-300">
              {current.bullets.map((bullet) => (
                <li key={bullet} className="flex gap-2">
                  <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
                  <span>{bullet}</span>
                </li>
              ))}
            </ul>
            {current.action && current.actionLabel && (
              <Button variant="secondary" className="mt-5" onClick={() => handleAction(current.action!)}>
                {current.action === 'mappings' && <Map className="mr-1.5 inline h-3.5 w-3.5" />}
                {current.action === 'import' && <Upload className="mr-1.5 inline h-3.5 w-3.5" />}
                {current.action === 'audit' && <ClipboardCheck className="mr-1.5 inline h-3.5 w-3.5" />}
                {current.actionLabel}
              </Button>
            )}
          </div>
        </div>

        <div className="flex items-center justify-between border-t border-zinc-800 px-6 py-4">
          <button type="button" onClick={close} className="text-sm text-zinc-500 hover:text-zinc-300">Skip guide</button>
          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={() => setStep((value) => Math.max(0, value - 1))} disabled={step === 0}>
              <ArrowLeft className="mr-1.5 inline h-3.5 w-3.5" /> Back
            </Button>
            {step < GUIDE_STEPS.length - 1 ? (
              <Button onClick={() => setStep((value) => value + 1)}>
                Next <ArrowRight className="ml-1.5 inline h-3.5 w-3.5" />
              </Button>
            ) : (
              <Button onClick={close}>Finish guide</Button>
            )}
          </div>
        </div>
      </div>
    </Modal>
  )
}
