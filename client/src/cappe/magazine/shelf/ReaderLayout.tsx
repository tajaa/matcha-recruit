import { useEffect } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { cappeApi, clearCappeTokens, getCappeToken } from '../../api'
import { invalidateCappeMeCache, useCappeMe } from '../../hooks/useCappeMe'
import { readerPaths } from './readerPaths'

/** The reader's dashboard shell: a slim bar over the page, no site-building
 *  sidebar. Without a session it sends the reader to sign in and back. */
export default function ReaderLayout() {
  const { account, loading } = useCappeMe()
  const navigate = useNavigate()
  const location = useLocation()
  const here = location.pathname + location.search

  useEffect(() => {
    if (!getCappeToken() || (!loading && !account)) {
      navigate(`${readerPaths.login}?next=${encodeURIComponent(here)}`, { replace: true })
    }
  }, [loading, account, navigate, here])

  async function signOut() {
    await cappeApi.post('/auth/logout').catch(() => {})
    clearCappeTokens()
    invalidateCappeMeCache()
    navigate(readerPaths.login)
  }

  if (loading || !account) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950">
        <Loader2 className="h-6 w-6 animate-spin text-zinc-600" />
      </div>
    )
  }

  return (
    <div className="flex min-h-dvh flex-col bg-zinc-950 text-zinc-100">
      <header className="flex items-center gap-3 border-b border-zinc-800 bg-zinc-900 px-4 py-3">
        <Link to={readerPaths.home} className="flex items-center gap-2 font-semibold tracking-tight text-zinc-50">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-lime-300 to-lime-500 text-sm font-bold text-zinc-950">G</span>
          My magazines
        </Link>
        <span className="ml-auto hidden truncate text-xs text-zinc-500 sm:inline">{account.email}</span>
        <button type="button" onClick={signOut} className="text-sm text-zinc-400 hover:text-zinc-100">Sign out</button>
      </header>
      <main className="flex min-h-0 flex-1 flex-col">
        <Outlet />
      </main>
    </div>
  )
}
