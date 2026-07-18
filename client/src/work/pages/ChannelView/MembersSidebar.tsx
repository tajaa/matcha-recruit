import { Crown, Shield, X } from 'lucide-react'
import { getChannel, kickMember, setMemberRole } from '../../api/channels'
import type { ChannelDetail, ChannelMember } from '../../api/channels'

type OnlineUser = { id: string; name: string; avatar_url: string | null }

interface MembersSidebarProps {
  channel: ChannelDetail | null
  onlineUsers: OnlineUser[]
  userId: string | undefined
  setChannel: (channel: ChannelDetail) => void
}

export default function MembersSidebar({
  channel,
  onlineUsers,
  userId,
  setChannel,
}: MembersSidebarProps) {
  return (
    <div className="w-64 border-l border-w-line overflow-y-auto px-3 py-3 hidden sm:block">
      <h3 className="text-xs font-medium text-w-dim uppercase mb-2">
        Members ({channel?.member_count ?? 0})
      </h3>
      <div className="space-y-0.5">
        {channel?.members.map((m: ChannelMember) => {
          const isOnline = onlineUsers.some((u) => u.id === m.user_id)
          const canManage = channel.my_role === 'owner' || (channel.my_role === 'moderator' && m.channel_role === 'member')
          const isMe = m.user_id === userId
          return (
            <div key={m.user_id} className="group flex items-center gap-2 py-1.5 px-1 rounded hover:bg-w-surface2/50">
              <span className={`w-2 h-2 rounded-full shrink-0 ${isOnline ? 'bg-w-accent' : 'bg-w-surface2'}`} />
              <span className="text-sm text-w-text truncate flex-1">{m.name}</span>
              {m.channel_role === 'owner' && (
                <Crown size={12} className="text-amber-500 shrink-0" aria-label="Owner" />
              )}
              {m.channel_role === 'moderator' && (
                <Shield size={12} className="text-blue-400 shrink-0" aria-label="Moderator" />
              )}
              {!isMe && canManage && (
                <div className="opacity-0 group-hover:opacity-100 flex items-center gap-0.5 shrink-0">
                  {channel.my_role === 'owner' && m.channel_role !== 'owner' && (
                    <button
                      onClick={async () => {
                        try {
                          const newRole = m.channel_role === 'moderator' ? 'member' : 'moderator'
                          await setMemberRole(channel.id, m.user_id, newRole)
                          const data = await getChannel(channel.id)
                          setChannel(data)
                        } catch {}
                      }}
                      className="p-0.5 text-w-dim hover:text-blue-400"
                      title={m.channel_role === 'moderator' ? 'Remove moderator' : 'Make moderator'}
                    >
                      <Shield size={11} />
                    </button>
                  )}
                  <button
                    onClick={async () => {
                      try {
                        await kickMember(channel.id, m.user_id)
                        const data = await getChannel(channel.id)
                        setChannel(data)
                      } catch {}
                    }}
                    className="p-0.5 text-w-dim hover:text-red-400"
                    title="Remove from channel"
                  >
                    <X size={11} />
                  </button>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
