import type { ChannelDetail, ChannelPaymentInfo } from '../../api/channels'
import { getChannel } from '../../api/channels'
import AddMembersModal from '../../components/channels/AddMembersModal'
import ChannelSettingsPanel from '../../components/channels/ChannelSettingsPanel'
import ChannelAnalytics from '../../components/channels/ChannelAnalytics'
import TipModal from '../../components/channels/TipModal'
import JobPostingsPanel from '../../components/channels/JobPostingsPanel'
import JobPostingDetail from '../../components/channels/JobPostingDetail'

interface ChannelModalsProps {
  channel: ChannelDetail | null
  channelId: string | undefined
  paymentInfo: ChannelPaymentInfo | null
  showSettings: boolean
  setShowSettings: (v: boolean) => void
  showAnalytics: boolean
  setShowAnalytics: (v: boolean) => void
  showTip: boolean
  setShowTip: (v: boolean) => void
  showJobPostings: boolean
  setShowJobPostings: (v: boolean) => void
  activePostingId: string | null
  setActivePostingId: (id: string | null) => void
  showAddMembers: boolean
  setShowAddMembers: (v: boolean) => void
  setChannel: (channel: ChannelDetail) => void
}

export default function ChannelModals({
  channel,
  channelId,
  paymentInfo,
  showSettings,
  setShowSettings,
  showAnalytics,
  setShowAnalytics,
  showTip,
  setShowTip,
  showJobPostings,
  setShowJobPostings,
  activePostingId,
  setActivePostingId,
  showAddMembers,
  setShowAddMembers,
  setChannel,
}: ChannelModalsProps) {
  return (
    <>
      {showSettings && channel && (
        <ChannelSettingsPanel
          channelId={channel.id}
          channelName={channel.name}
          isPaid={paymentInfo?.is_paid ?? false}
          onClose={() => setShowSettings(false)}
        />
      )}

      {showAnalytics && channel && (
        <ChannelAnalytics
          channelId={channel.id}
          channelName={channel.name}
          onClose={() => setShowAnalytics(false)}
        />
      )}

      {showTip && channel && (
        <TipModal
          channelId={channel.id}
          channelName={channel.name}
          onClose={() => setShowTip(false)}
        />
      )}

      {showJobPostings && channel && (
        <JobPostingsPanel
          channelId={channel.id}
          myRole={channel.my_role ?? 'member'}
          onClose={() => setShowJobPostings(false)}
          onOpenDetail={(id) => { setActivePostingId(id); setShowJobPostings(false) }}
        />
      )}

      {activePostingId && channel && (
        <JobPostingDetail
          channelId={channel.id}
          postingId={activePostingId}
          myRole={channel.my_role ?? 'member'}
          onClose={() => setActivePostingId(null)}
        />
      )}

      {showAddMembers && channel && (
        <AddMembersModal
          channelId={channel.id}
          channelName={channel.name}
          existingMemberIds={channel.members.map((m) => m.user_id)}
          onClose={() => setShowAddMembers(false)}
          onAdded={async () => {
            setShowAddMembers(false)
            // Refresh channel to update member list
            if (channelId) {
              const data = await getChannel(channelId)
              setChannel(data)
            }
          }}
        />
      )}
    </>
  )
}
