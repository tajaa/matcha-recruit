import { useState } from 'react'
import { Link, Route, Routes } from 'react-router-dom'
import { getToken, login, logout } from './api/client'
import { CatalogPage } from './pages/CatalogPage'
import { ReleaseDetailPage } from './pages/ReleaseDetailPage'
import { SettingsPage } from './pages/SettingsPage'

function TokenGate({ children }: { children: React.ReactNode }) {
  const [hasToken, setHasToken] = useState(!!getToken())
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  if (hasToken) return <>{children}</>

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="border rounded-lg p-6 w-full max-w-sm">
          <h1 className="text-lg font-semibold mb-3">oceanlab admin</h1>
          <p className="text-sm text-neutral-500 mb-3">Sign in with your master-admin account.</p>
          <input className="border rounded px-2 py-1 text-sm w-full mb-3" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          <input
          className="border rounded px-2 py-1 text-sm w-full mb-3"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
        />
        <button
          className="w-full px-3 py-1.5 rounded bg-black text-white dark:bg-white dark:text-black text-sm"
          onClick={() => {
            void login(email, password).then(() => setHasToken(true)).catch(() => setError('Invalid email or password'))
          }}
          disabled={!email || !password}
        >
          Continue
        </button>
        {error && <p className="text-sm text-red-600 mt-3">{error}</p>}
      </div>
    </div>
  )
}

function LandingPage() {
  return <main className="landing-page">
    <nav className="landing-nav"><Link className="wordmark" to="/">oceanlab<span>.</span></Link><a href="#about">About</a><a href="#contact">Contact</a><Link className="nav-button" to="/admin">Label portal</Link></nav>
    <section className="hero"><div className="hero-copy"><p className="eyebrow">Independent music, carefully released</p><h1>Make room for<br /><em>the next sound.</em></h1><p className="hero-lede">Oceanlab is an independent record label for artists with something singular to say. We build considered releases, long-term careers, and a catalog that stays in rotation.</p><a className="primary-button" href="#about">Explore Oceanlab <span>↗</span></a></div><div className="hero-art"><div className="art-sun" /><div className="art-ring" /><div className="art-line art-line-one" /><div className="art-line art-line-two" /><span className="art-caption">OCEANLAB / 001</span></div></section>
    <section className="ticker"><span>Artists first</span><b>✦</b><span>Independent forever</span><b>✦</b><span>Sound with intent</span></section>
    <section className="about-section" id="about"><p className="eyebrow">A small label with a wide horizon</p><div className="about-grid"><h2>Music that<br /><em>finds its people.</em></h2><p>From first demo to final master, Oceanlab gives artists the space, attention, and practical support to make their best work. No conveyor belt. No noise for noise's sake. Just great records, released with care.</p></div></section>
    <footer id="contact"><span className="wordmark">oceanlab<span>.</span></span><span>For demos, collaborations, and good conversations:<br /><a href="mailto:hello@oceanlab.co">hello@oceanlab.co</a></span><span>© 2026 Oceanlab</span></footer>
  </main>
}

function Admin() {
  return <TokenGate><nav className="admin-nav"><Link className="font-semibold" to="/">oceanlab</Link><Link to="/admin">Catalog</Link><Link to="/admin/settings">Settings</Link><button type="button" onClick={() => { void logout().finally(() => window.location.reload()) }}>Sign out</button></nav><Routes><Route path="/admin" element={<CatalogPage />} /><Route path="/admin/releases/:id" element={<ReleaseDetailPage />} /><Route path="/admin/settings" element={<SettingsPage />} /></Routes></TokenGate>
}

function App() {
  return (
    <Routes><Route path="/" element={<LandingPage />} /><Route path="/*" element={<Admin />} /></Routes>
  )
}

export default App
