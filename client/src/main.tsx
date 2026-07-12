import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { ToastProvider } from './components/ui'
import { ErrorBoundary } from './components/ErrorBoundary'
import { installErrorReporter } from './api/errorReporter'
import { installUsageTracker } from './lib/usageTracker'
import { reloadForStaleChunk } from './utils/staleChunk'
import './index.css'

installErrorReporter()
installUsageTracker()

// Stale-chunk recovery: after a deploy, hashed chunks from the previous build
// 404 for tabs that loaded the old index ("Failed to fetch dynamically
// imported module"). Reload once to pick up the new manifest. See
// utils/staleChunk for the shared detection + one-shot guard (ErrorBoundary
// uses the same guard for React.lazy failures that bypass this event).
window.addEventListener('vite:preloadError', (event) => {
  event.preventDefault()
  reloadForStaleChunk()
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
