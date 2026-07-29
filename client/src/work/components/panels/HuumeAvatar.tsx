/** Small ASCII-style "face" marking a Huume-authored reply — distinguishes
 * it from a plain assistant bubble in the transcript. Presentational only;
 * callers decide when to show it (message-level via `metadata.huume_run_id`,
 * or thread-level while streaming, before a message exists to carry that). */
export default function HuumeAvatar({ size = 'sm', lightMode }: { size?: 'sm' | 'md'; lightMode?: boolean }) {
  const dims = size === 'md' ? 'h-8 text-[11px] px-1.5' : 'h-6 text-[9px] px-1'
  return (
    <div
      className={`shrink-0 flex items-center justify-center whitespace-nowrap leading-none rounded-md font-mono font-medium ${dims} ${
        lightMode
          ? 'bg-orange-100 text-orange-700 border border-orange-300'
          : 'bg-orange-950/50 text-orange-300 border border-orange-800/60'
      }`}
      title="Huume"
    >
      [·ᴗ·]
    </div>
  )
}
