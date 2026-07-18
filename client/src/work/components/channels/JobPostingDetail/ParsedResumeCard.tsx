import type { ParsedResume } from '../../../../api/profileResume'

export function ParsedResumeCard({ data }: { data: ParsedResume }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3 space-y-2">
      {data.name && (
        <div className="flex items-baseline gap-2">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500 w-16 shrink-0">Name</span>
          <span className="text-xs text-zinc-200">{data.name}</span>
        </div>
      )}
      {data.current_title && (
        <div className="flex items-baseline gap-2">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500 w-16 shrink-0">Title</span>
          <span className="text-xs text-zinc-200">
            {data.current_title}
            {typeof data.experience_years === 'number' && ` · ${data.experience_years} yrs`}
          </span>
        </div>
      )}
      {data.location && (
        <div className="flex items-baseline gap-2">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500 w-16 shrink-0">Location</span>
          <span className="text-xs text-zinc-200">{data.location}</span>
        </div>
      )}
      {data.skills && data.skills.length > 0 && (
        <div className="flex items-start gap-2">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500 w-16 shrink-0 mt-0.5">Skills</span>
          <div className="flex flex-wrap gap-1">
            {data.skills.slice(0, 14).map((s) => (
              <span
                key={s}
                className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 border border-zinc-700 text-zinc-300"
              >
                {s}
              </span>
            ))}
          </div>
        </div>
      )}
      {data.summary && (
        <div className="flex items-start gap-2">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500 w-16 shrink-0 mt-0.5">Summary</span>
          <span className="text-[11px] text-zinc-400 leading-relaxed">{data.summary}</span>
        </div>
      )}
      {data.strengths && data.strengths.length > 0 && (
        <div className="flex items-start gap-2">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500 w-16 shrink-0 mt-0.5">Strengths</span>
          <span className="text-[11px] text-zinc-400">{data.strengths.join(', ')}</span>
        </div>
      )}
    </div>
  )
}
