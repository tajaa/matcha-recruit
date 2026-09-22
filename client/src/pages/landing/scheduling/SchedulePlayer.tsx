import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Player, type PlayerRef } from '@remotion/player'
import { Pause, Play } from 'lucide-react'
import { WeekComposition } from './WeekComposition'
import { DURATION, FPS, LAYOUTS, STILL_FRAME, type Variant } from './timeline'
import { INK, PAPER } from './theme'

function useMedia(query: string): boolean {
  const [matches, setMatches] = useState(() => typeof window !== 'undefined' && window.matchMedia(query).matches)
  useEffect(() => {
    const mql = window.matchMedia(query)
    const onChange = () => setMatches(mql.matches)
    onChange()
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [query])
  return matches
}

/**
 * The hero animation. Pauses itself offscreen, honours reduced motion by
 * showing the finished week as a still, and exposes a pause control (it moves
 * for longer than five seconds, so WCAG 2.2.2 wants one).
 */
export default function SchedulePlayer({ caption }: { caption: ReactNode }) {
  const narrow = useMedia('(max-width: 640px)')
  const reduced = useMedia('(prefers-reduced-motion: reduce)')
  const variant: Variant = narrow ? 'narrow' : 'wide'
  const L = LAYOUTS[variant]
  const playerRef = useRef<PlayerRef>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const [userPaused, setUserPaused] = useState(false)
  const [playing, setPlaying] = useState(false)

  useEffect(() => {
    const player = playerRef.current
    if (!player) return
    const onPlay = () => setPlaying(true)
    const onPause = () => setPlaying(false)
    player.addEventListener('play', onPlay)
    player.addEventListener('pause', onPause)
    return () => {
      player.removeEventListener('play', onPlay)
      player.removeEventListener('pause', onPause)
    }
  }, [variant])

  useEffect(() => {
    const el = wrapRef.current
    const player = playerRef.current
    if (!el || !player) return
    if (reduced) {
      player.pause()
      player.seekTo(STILL_FRAME)
      return
    }
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !userPaused) player.play()
        else player.pause()
      },
      { threshold: 0.25 },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [reduced, userPaused, variant])

  const toggle = () => {
    const player = playerRef.current
    if (!player) return
    if (player.isPlaying()) {
      player.pause()
      setUserPaused(true)
    } else {
      player.play()
      setUserPaused(false)
    }
  }

  return (
    <div ref={wrapRef}>
      <div className="sched-sheet overflow-hidden rounded-[6px]" style={{ border: `1.5px solid ${INK}` }}>
        <div
          role="img"
          aria-label="Animated example: a week's schedule for a café drafts itself from the sales forecast, flags a 44-hour week and a 7-hour close-to-open turnaround, moves both shifts to crew with room, and is published."
        >
          <Player
            key={variant}
            ref={playerRef}
            component={WeekComposition}
            inputProps={{ variant }}
            durationInFrames={DURATION}
            fps={FPS}
            compositionWidth={L.w}
            compositionHeight={L.h}
            style={{ width: '100%', display: 'block' }}
            initialFrame={reduced ? STILL_FRAME : 0}
            loop
            controls={false}
            clickToPlay={false}
            doubleClickToFullscreen={false}
            numberOfSharedAudioTags={0}
            // Silent composition. Unmuted, the playback loop waits for the
            // shared AudioContext to resume, which browsers refuse without a
            // user gesture — play() started by the IntersectionObserver then
            // sits on frame 0 forever.
            initiallyMuted
          />
        </div>
      </div>
      <div className="mt-4 flex items-start gap-4">
        {!reduced && (
          <button
            type="button"
            onClick={toggle}
            aria-label={playing ? 'Pause animation' : 'Play animation'}
            className="sched-focus inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-opacity hover:opacity-80"
            style={{ backgroundColor: INK, color: PAPER }}
          >
            {playing ? <Pause size={14} /> : <Play size={14} />}
          </button>
        )}
        <div className="min-w-0 flex-1">{caption}</div>
      </div>
    </div>
  )
}
