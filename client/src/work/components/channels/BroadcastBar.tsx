import { useEffect, useRef, useState } from 'react'
import { Camera, CameraOff, Mic, MicOff, Radio, Square, X } from 'lucide-react'
import type { ChannelMember } from '../../api/channels'
import type { useLiveKitBroadcast } from '../../hooks/useLiveKitBroadcast'

type Broadcast = ReturnType<typeof useLiveKitBroadcast>

function BroadcastTile({ stream, label, muted }: { stream: MediaStream | null; label: string; muted?: boolean }) {
  const ref = useRef<HTMLVideoElement>(null)
  const [hasVideo, setHasVideo] = useState(false)
  useEffect(() => {
    const element = ref.current
    if (element) element.srcObject = stream
    const tracks = stream?.getVideoTracks() ?? []
    const update = () => setHasVideo(tracks.some((track) => track.enabled && !track.muted))
    update()
    for (const track of tracks) {
      track.addEventListener('mute', update)
      track.addEventListener('unmute', update)
      track.addEventListener('ended', update)
    }
    return () => {
      for (const track of tracks) {
        track.removeEventListener('mute', update)
        track.removeEventListener('unmute', update)
        track.removeEventListener('ended', update)
      }
      if (element) element.srcObject = null
    }
  }, [stream])
  return <div className="relative aspect-video overflow-hidden rounded-lg bg-zinc-800">
    <video ref={ref} autoPlay playsInline muted={muted} className={`h-full w-full object-cover ${hasVideo ? '' : 'invisible'}`} />
    {!hasVideo && <span className="absolute inset-0 flex items-center justify-center text-2xl text-zinc-400">{label.charAt(0).toUpperCase()}</span>}
    <span className="absolute bottom-1 left-1 rounded bg-black/70 px-1.5 text-xs text-white">{label}</span>
  </div>
}

export default function BroadcastBar({ broadcast, members, isOwner, canGoLive, callActive, onUpgrade, onClose }: {
  broadcast: Broadcast
  members: ChannelMember[]
  isOwner: boolean
  canGoLive: boolean
  callActive: boolean
  onUpgrade: () => void
  onClose: () => void
}) {
  const [title, setTitle] = useState('')
  const status = broadcast.status
  const active = status?.active ?? false
  const publisherIds = new Set(status?.publisher_user_ids ?? [])
  return <section className="shrink-0 border-b border-w-line bg-w-surface px-4 py-3 text-sm text-w-text" aria-label="Broadcast">
    <div className="mb-2 flex items-center gap-2">
      <Radio size={16} className={active ? 'text-red-400' : 'text-w-dim'} />
      <strong>{active ? (status?.title || 'Live broadcast') : 'Go Live'}</strong>
      {active && <span className="rounded bg-red-500/20 px-1.5 text-[10px] font-bold text-red-300">LIVE</span>}
      <span className="ml-auto text-xs text-w-dim">{status ? `${status.weekly_remaining} of ${status.weekly_limit} starts remaining` : 'Loading…'}</span>
      <button onClick={onClose} aria-label="Close broadcast panel" className="text-w-dim hover:text-w-text"><X size={16} /></button>
    </div>
    {broadcast.error && <p role="alert" className="mb-2 text-xs text-red-400">{broadcast.error}</p>}
    {!active && isOwner && <div className="flex flex-wrap items-center gap-2">
      <input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={120} placeholder="Broadcast title (optional)" className="min-w-40 flex-1 rounded border border-w-line bg-w-bg px-2 py-1.5 text-xs" />
      {canGoLive ? <button onClick={() => void broadcast.start(title)} disabled={!status || callActive || status.weekly_remaining <= 0} className="rounded bg-w-accent px-3 py-1.5 text-xs font-semibold text-black disabled:opacity-40">Go Live</button>
        : <button onClick={onUpgrade} disabled={callActive} className="rounded bg-w-accent px-3 py-1.5 text-xs font-semibold text-black disabled:opacity-40">Get Pro to go live</button>}
      {callActive && <span className="text-xs text-w-dim">End the voice call first.</span>}
    </div>}
    {!active && !isOwner && <p className="text-xs text-w-dim">The channel owner can start a broadcast. Watching is free.</p>}
    {active && <>
      <div className="flex flex-wrap items-center gap-2">
        {broadcast.connectionState === 'idle' ? <button onClick={() => void broadcast.watch()} className="rounded bg-w-accent px-3 py-1.5 text-xs font-semibold text-black">Watch live</button>
          : broadcast.connectionState === 'connecting' ? <span className="text-xs text-w-dim">Connecting…</span>
            : <button onClick={broadcast.leave} className="rounded border border-w-line px-3 py-1.5 text-xs">Leave broadcast</button>}
        {isOwner && <button onClick={() => void broadcast.stop()} className="ml-auto flex items-center gap-1 rounded bg-red-600/20 px-2 py-1.5 text-xs text-red-300"><Square size={12} /> End broadcast</button>}
      </div>
      {broadcast.connectionState === 'connected' && <>
        <div className="mt-3 grid max-h-[45vh] grid-cols-2 gap-2 overflow-y-auto sm:grid-cols-3">
          {broadcast.participants.map((person) => <BroadcastTile key={person.userId} stream={person.stream} label={person.name} />)}
          {broadcast.isPublishing && <BroadcastTile stream={broadcast.localStream} label="You" muted />}
        </div>
        {broadcast.isPublishing && <div className="mt-2 flex gap-2">
          <button onClick={() => void broadcast.toggleMute()} className="rounded border border-w-line p-1.5" aria-label={broadcast.isMuted ? 'Unmute' : 'Mute'}>{broadcast.isMuted ? <MicOff size={15} /> : <Mic size={15} />}</button>
          <button onClick={() => void broadcast.toggleVideo()} className="rounded border border-w-line p-1.5" aria-label={broadcast.isVideoEnabled ? 'Turn off camera' : 'Turn on camera'}>{broadcast.isVideoEnabled ? <Camera size={15} /> : <CameraOff size={15} />}</button>
        </div>}
      </>}
      {isOwner && <div className="mt-3 border-t border-w-line pt-2">
        <p className="mb-1 text-xs font-medium text-w-dim">Publishers</p>
        <div className="flex flex-wrap gap-1.5">{members.filter((member) => member.channel_role !== 'owner' && broadcast.participants.some((person) => person.userId === member.user_id)).map((member) => {
          const publishing = publisherIds.has(member.user_id)
          return <button key={member.user_id} onClick={() => void broadcast.setPublisher(member.user_id, !publishing)} className="rounded border border-w-line px-2 py-1 text-xs" aria-label={`${publishing ? 'Demote' : 'Promote'} ${member.name}`}>
            {member.name} · {publishing ? 'On stage' : 'Invite to stage'}
          </button>
        })}{!broadcast.participants.length && <span className="text-xs text-w-dim">Viewers can join the stage once they are watching.</span>}</div>
      </div>}
    </>}
  </section>
}
