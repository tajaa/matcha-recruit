// Google Identity Services — "Sign in with Google" (button only, no One Tap).
// OAuth web client IDs are public by design (visible in the page source of
// every GIS-using site) — safe to hardcode. Matches the iOS client ID's
// treatment in platforms/ios/TellUs/project.yml.
export const GOOGLE_CLIENT_ID = '62787429179-17f4l11tim353s9dqgu8fc1cei0up55m.apps.googleusercontent.com'

const GSI_SRC = 'https://accounts.google.com/gsi/client'

let scriptPromise: Promise<void> | null = null

/** Loads Google Identity Services once; repeat calls share the same promise. */
export function loadGoogleIdentityScript(): Promise<void> {
  if (scriptPromise) return scriptPromise
  scriptPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${GSI_SRC}"]`)
    if (existing) {
      resolve()
      return
    }
    const script = document.createElement('script')
    script.src = GSI_SRC
    script.async = true
    script.defer = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Failed to load Google Identity Services'))
    document.head.appendChild(script)
  })
  return scriptPromise
}

// Minimal surface — the three functions this app actually calls. Narrower
// than pulling in @types/google.accounts for one file.
declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize(config: {
            client_id: string
            callback: (response: { credential: string }) => void
          }): void
          renderButton(parent: HTMLElement, options: Record<string, string>): void
        }
      }
    }
  }
}
