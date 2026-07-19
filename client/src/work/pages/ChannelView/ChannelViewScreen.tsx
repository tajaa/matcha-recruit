import InactivityWarningBanner from '../../components/channels/InactivityWarningBanner'
import VoiceCallBar from '../../components/channels/VoiceCallBar'
import JobInviteBanner from '../../components/channels/JobInviteBanner'
import ChannelOpenRoleBanner from '../../components/channels/ChannelOpenRoleBanner'
import { useChannelView } from './useChannelView'
import { ChannelLoading, ChannelJoinGate, ChannelErrorGate } from './ChannelGate'
import ChannelHeader from './ChannelHeader'
import MessageList from './MessageList'
import MessageComposer from './MessageComposer'
import MembersSidebar from './MembersSidebar'
import ChannelModals from './ChannelModals'

interface ChannelViewScreenProps {
  /** Render this channel instead of the route's `:channelId`. See useChannelView. */
  channelId?: string | null
  /** Rendered inside another surface (the collab project view) rather than as
   *  the `/channels/:id` page. Hides the leave action — see useChannelView. */
  embedded?: boolean
}

export default function ChannelViewScreen({ channelId: channelIdOverride, embedded = false }: ChannelViewScreenProps = {}) {
  const {
    channelId,
    navigate,
    base,
    brand,
    userId,
    channel,
    setChannel,
    messages,
    input,
    loading,
    error,
    typingUsers,
    onlineUsers,
    showMembers,
    setShowMembers,
    isMember,
    joining,
    showAddMembers,
    setShowAddMembers,
    pendingFiles,
    setPendingFiles,
    uploading,
    mentionQuery,
    mentionMatches,
    inputTextareaRef,
    paymentInfo,
    warningDismissed,
    setWarningDismissed,
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
    openPostings,
    showMobileActions,
    setShowMobileActions,
    fileInputRef,
    messagesEndRef,
    messagesContainerRef,
    voice,
    postingParam,
    canModerate,
    handleDeleteMessage,
    handleSend,
    applyMention,
    handleKeyDown,
    handleInputChange,
    handleJoin,
    typingText,
    secondaryActions,
  } = useChannelView(channelIdOverride, embedded)

  if (loading) {
    return <ChannelLoading />
  }

  // Not a member — show join prompt or invite-only message
  if (!isMember && !error) {
    return (
      <ChannelJoinGate
        channel={channel}
        paymentInfo={paymentInfo}
        joining={joining}
        onJoin={handleJoin}
        onBack={() => navigate(base)}
        brand={brand}
      />
    )
  }

  if (error) {
    return <ChannelErrorGate error={error} onBack={() => navigate(base)} brand={brand} />
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <ChannelHeader
        channel={channel}
        paymentInfo={paymentInfo}
        onlineUsers={onlineUsers}
        showMembers={showMembers}
        setShowMembers={setShowMembers}
        isMember={isMember}
        voice={voice}
        secondaryActions={secondaryActions}
        showMobileActions={showMobileActions}
        setShowMobileActions={setShowMobileActions}
      />

      {paymentInfo?.days_until_removal != null && paymentInfo.days_until_removal <= (paymentInfo.inactivity_warning_days ?? 3) && !warningDismissed && (
        <InactivityWarningBanner
          daysUntilRemoval={Math.ceil(paymentInfo.days_until_removal)}
          onDismiss={() => setWarningDismissed(true)}
        />
      )}

      {isMember && paymentInfo?.is_paid && (
        <div className="flex items-center gap-4 px-4 py-1.5 border-b border-w-line/50 bg-w-surface/60 text-xs text-w-dim">
          <span className="text-w-accent font-medium">${((paymentInfo.price_cents ?? 0) / 100).toFixed(2)}/mo</span>
          <span>{channel?.member_count ?? 0} members</span>
          {onlineUsers.length > 0 && <span>{onlineUsers.length} online</span>}
          {paymentInfo.subscription_status === 'active' && (
            <button
              onClick={() => navigate(`${base}/billing`)}
              className="ml-auto text-w-faint"
            >
              Manage subscription
            </button>
          )}
        </div>
      )}

      {(voice.callState !== 'idle' || voice.participants.length > 0) && (
        <VoiceCallBar
          callState={voice.callState}
          participants={voice.participants}
          isMuted={voice.isMuted}
          isVideoEnabled={voice.isVideoEnabled}
          elapsedSeconds={voice.elapsedSeconds}
          localStream={voice.localStream}
          onJoin={voice.joinCall}
          onLeave={voice.leaveCall}
          onToggleMute={voice.toggleMute}
          onToggleVideo={voice.toggleVideo}
          activeCallUsers={voice.participants.map(p => ({ user_id: p.userId, name: p.name }))}
        />
      )}

      {postingParam && !activePostingId && channelId && (
        <JobInviteBanner
          channelId={channelId}
          postingId={postingParam}
          onView={() => setActivePostingId(postingParam)}
        />
      )}

      {openPostings.length > 0 && !activePostingId && (
        <ChannelOpenRoleBanner
          postings={openPostings}
          onView={(id) => setActivePostingId(id)}
        />
      )}

      <div className="flex flex-1 min-h-0">
        {/* Messages */}
        <div className="flex-1 flex flex-col min-w-0">
          <MessageList
            messages={messages}
            messagesContainerRef={messagesContainerRef}
            messagesEndRef={messagesEndRef}
            userId={userId}
            canModerate={canModerate}
            members={channel?.members ?? []}
            onDelete={handleDeleteMessage}
          />

          {/* Typing indicator */}
          {typingText && (
            <div className="px-4 pb-1 text-xs text-w-dim italic">
              {typingText} {typingUsers.size === 1 ? 'is' : 'are'} typing...
            </div>
          )}

          {/* Input */}
          <MessageComposer
            pendingFiles={pendingFiles}
            setPendingFiles={setPendingFiles}
            fileInputRef={fileInputRef}
            mentionQuery={mentionQuery}
            mentionMatches={mentionMatches}
            applyMention={applyMention}
            inputTextareaRef={inputTextareaRef}
            input={input}
            onInputChange={handleInputChange}
            onKeyDown={handleKeyDown}
            channelName={channel?.name}
            onSend={handleSend}
            uploading={uploading}
          />
        </div>

        {/* Members sidebar */}
        {showMembers && (
          <MembersSidebar
            channel={channel}
            onlineUsers={onlineUsers}
            userId={userId}
            setChannel={setChannel}
          />
        )}
      </div>

      <ChannelModals
        channel={channel}
        channelId={channelId}
        paymentInfo={paymentInfo}
        showSettings={showSettings}
        setShowSettings={setShowSettings}
        showAnalytics={showAnalytics}
        setShowAnalytics={setShowAnalytics}
        showTip={showTip}
        setShowTip={setShowTip}
        showJobPostings={showJobPostings}
        setShowJobPostings={setShowJobPostings}
        activePostingId={activePostingId}
        setActivePostingId={setActivePostingId}
        showAddMembers={showAddMembers}
        setShowAddMembers={setShowAddMembers}
        setChannel={setChannel}
      />
    </div>
  )
}
