export interface Props {
  onClose: () => void
  onCreated: (channel: { id: string; name: string; slug: string }) => void
  canCreatePaid?: boolean
}

export type AccessModel = 'free' | 'paid' | 'paid_engagement'
