import { useEffect, useRef, useState } from 'react'
import { Player, type PlayerRef } from '@remotion/player'
import { Pause, Play } from 'lucide-react'
import { useReducedMotion } from './hooks'
import type { StageProps } from './Stage'
import { Poster, StageLayout } from './StageFrame'
import { INK, PAPER } from './theme'
import { FPS, type Variant } from './timeline'

/**
 * A Remotion Player that behaves like part of the page: plays only while on
 * screen, honours reduced motion with a still of the finished state, and has a
 * pause control (it moves for longer than five seconds — WCAG 2.2.2).
 */
export default function RemotionStage({
  load,
  sizes,
  variant,
  durationInFrames,
  stillFrame,
  label,
  caption,
  mediaClassName,
  mediaStyle,
  decor,
}: StageProps & { variant: Variant }) {
  const reduced = useReducedMotion()
  const size = sizes[variant]
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
      player.seekTo(stillFrame)
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
  }, [reduced, userPaused, variant, stillFrame])

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
      <StageLayout
        mediaClassName={mediaClassName}
        mediaStyle={mediaStyle}
        decor={decor}
        caption={caption}
        media={
          <div role="img" aria-label={label}>
            <Player
              key={variant}
              ref={playerRef}
              lazyComponent={load}
              inputProps={{ variant }}
              durationInFrames={durationInFrames}
              fps={FPS}
              compositionWidth={size.w}
              compositionHeight={size.h}
              style={{ width: '100%', display: 'block' }}
              initialFrame={reduced ? stillFrame : 0}
              renderLoading={() => <Poster width={size.w} height={size.h} />}
              loop
              controls={false}
              clickToPlay={false}
              doubleClickToFullscreen={false}
              numberOfSharedAudioTags={0}
              // Silent compositions. Unmuted, the playback loop waits for the
              // shared AudioContext to resume, which browsers refuse without a
              // user gesture — play() started by the IntersectionObserver then
              // sits on frame 0 forever.
              initiallyMuted
            />
          </div>
        }
        control={
          reduced ? null : (
            <button
              type="button"
              onClick={toggle}
              aria-label={playing ? 'Pause animation' : 'Play animation'}
              className="sched-focus inline-flex h-8 w-8 items-center justify-center rounded-full transition-opacity hover:opacity-80"
              style={{ backgroundColor: INK, color: PAPER }}
            >
              {playing ? <Pause size={14} /> : <Play size={14} />}
            </button>
          )
        }
      />
    </div>
  )
}
