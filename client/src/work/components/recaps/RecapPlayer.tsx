import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../../../api/client'
import { getRecapPlayback } from '../../api/matchaWork/recaps'
import type { RecapDetail, RecapPlayback } from '../../types'

export default function RecapPlayer({ recap }: { recap: RecapDetail }) {
  const video = useRef<HTMLVideoElement>(null)
  const position = useRef(0)
  const recovery = useRef(false)
  const [playback, setPlayback] = useState<RecapPlayback | null>(null)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let alive = true
    let sequence = 0
    let timer: ReturnType<typeof setTimeout> | undefined
    async function refresh() {
      clearTimeout(timer)
      if (!alive || document.hidden) return
      const request = ++sequence
      try {
        const value = await getRecapPlayback(recap.id)
        if (!alive || request !== sequence) return
        position.current = video.current?.currentTime ?? position.current
        setPlayback(value)
        setError('')
        timer = setTimeout(() => void refresh(), Math.max(1000, (value.expires_in - 45) * 1000))
      } catch (caught) {
        if (!alive || request !== sequence) return
        if (caught instanceof ApiError && [401, 403, 404, 409, 410].includes(caught.status)) {
          setPlayback(null); setError('Playback is unavailable. Reopen the recap to check access.')
        } else {
          setError('Connection interrupted. Retrying playback…')
          timer = setTimeout(() => void refresh(), 15_000)
        }
      }
    }
    const visibility = () => { ++sequence; clearTimeout(timer); if (document.hidden) video.current?.pause(); else void refresh() }
    document.addEventListener('visibilitychange', visibility)
    void refresh()
    return () => { alive = false; clearTimeout(timer); document.removeEventListener('visibilitychange', visibility) }
  }, [recap.id, revision])
  return <div>
    {playback && <video ref={video} controls playsInline preload="metadata" src={playback.video_url} poster={playback.poster_url}
      aria-label={recap.title} className="aspect-video w-full rounded-xl bg-black"
      onLoadedMetadata={() => { if (video.current) video.current.currentTime = position.current }}
      onLoadedData={() => { recovery.current = false }}
      onError={() => { if (!recovery.current) { recovery.current = true; setRevision((v) => v + 1) } else { setError('Video could not be played. Try reopening the recap.'); setPlayback(null) } }} />}
    {error && <p role="alert" className="my-3 text-sm text-amber-500">{error}</p>}
    <div aria-label="Video chapters" className="mt-3 flex flex-wrap gap-2">{recap.chapters.map((chapter) => <button key={chapter.start_ms} className="rounded border border-w-line px-2 py-1 text-xs text-w-dim" onClick={() => { if (video.current) video.current.currentTime = chapter.start_ms / 1000 }}>{chapter.label}</button>)}</div>
  </div>
}
