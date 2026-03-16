import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Logo } from '../components/ui'
import { AsciiHalftone } from '../components/AsciiHalftone'
import { api } from '../api/client'

type LoginResponse = {
  access_token: string
  refresh_token: string
  user: { role: string }
}

const roleRoutes: Record<string, string> = {
  admin: '/admin',
  client: '/app',
  employee: '/portal',
  candidate: '/candidate',
}

function GrayInput({ label, id, ...props }: React.ComponentProps<'input'> & { label: string }) {
  return (
    <div>
      <label htmlFor={id} className="block text-xs font-medium tracking-[0.1em] text-zinc-400 mb-1.5 font-[Space_Mono] uppercase">
        {label}
      </label>
      <input
        id={id}
        className="w-full rounded-lg border border-zinc-700 bg-zinc-900/80 px-3.5 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-zinc-500 focus:ring-1 focus:ring-zinc-500 transition-colors"
        {...props}
      />
    </div>
  )
}

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await api.post<LoginResponse>('/auth/login', { email, password })
      localStorage.setItem('matcha_access_token', res.access_token)
      localStorage.setItem('matcha_refresh_token', res.refresh_token)
      navigate(roleRoutes[res.user.role] ?? '/app')
    } catch {
      setError('Invalid email or password')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative min-h-screen bg-zinc-900 flex items-center justify-center px-4 overflow-hidden">
      <AsciiHalftone />
      <div className="relative z-10 w-full max-w-sm">
        <Logo className="justify-center mb-10 grayscale" />

        <form onSubmit={handleSubmit} className="space-y-5">
          <GrayInput
            id="email"
            label="Email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
          />
          <GrayInput
            id="password"
            label="Password"
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
          />
          {error && <p className="text-sm text-red-400">{error}</p>}
          <Button
            type="submit"
            variant="secondary"
            className="w-full tracking-[0.15em] font-[Space_Mono] uppercase border border-zinc-600"
            disabled={loading}
          >
            {loading ? 'Signing in...' : 'Sign in'}
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-zinc-500">
          Don&apos;t have an account?{' '}
          <span className="text-zinc-300 cursor-pointer hover:text-zinc-100 transition-colors">
            Contact sales
          </span>
        </p>
      </div>
    </div>
  )
}
