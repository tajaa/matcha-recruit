import type { MWMessage } from '../types'
import { BaseSocket } from './baseSocket'

type NewMessageHandler = (messages: MWMessage[]) => void
type TypingHandler = (user: { id: string; name: string }) => void
type OnlineHandler = (users: { id: string; name: string }[]) => void
type UserEventHandler = (user: { id: string; name: string }) => void

export class ThreadSocket extends BaseSocket {
  private currentThread: string | null = null

  onNewMessage: NewMessageHandler | null = null
  onTyping: TypingHandler | null = null
  onOnlineUsers: OnlineHandler | null = null
  onUserJoined: UserEventHandler | null = null
  onUserLeft: UserEventHandler | null = null

  protected path() {
    return '/ws/threads'
  }

  protected rejoin() {
    if (this.currentThread) {
      this.send({ type: 'join_thread', thread_id: this.currentThread })
    }
  }

  protected clearState() {
    this.currentThread = null
  }

  protected handleMessage(data: Record<string, unknown>) {
    switch (data.type) {
      case 'new_messages':
        this.onNewMessage?.(data.messages as MWMessage[])
        break
      case 'typing':
        this.onTyping?.(data.user as { id: string; name: string })
        break
      case 'online_users':
        this.onOnlineUsers?.(data.users as { id: string; name: string }[])
        break
      case 'user_joined':
        this.onUserJoined?.(data.user as { id: string; name: string })
        break
      case 'user_left':
        this.onUserLeft?.(data.user as { id: string; name: string })
        break
    }
  }

  joinThread(threadId: string) {
    this.currentThread = threadId
    this.send({ type: 'join_thread', thread_id: threadId })
  }

  leaveThread(threadId: string) {
    this.send({ type: 'leave_thread', thread_id: threadId })
    if (this.currentThread === threadId) this.currentThread = null
  }

  sendTyping(threadId: string) {
    this.send({ type: 'typing', thread_id: threadId })
  }
}
