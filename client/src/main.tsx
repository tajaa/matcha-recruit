import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { ToastProvider } from './components/ui'
import { ErrorBoundary } from './components/ErrorBoundary'
import { installErrorReporter } from './api/errorReporter'
import './index.css'

installErrorReporter()

// Stale-chunk recovery: after a deploy, hashed chunks from the previous build
// 404 for tabs that loaded the old index ("Failed to fetch dynamically
// imported module"). Reload once to pick up the new manifest. The time guard
// means a genuinely broken asset surfaces normally (and gets error-reported)
// instead of looping reloads.
window.addEventListener('vite:preloadError', (event) => {
  const last = Number(sessionStorage.getItem('matcha_chunk_reload_at') ?? 0)
  if (Date.now() - last < 60_000) return
  sessionStorage.setItem('matcha_chunk_reload_at', String(Date.now()))
  event.preventDefault()
  window.location.reload()
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <ErrorBoundary>
        <ToastProvider>
          <App />
        </ToastProvider>
      </ErrorBoundary>
    </BrowserRouter>
  </StrictMode>,
)
