// Shared types for the ChannelView module.

export type HeaderAction = {
  key: string
  icon: React.ElementType
  label: string
  onClick: () => void
  active?: boolean
  hover: string
}
