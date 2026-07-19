import { Loader2 } from 'lucide-react'
import { getConversation, sendMessage as sendInboxMessage } from '../../api/inbox'
import { ConversationList } from '../../components/inbox/ConversationList'
import { MessageThread } from '../../components/inbox/MessageThread'
import { ComposeModal } from '../../components/inbox/ComposeModal'
import type { ProjectViewModel } from './useProjectView'

interface Props {
  vm: ProjectViewModel
}

/** Center pane when the sidebar is in inbox mode: DM thread, conversation list, compose. */
export function InboxPane({ vm }: Props) {
  const { activeTab, currentUserId, setMobileMenuOpen } = vm
  const {
    inboxConversations,
    inboxActiveConvo,
    setInboxActiveConvo,
    inboxLoading,
    inboxComposeOpen,
    setInboxComposeOpen,
    loadInbox,
  } = vm.inbox

  return (
    <div className={`flex-1 flex-col min-w-0 min-h-0 bg-w-bg ${activeTab === vm.aiTab ? 'flex' : 'hidden'}`}>
      {inboxActiveConvo ? (
        <MessageThread
          conversation={inboxActiveConvo}
          currentUserId={currentUserId}
          onSendMessage={async (content) => {
            const msg = await sendInboxMessage(inboxActiveConvo.id, content)
            setInboxActiveConvo((prev) => prev ? { ...prev, messages: [...prev.messages, msg] } : prev)
          }}
          onMarkRead={() => {}}
          onBack={() => { setInboxActiveConvo(null); loadInbox() }}
        />
      ) : inboxLoading ? (
        <div className="flex items-center justify-center h-full">
          <Loader2 size={20} className="animate-spin text-[var(--color-w-dim)]" />
        </div>
      ) : (
        <ConversationList
          conversations={inboxConversations}
          selectedId={null}
          currentUserId={currentUserId}
          onSelect={async (id) => {
            try {
              const convo = await getConversation(id)
              setInboxActiveConvo(convo)
            } catch {}
          }}
          onCompose={() => setInboxComposeOpen(true)}
          onMenuToggle={() => setMobileMenuOpen(true)}
        />
      )}
      <ComposeModal
        isOpen={inboxComposeOpen}
        onClose={() => setInboxComposeOpen(false)}
        onCreated={(convo) => {
          setInboxActiveConvo(convo)
          setInboxComposeOpen(false)
          loadInbox()
        }}
      />
    </div>
  )
}
