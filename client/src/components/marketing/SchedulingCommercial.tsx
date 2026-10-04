import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Play, Pause, Volume2, VolumeX, ArrowRight, RotateCcw } from 'lucide-react'
import { landingMedia } from '../../api/admin/landingMedia'
import type { SchedulingCommercial as CommercialSettings } from '../../types/landingMedia'
import { useMedia, useReducedMotion } from './kit/hooks'
import { mono } from './kit/styles'
import { BOARD, PAPER, hexA } from './kit/theme'

export function SchedulingCommercial({ enabled, fallback }: { enabled: boolean; fallback: ReactNode }) {
  const [settings, setSettings] = useState<CommercialSettings | null>(null)
  useEffect(() => {
    if (!enabled) return
    const controller = new AbortController()
    landingMedia.getPublic(controller.signal).then((data) => {
      const commercial = data.scheduling_commercial
      if (commercial?.enabled && commercial.desktop_video_url) setSettings(commercial)
    }).catch(() => { /* Media is optional; the landing page remains usable. */ })
    return () => controller.abort()
  }, [enabled])
  return enabled && settings ? <CommercialPlayer settings={settings} fallback={fallback} /> : fallback
}

export function CommercialPlayer({ settings, fallback }: { settings: CommercialSettings; fallback: ReactNode }) {
  const narrow = useMedia('(max-width: 767px)')
  const reduced = useReducedMotion()
  const video = useRef<HTMLVideoElement>(null)
  const container = useRef<HTMLDivElement>(null)
  // Set only by the visitor's own pause click, so scrolling away and back never overrides it.
  const userPaused = useRef(false)
  const [skipped, setSkipped] = useState(false)
  const [failed, setFailed] = useState(false)
  const [watching, setWatching] = useState(false)
  const [ended, setEnded] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [muted, setMuted] = useState(true)
  // Saved before the option existed (or missing) means sound stays on, as it always was.
  const soundOn = settings.sound_enabled !== false
  const source = narrow && settings.mobile_video_url ? settings.mobile_video_url : settings.desktop_video_url
  const poster = narrow && settings.mobile_video_url ? settings.mobile_poster_url ?? undefined : settings.desktop_poster_url ?? undefined
  const vertical = narrow && Boolean(settings.mobile_video_url)

  useEffect(() => {
    const element = video.current
    const wrapper = container.current
    if (!element || !wrapper || skipped || failed) return
    const connection = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection
    if (typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) element.pause()
      else if (!reduced && !connection?.saveData && !watching && !ended && !userPaused.current) void element.play().catch(() => { /* Play remains available if autoplay is blocked. */ })
    }, { threshold: 0.25 })
    observer.observe(wrapper)
    return () => observer.disconnect()
  }, [source, reduced, watching, ended, skipped, failed])

  // Start over with sound (sound mode only). A click is the user gesture browsers require to unmute.
  function watch() {
    const element = video.current
    if (!element) return
    element.muted = false
    element.currentTime = 0
    userPaused.current = false
    setMuted(false)
    setWatching(true)
    setEnded(false)
    void element.play().catch(() => setWatching(false))
  }
  function toggleSound() {
    const element = video.current
    if (!element) return
    element.muted = !element.muted
    setMuted(element.muted)
  }
  // Silent mode: play / pause / replay, never any sound.
  function togglePlay() {
    const element = video.current
    if (!element) return
    if (playing) {
      userPaused.current = true
      element.pause()
      return
    }
    userPaused.current = false
    if (ended) { element.currentTime = 0; setEnded(false) }
    void element.play().catch(() => { /* Stays paused; the Play button remains. */ })
  }
  function skip() {
    video.current?.pause()
    setSkipped(true)
  }
  function resume() {
    userPaused.current = false
    setSkipped(false); setWatching(false); setEnded(false); setPlaying(false); setMuted(true)
  }

  if (failed || !source) return fallback
  if (skipped) return <><div className="mb-5 flex justify-end"><button type="button" onClick={resume} className="sched-link sched-focus inline-flex items-center gap-2 rounded text-sm"><RotateCcw size={14} aria-hidden />Watch the film</button></div>{fallback}</>
  const soundHeard = soundOn && watching && !muted
  return (
    <div ref={container}>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-4" style={mono('10px', { color: hexA(PAPER, 0.65) })}>
        <span>Matcha · the film</span><button type="button" onClick={skip} className="sched-link sched-focus inline-flex min-h-11 items-center gap-2 rounded" style={{ color: PAPER }}>Skip film<ArrowRight size={13} aria-hidden /></button>
      </div>
      <div className="relative mx-auto overflow-hidden bg-black" style={{ aspectRatio: vertical ? '9 / 16' : '16 / 9', maxWidth: vertical ? 'min(100%, 380px)' : undefined }}>
        <video key={source} ref={video} src={source} poster={poster} muted={!soundOn || muted} playsInline controls={soundOn && (watching || ended)} preload={reduced ? 'none' : 'metadata'} crossOrigin={settings.captions_url ? 'anonymous' : undefined} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => { setEnded(true); setPlaying(false) }} onVolumeChange={(event) => { if (soundOn && watching) setMuted(event.currentTarget.muted) }} onError={() => setFailed(true)} className="h-full w-full object-contain" aria-label="Matcha scheduling commercial">
          {settings.captions_url && <track kind="captions" src={settings.captions_url} srcLang="en" label="English" default />}
        </video>
        {soundOn && !watching && <div className="pointer-events-none absolute inset-0 flex items-center justify-center" style={{ background: 'linear-gradient(transparent 50%, rgba(0,0,0,.35))' }}><button type="button" onClick={watch} className="pointer-events-auto sched-btn sched-btn-paper sched-focus inline-flex min-h-14 items-center gap-3 rounded-full px-7 text-sm font-medium"><Play size={17} fill="currentColor" aria-hidden />Watch with sound</button></div>}
        {!soundOn && !playing && <div className="pointer-events-none absolute inset-0 flex items-center justify-center" style={{ background: 'linear-gradient(transparent 50%, rgba(0,0,0,.35))' }}><button type="button" onClick={togglePlay} className="pointer-events-auto sched-btn sched-btn-paper sched-focus inline-flex min-h-14 items-center gap-3 rounded-full px-7 text-sm font-medium">{ended ? <RotateCcw size={17} aria-hidden /> : <Play size={17} fill="currentColor" aria-hidden />}{ended ? 'Watch again' : 'Play film'}</button></div>}
      </div>
      <div className="mt-5 flex flex-wrap items-center justify-between gap-4 text-sm" style={{ color: hexA(PAPER, 0.7) }}>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-1">
          {soundOn ? <>
            <button type="button" onClick={watch} className="sched-link sched-focus inline-flex min-h-11 items-center gap-2 rounded">{ended ? <RotateCcw size={14} aria-hidden /> : <Volume2 size={14} aria-hidden />}{ended ? 'Watch again' : watching ? 'Restart the film' : 'Watch with sound'}</button>
            {watching && !ended && <button type="button" onClick={toggleSound} className="sched-link sched-focus inline-flex min-h-11 items-center gap-2 rounded">{soundHeard ? <VolumeX size={14} aria-hidden /> : <Volume2 size={14} aria-hidden />}{soundHeard ? 'Sound off' : 'Sound on'}</button>}
          </> : (
            <button type="button" onClick={togglePlay} className="sched-link sched-focus inline-flex min-h-11 items-center gap-2 rounded">{playing ? <Pause size={14} aria-hidden /> : ended ? <RotateCcw size={14} aria-hidden /> : <Play size={14} aria-hidden />}{playing ? 'Pause film' : ended ? 'Watch again' : 'Play film'}</button>
          )}
        </div>
        <button type="button" onClick={skip} className="group sched-link sched-focus inline-flex min-h-11 items-center gap-2 rounded" style={{ color: BOARD.STAMP }}>Skip to the schedule<ArrowRight size={15} className="transition-transform group-hover:translate-x-1" aria-hidden /></button>
      </div>
    </div>
  )
}
