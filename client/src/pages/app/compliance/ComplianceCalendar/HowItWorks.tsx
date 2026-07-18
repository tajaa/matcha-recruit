import { useState } from 'react'
import { Info } from 'lucide-react'

export function HowItWorks() {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button
        onClick={() => setOpen((v) => !v)}
        className="text-zinc-500 hover:text-zinc-300 p-1 rounded hover:bg-zinc-800"
        title="How this works"
      >
        <Info size={14} />
      </button>
      {open && (
        <div className="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4" onClick={() => setOpen(false)}>
          <div
            className="bg-zinc-900 border border-zinc-700 rounded-xl max-w-md w-full p-5 space-y-4 text-sm text-zinc-300"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-zinc-100">How the calendar works</h3>
              <button onClick={() => setOpen(false)} className="text-zinc-500 hover:text-zinc-300">×</button>
            </div>
            <div className="space-y-3 text-xs leading-relaxed text-zinc-400">
              <div>
                <p className="text-zinc-300 font-medium mb-1">Where deadlines come from</p>
                <span className="text-emerald-400">Baseline</span> rows are the
                broad-strokes federal + California annual deadlines every
                employer is expected to know — W-2, OSHA 300A, ACA, EEO-1, Form
                5500, CA DE 9 quarters, IIPP, harassment training. They appear
                automatically based on your headcount and locations. The other
                rows come from compliance alerts generated when you run a check
                on a location (Locations → Run check) — those add jurisdiction-
                specific rule changes on top of the baseline.
              </div>
              <div>
                <p className="text-zinc-300 font-medium mb-1">Status buckets</p>
                <ul className="space-y-1 list-disc list-inside">
                  <li><span className="text-red-400">Overdue</span> — past their deadline</li>
                  <li><span className="text-amber-400">Due in 30 days</span> — schedule action this month</li>
                  <li><span className="text-zinc-300">Due in 90 days</span> — plan ahead</li>
                  <li><span className="text-emerald-400">Future</span> — awareness only</li>
                </ul>
              </div>
              <div>
                <p className="text-zinc-300 font-medium mb-1">Per-row actions</p>
                <span className="text-zinc-300">Click a row</span> to mark it
                read. <span className="text-zinc-300">View</span> opens the
                full alert detail. <span className="text-zinc-300">Dismiss</span> removes
                it from the calendar (use this for false-positives or things
                you've already handled outside the system).
              </div>
              <div>
                <p className="text-zinc-300 font-medium mb-1">Filters</p>
                Location and category filters persist in the URL — bookmark a
                filtered view if you only care about, say, California payroll
                deadlines.
              </div>
              <div>
                <p className="text-zinc-300 font-medium mb-1">Coming soon</p>
                Email reminders 7 days before each deadline + iCal export.
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
