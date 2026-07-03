// Shared upload helper — both image and video go to the same endpoint;
// the backend keys off file extension and the editor inserts the right tag.
export async function uploadNewsletterMedia(file: File): Promise<string | null> {
  const BASE = import.meta.env.VITE_API_URL ?? '/api'
  const token = localStorage.getItem('matcha_access_token')
  const form = new FormData()
  form.append('file', file)
  try {
    const res = await fetch(`${BASE}/admin/newsletter/media/upload`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    })
    if (!res.ok) return null
    const data = await res.json()
    return data.url
  } catch {
    return null
  }
}
