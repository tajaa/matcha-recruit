import { Info } from 'lucide-react'
import { useState } from 'react'

export function InfoTip({ text }: { text: string }) {
  const [show, setShow] = useState(false)

  return (
    <span
      className="relative inline-flex ml-1 cursor-help"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      <Info size={11} className="text-zinc-600 hover:text-zinc-400 transition-colors" />
      {show && (
        <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 px-3 py-2 text-[11px] leading-relaxed text-zinc-300 bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl z-50 pointer-events-none">
          {text}
          <span className="absolute top-full left-1/2 -translate-x-1/2 -mt-px border-4 border-transparent border-t-zinc-700" />
        </span>
      )}
    </span>
  )
}
