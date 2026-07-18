export function ColorField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="flex items-center gap-3">
      <input
        type="color"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-8 w-10 shrink-0 rounded border border-white/10 bg-transparent cursor-pointer p-0"
      />
      <span className="flex-1 text-[11px] text-zinc-400">{label}</span>
      <span className="text-[11px] font-mono text-zinc-500 uppercase">{value}</span>
    </label>
  )
}
