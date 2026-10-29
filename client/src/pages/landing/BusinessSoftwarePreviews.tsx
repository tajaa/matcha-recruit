import { ArrowRight, Check, FileText } from 'lucide-react'
import { mono } from '../../components/marketing/kit/styles'
import { BOARD, INK, PAPER, STAMP, hexA } from '../../components/marketing/kit/theme'

/** Small, static product illustrations; the full workflows live on their product pages. */
export function SchedulingPreview() {
  return (
    <div aria-hidden className="min-h-[244px] overflow-hidden border p-5 sm:p-6" style={{ backgroundColor: BOARD.PAPER, color: PAPER, borderColor: hexA(INK, 0.12) }}>
      <div className="flex items-center justify-between gap-3"><span className="text-sm font-medium">The week, in view.</span><span style={mono('9px', { color: BOARD.INK_SOFT })}>Illustrative schedule</span></div>
      <div className="mt-5 grid grid-cols-[42px_repeat(3,minmax(0,1fr))] gap-1.5 text-[11px]">
        <span />{['Mon', 'Tue', 'Wed'].map(day => <span key={day} className="pb-2 text-center" style={{ color: BOARD.INK_SOFT }}>{day}</span>)}
        {['Open', 'Close'].map((shift, row) => <div key={shift} className="contents"><span className="self-center" style={{ color: BOARD.INK_SOFT }}>{shift}</span>{[0, 1, 2].map(day => <span key={day} className="border-l-2 px-2 py-3 sm:px-3" style={{ backgroundColor: hexA(BOARD.STAMP, row ? 0.08 : 0.16), borderColor: row ? hexA(BOARD.STAMP, 0.4) : BOARD.STAMP }}>{row ? '2–8 pm' : '8 am–2 pm'}</span>)}</div>)}
      </div>
      <div className="mt-5 flex items-center gap-2 text-[11px]" style={{ color: BOARD.STAMP }}><Check size={13} />Draft. Check. Publish.<ArrowRight size={13} className="ml-auto" /></div>
    </div>
  )
}

export function IncidentsPreview() {
  return (
    <div aria-hidden className="min-h-[244px] overflow-hidden border p-5 sm:p-6" style={{ backgroundColor: BOARD.PAPER, color: PAPER, borderColor: hexA(INK, 0.12) }}>
      <div className="flex items-center justify-between gap-3"><span className="text-sm font-medium">Every step, documented.</span><span style={mono('9px', { color: BOARD.INK_SOFT })}>Illustrative case</span></div>
      <div className="mt-5 flex items-center gap-4 border p-4" style={{ backgroundColor: PAPER, color: INK, borderColor: hexA(PAPER, 0.15) }}>
        <FileText size={28} strokeWidth={1.2} style={{ color: STAMP }} /><div><div className="text-sm font-medium">A report. A clear next step.</div><div className="mt-1 text-[11px] opacity-65">Your handbook. Your review process.</div></div>
      </div>
      <div className="mt-5 flex items-center justify-between gap-2 text-[11px]">
        {['Report', 'Review', 'Signed copy'].map((step, i) => <div key={step} className="flex items-center gap-2"><span className="h-1 w-1 rounded-full" style={{ backgroundColor: BOARD.STAMP }} />{step}{i < 2 && <ArrowRight size={12} className="ml-1" style={{ color: BOARD.INK_SOFT }} />}</div>)}
      </div>
      <div className="mt-4 text-[11px]" style={{ color: BOARD.STAMP }}>People make every decision.</div>
    </div>
  )
}
