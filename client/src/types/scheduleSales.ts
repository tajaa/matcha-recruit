export type SalesSetupStatus = {
  location_id: string
  days_with_sales: number
  latest_sales_date: string | null
  draft_imports: number
  square_configured: boolean
  square_connected: boolean
  square_bound: boolean
  square_sync_enabled: boolean
  mailbox_configured: boolean
  mailbox_address: string | null
  email_registered: boolean
  email_poll_enabled: boolean
}
