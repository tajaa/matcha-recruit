import { useState } from 'react'
import { Link, Route, Routes } from 'react-router-dom'
import { getToken, setToken } from './api/client'
import { CatalogPage } from './pages/CatalogPage'
import { ReleaseDetailPage } from './pages/ReleaseDetailPage'
import { SettingsPage } from './pages/SettingsPage'

function TokenGate({ children }: { children: React.ReactNode }) {
  const [hasToken, setHasToken] = useState(!!getToken())
  const [input, setInput] = useState('')

  if (hasToken) return <>{children}</>

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="border rounded-lg p-6 w-full max-w-sm">
        <h1 className="text-lg font-semibold mb-3">oceanlab</h1>
        <p className="text-sm text-neutral-500 mb-3">Enter your access token.</p>
        <input
          className="border rounded px-2 py-1 text-sm w-full mb-3"
          type="password"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="OCEANLAB_TOKEN"
        />
        <button
          className="w-full px-3 py-1.5 rounded bg-black text-white dark:bg-white dark:text-black text-sm"
          onClick={() => {
            setToken(input)
            setHasToken(true)
          }}
          disabled={!input}
        >
          Continue
        </button>
      </div>
    </div>
  )
}

function Nav() {
  return (
    <nav className="border-b px-6 py-3 flex gap-4 text-sm">
      <Link className="font-semibold" to="/">
        oceanlab
      </Link>
      <Link to="/">Catalog</Link>
      <Link to="/settings">Settings</Link>
    </nav>
  )
}

function App() {
  return (
    <TokenGate>
      <Nav />
      <Routes>
        <Route path="/" element={<CatalogPage />} />
        <Route path="/releases/:id" element={<ReleaseDetailPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </TokenGate>
  )
}

export default App
