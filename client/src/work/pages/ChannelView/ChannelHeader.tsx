import { Hash, Users, Phone, MoreHorizontal } from 'lucide-react'
import type { ChannelDetail, ChannelPaymentInfo } from '../../api/channels'
import type { useLiveKitCall } from '../../hooks/useLiveKitCall'
import type { HeaderAction } from './types'

type OnlineUser = { id: string; name: string; avatar_url: string | null }
type VoiceCall = ReturnType<typeof useLiveKitCall>

interface ChannelHeaderProps {
  channel: ChannelDetail | null
  paymentInfo: ChannelPaymentInfo | null
  onlineUsers: OnlineUser[]
  showMembers: boolean
  setShowMembers: (v: boolean) => void
  isMember: boolean
  voice: VoiceCall
  secondaryActions: HeaderAction[]
  showMobileActions: boolean
  setShowMobileActions: React.Dispatch<React.SetStateAction<boolean>>
}

export default function ChannelHeader({
  channel,
  paymentInfo,
  onlineUsers,
  showMembers,
  setShowMembers,
  isMember,
  voice,
  secondaryActions,
  showMobileActions,
  setShowMobileActions,
}: ChannelHeaderProps) {
  return (
    <div className="flex items-center gap-3 px-4 py-3 border-b border-w-line shrink-0">
      <Hash size={18} className="text-w-accent shrink-0" />
      <div className="flex-1 min-w-0">
        <h2 className="text-white font-semibold truncate flex items-center gap-1.5">
          {channel?.name}
          {paymentInfo?.is_paid && (
            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-w-accent/15 text-w-accent">$</span>
          )}
        </h2>
        {channel?.description && (
          <p className="text-xs text-w-dim truncate">{channel.description}</p>
        )}
      </div>
      <div className="flex items-center gap-2 shrink-0">
        {onlineUsers.length > 0 && (
          <span className="hidden sm:flex items-center gap-1 text-xs text-w-dim">
            <span className="w-2 h-2 bg-w-accent rounded-full" />
            {onlineUsers.length} online
          </span>
        )}
        {/* Primary actions — always inline */}
        <button
          onClick={() => setShowMembers(!showMembers)}
          className={`p-1.5 rounded hover:bg-w-surface2 ${showMembers ? 'text-w-accent' : 'text-w-dim'}`}
          title="Members"
        >
          <Users size={16} />
        </button>
        {isMember && (
          <button
            onClick={voice.callState === 'idle' ? voice.joinCall : undefined}
            className="p-1.5 rounded hover:bg-w-surface2 text-w-dim hover:text-w-accent"
            title="Voice call"
          >
            <Phone size={16} />
          </button>
        )}
        {/* Secondary actions — inline on desktop */}
        <div className="hidden sm:flex items-center gap-2">
          {secondaryActions.map((a) => (
            <button
              key={a.key}
              onClick={a.onClick}
              className={`p-1.5 rounded hover:bg-w-surface2 ${a.hover} ${a.active ? 'text-w-accent' : 'text-w-dim'}`}
              title={a.label}
            >
              <a.icon size={16} />
            </button>
          ))}
        </div>
        {/* Secondary actions — kebab dropdown on mobile */}
        {secondaryActions.length > 0 && (
          <div className="relative sm:hidden">
            <button
              onClick={() => setShowMobileActions((v) => !v)}
              className={`p-1.5 rounded hover:bg-w-surface2 ${showMobileActions ? 'text-w-accent' : 'text-w-dim'}`}
              title="More"
            >
              <MoreHorizontal size={18} />
            </button>
            {showMobileActions && (
              <>
                <div className="fixed inset-0 z-20" onClick={() => setShowMobileActions(false)} />
                <div className="absolute right-0 top-full mt-1 z-30 min-w-[180px] py-1 bg-w-surface border border-w-line rounded-lg shadow-xl">
                  {secondaryActions.map((a) => (
                    <button
                      key={a.key}
                      onClick={() => { a.onClick(); setShowMobileActions(false) }}
                      className={`w-full flex items-center gap-2.5 px-3 py-2 text-sm text-left hover:bg-w-surface2 ${a.active ? 'text-w-accent' : 'text-w-text'} ${a.hover}`}
                    >
                      <a.icon size={16} className="shrink-0" />
                      <span className="flex-1">{a.label}</span>
                      {a.active && <span className="w-1.5 h-1.5 rounded-full bg-w-accent shrink-0" />}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
