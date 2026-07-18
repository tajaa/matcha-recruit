export type BlogStatus = 'draft' | 'published' | 'archived'

export type BlogPost = {
  id: string
  title: string
  slug: string
  content: string
  excerpt: string | null
  cover_image: string | null
  status: BlogStatus
  tags: string[]
  meta_title: string | null
  meta_description: string | null
  published_at: string | null
  created_at: string
  updated_at: string
  author_name?: string
  likes_count?: number
  submitted_for_review?: boolean
  submitted_at?: string | null
  source_project_id?: string | null
  review_notes?: string | null
}

export type BlogList = { items: BlogPost[]; total: number }

export type AdminTab = 'posts' | 'comments'

export type PendingComment = {
  id: string
  post_id: string
  user_id: string | null
  author_name: string
  content: string
  status: 'pending' | 'approved' | 'rejected' | 'spam'
  created_at: string
  post_title?: string | null
}
