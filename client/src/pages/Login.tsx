import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Input, Logo } from '../components/ui'
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

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  async function handleSubmit(e: FormEvent) {
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
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <Logo className="justify-center mb-10" />

        <form onSubmit={handleSubmit} className="space-y-5">
          <Input
            id="email"
            label="Email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
          />
          <Input
            id="password"
            label="Password"
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
          />
          {error && (
            <p className="text-sm text-red-400">{error}</p>
          )}
          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? 'Signing in...' : 'Sign in'}
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-zinc-500">
          Don&apos;t have an account?{' '}
          <span className="text-emerald-400 cursor-pointer hover:text-emerald-300">
            Contact sales
          </span>
        </p>
      </div>
    </div>
  )
}
