import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { AccountProvider } from './hooks/useAccount'
import './index.css'

// basename='/tellus' — the app is served at /tellus/ by the shared nginx
// container, so the router must strip that prefix from every path.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter basename="/tellus">
      <AccountProvider>
        <App />
      </AccountProvider>
    </BrowserRouter>
  </StrictMode>,
)
