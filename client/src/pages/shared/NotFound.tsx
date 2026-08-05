import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <div className="min-h-screen bg-[#0c0c0e] flex items-center justify-center px-4">
      <div className="max-w-sm w-full text-center">
        <h1 className="text-xl font-semibold text-zinc-100 mb-2">Page not found</h1>
        <p className="text-sm text-zinc-500 mb-6">
          The page you're looking for doesn't exist or the link may be out of date.
        </p>
        <Link
          to="/"
          className="inline-block text-sm text-emerald-500 hover:text-emerald-400 transition-colors"
        >
          Go to hey-matcha.com
        </Link>
      </div>
    </div>
  )
}
