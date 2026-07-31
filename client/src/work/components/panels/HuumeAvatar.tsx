import { HuumeMark } from '../HuumeMark'

/** Small mark identifying a Huume-authored reply — distinguishes it from a
 * plain assistant bubble in the transcript. Presentational only; callers
 * decide when to show it (message-level via `metadata.huume_run_id`, or
 * thread-level while streaming, before a message exists to carry that). */
export default function HuumeAvatar({ size = 'sm', lightMode }: { size?: 'sm' | 'md'; lightMode?: boolean }) {
  const dims = size === 'md' ? 'h-8 w-8' : 'h-6 w-6'
  const glyph = size === 'md' ? 'w-4.5 h-4.5' : 'w-3.5 h-3.5'
  return (
    <div
      className={`shrink-0 flex items-center justify-center rounded-md ${dims} ${
        lightMode
          ? 'bg-orange-100 text-orange-700 border border-orange-300'
          : 'bg-orange-950/50 text-orange-300 border border-orange-800/60'
      }`}
      title="Huume"
    >
      <HuumeMark className={glyph} />
    </div>
  )
}
