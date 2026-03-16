import { useState } from 'react'

type Props = { names?: string[] | null; count: number; children: React.ReactNode }

export function EmployeesTooltip({ names, count, children }: Props) {
  const [show, setShow] = useState(false)
  if (!names?.length) return <>{children}</>
  return (
    <span className="relative" onMouseEnter={() => setShow(true)} onMouseLeave={() => setShow(false)}>
      {children}
      {show && (
        <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50 pointer-events-none">
          <span className="flex flex-col gap-0.5 bg-zinc-800 border border-zinc-700 rounded px-2.5 py-2 shadow-xl min-w-[120px]">
            {names.map((n, i) => (
              <span key={i} className="text-[10px] text-zinc-200 font-medium whitespace-nowrap">{n}</span>
            ))}
            {count > names.length && (
              <span className="text-[9px] text-zinc-500 font-mono mt-0.5">+{count - names.length} more</span>
            )}
          </span>
        </span>
      )}
    </span>
  )
}
