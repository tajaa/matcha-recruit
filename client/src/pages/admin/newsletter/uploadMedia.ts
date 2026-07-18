// Shared upload helper — both image and video go to the same endpoint;
// the backend keys off file extension and the editor inserts the right tag.
import { api } from '../../../api/client'

export async function uploadNewsletterMedia(file: File): Promise<string | null> {
  const form = new FormData()
  form.append('file', file)
  try {
    const data = await api.upload<{ url: string }>('/admin/newsletter/media/upload', form)
    return data.url
  } catch {
    return null
  }
}
