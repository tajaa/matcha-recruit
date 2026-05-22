export type NewsItem = {
  id: string
  title: string
  description: string | null
  link: string
  pub_date: string | null
  source_name: string | null
  source_feed_url: string | null
  image_url: string | null
}

export type NewsResponse = { items: NewsItem[] }
