import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '../components/ui'
import { Input } from '../components/ui'
import { Logo } from '../components/ui'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const navigate = useNavigate()

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    // TODO: wire to /api/auth/login
    navigate('/admin')
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
          <Button type="submit" className="w-full">
            Sign in
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
