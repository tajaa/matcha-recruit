import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { ToastProvider } from './components/ui'
import { ErrorBoundary } from './components/shared/ErrorBoundary'
import { installErrorReporter } from './api/errorReporter'
import { installSessionSecurity } from './api/sessionSecurity'
import { installUsageTracker } from './utils/usageTracker'
import { reloadForStaleChunk } from './utils/staleChunk'
import { applyTheme, getTheme } from './utils/theme'
import './index.css'

installErrorReporter()
installSessionSecurity()
installUsageTracker()
applyTheme(getTheme())

// Stale-chunk recovery: after a deploy, hashed chunks from the previous build
// 404 for tabs that loaded the old index ("Failed to fetch dynamically
// imported module"). Reload once to pick up the new manifest. See
// utils/staleChunk for the shared detection + one-shot guard (ErrorBoundary
// uses the same guard for React.lazy failures that bypass this event).
window.addEventListener('vite:preloadError', () => {
  // Do not cancel the event: Vite interprets preventDefault() as recovery and
  // resolves the failed import with undefined, which makes React.lazy throw
  // while the reload is pending when it reads the module's default export.
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
