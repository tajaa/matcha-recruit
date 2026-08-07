import { getToken } from '../api/client'

export function uploadWithProgress(
  url: string,
  file: File,
  fields: Record<string, string> = {},
  onProgress: (pct: number) => void = () => {},
): Promise<XMLHttpRequest> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const form = new FormData()
    for (const [key, value] of Object.entries(fields)) {
      form.append(key, value)
    }
    form.append('file', file)

    xhr.open('POST', url)
    const token = getToken()
    if (token) {
      xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    }
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100))
      }
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(xhr)
      } else {
        reject(new Error(`Upload failed: ${xhr.status} ${xhr.statusText}`))
      }
    }
    xhr.onerror = () => reject(new Error('Upload network error'))
    xhr.send(form)
  })
}
