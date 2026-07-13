export type Subscriber = {
  id: string; email: string; name: string | null; source: string
  status: string; subscribed_at: string; unsubscribed_at: string | null
}

export type Newsletter = {
  id: string; title: string; subject: string; status: string
  content_html: string | null; preheader: string | null
  scheduled_at: string | null; sent_at: string | null; created_at: string
  total_sends?: number; total_opened?: number
}

export type SubStats = { total: number; active: number; by_source: Record<string, number> }

export type Tag = { id: string; slug: string; label: string; description: string | null; subscriber_count: number }

export type Template = {
  id: string; name: string; description: string | null
  content_html: string | null; preheader: string | null
  created_at: string; updated_at: string
}

export type Idea = {
  id: string; title: string; notes: string | null; media_url: string | null
  status: 'idea' | 'converted'; newsletter_id: string | null
  created_at: string; updated_at: string
}

export type GrowthPoint = { day: string; subscribed: number; confirmed: number }

export type Analytics = {
  attempted: number; sent: number; failed: number
  opened: number; clicked: number
  bounced: number; unsubscribed_window: number
  open_rate: number; click_rate: number; bounce_rate: number; unsubscribe_rate: number
}

export type Progress = {
  newsletter_status: string | null
  queued: number; sent: number; failed: number; pending: number
  opened: number; clicked: number; bounced: number
}

export type Tab = 'ideas' | 'subscribers' | 'newsletters' | 'compose' | 'tags' | 'templates'
