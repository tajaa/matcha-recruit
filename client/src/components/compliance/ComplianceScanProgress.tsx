import type { ComplianceCheckMessage } from '../../hooks/compliance/useComplianceCheck'

type Props = { scanning: boolean; messages: ComplianceCheckMessage[] }

export function ComplianceScanProgress({ scanning, messages }: Props) {
  if (!scanning && messages.length === 0) return null

  const missingCategories = messages
    .filter((m) => m.missing_categories?.length)
    .flatMap((m) => m.missing_categories ?? [])
  const uniqueMissing = [...new Set(missingCategories)]

  return (
    <div className="border border-zinc-800 rounded-lg px-3 py-2.5 mb-3 space-y-2">
      <div className="max-h-28 overflow-y-auto space-y-0.5">
        {messages.filter((m) => m.message).map((msg, i) => (
          <p key={i} className="text-xs text-zinc-500 leading-5">{msg.message}</p>
        ))}
      </div>
      {scanning && <p className="text-xs text-zinc-400 animate-pulse">Scanning...</p>}
      {!scanning && uniqueMissing.length > 0 && (
        <div className="border border-amber-800/40 bg-amber-900/10 rounded px-3 py-2">
          <p className="text-[11px] text-amber-400">Missing coverage: {uniqueMissing.join(', ')}</p>
        </div>
      )}
    </div>
  )
}
