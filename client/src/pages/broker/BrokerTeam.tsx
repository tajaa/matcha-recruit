import { useEffect, useState } from 'react'
import { Users, Plus, Loader2, Trash2, Check, ShieldCheck } from 'lucide-react'
import { HelpHint } from '../../components/broker/HelpHint'
import { fetchBrokerMembers, createBrokerMember, deactivateBrokerMember } from '../../api/broker'
import type { BrokerMember, BrokerMemberCreateResponse } from '../../types/broker'

function fmtDate(iso: string | null) {
  if (!iso) return 'Never'
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

const ROLE_LABEL: Record<string, string> = { owner: 'Owner', admin: 'Admin', member: 'Member' }

const inputCls = 'min-w-0 px-3 h-9 rounded-lg text-sm bg-zinc-900/60 border border-zinc-700 text-zinc-100 placeholder-zinc-500 outline-none focus:border-zinc-500 focus:ring-1 focus:ring-zinc-600/50 transition-colors'

export default function BrokerTeam({ embedded = false }: { embedded?: boolean }) {
  const [members, setMembers] = useState<BrokerMember[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<'admin' | 'member'>('member')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [justCreated, setJustCreated] = useState<BrokerMemberCreateResponse | null>(null)

  async function load() {
    try {
      const data = await fetchBrokerMembers()
      setMembers(data.members)
    } catch {
      setError('Failed to load team')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim() || !email.trim()) return
    setCreating(true)
    setCreateError(null)
    setJustCreated(null)
    try {
      const res = await createBrokerMember({ name: name.trim(), email: email.trim().toLowerCase(), role })
      setJustCreated(res)
      setName('')
      setEmail('')
      setRole('member')
      await load()
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Failed to create teammate')
    } finally {
      setCreating(false)
    }
  }

  async function handleDeactivate(member: BrokerMember) {
    try {
      await deactivateBrokerMember(member.id)
      await load()
    } catch {
      load()
    }
  }

  return (
    <div>
      {!embedded && (
        <div className="mb-6">
          <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight text-zinc-100">Team <HelpHint text="Your broker users and their permissions — admins manage clients, seats and the team; members manage clients only. Add or deactivate colleagues here." /></h1>
          <p className="mt-1 text-sm text-zinc-500">
            Add broker users to your account. Admins can manage clients, seats, and the team; members
            manage clients only.
          </p>
        </div>
      )}

      <form onSubmit={handleCreate} className="mb-6 flex max-w-3xl flex-col gap-4 rounded-2xl border border-zinc-800 bg-zinc-900/40 p-5">
        <p className="text-[11px] font-bold uppercase tracking-widest text-zinc-500">Add a teammate</p>
        <div className="flex gap-3 flex-wrap">
          <input
            type="text"
            placeholder="Full name"
            value={name}
            onChange={e => setName(e.target.value)}
            className={`flex-1 ${inputCls}`}
          />
          <input
            type="email"
            placeholder="Work email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            className={`flex-1 ${inputCls}`}
          />
          <button
            type="submit"
            disabled={creating || !name.trim() || !email.trim()}
            className="flex items-center gap-2 px-4 h-9 rounded-lg text-sm font-medium bg-emerald-700 text-white hover:bg-emerald-600 disabled:opacity-50 transition-colors"
          >
            {creating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
            Add
          </button>
        </div>
        <div className="flex flex-col gap-1.5">
          <p className="text-xs text-zinc-500">Role</p>
          <div className="flex gap-2">
            {(['member', 'admin'] as const).map(r => (
              <button
                key={r}
                type="button"
                onClick={() => setRole(r)}
                className="px-3 h-8 rounded-lg text-xs font-medium transition-colors"
                style={role === r
                  ? { backgroundColor: '#15803d', color: '#fff' }
                  : { backgroundColor: 'transparent', border: '1px solid #3f3f46', color: '#71717a' }
                }
              >
                {ROLE_LABEL[r]}
              </button>
            ))}
          </div>
        </div>
        {createError && <p className="text-xs text-red-400">{createError}</p>}
        {justCreated && (
          <div className="flex items-start gap-2 p-3 rounded-lg bg-emerald-950/40 border border-emerald-900/50">
            <Check className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
            <div className="text-xs text-zinc-300">
              <p className="font-medium text-emerald-300">{justCreated.member.email} added.</p>
              {justCreated.email_sent
                ? <p className="text-zinc-400 mt-0.5">Login credentials emailed.</p>
                : <p className="text-zinc-400 mt-0.5">Email delivery unavailable — share this temporary password: <span className="font-mono text-zinc-100">{justCreated.password}</span></p>}
            </div>
          </div>
        )}
      </form>

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-zinc-500">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading…
        </div>
      ) : error ? (
        <p className="text-sm text-red-400">{error}</p>
      ) : (
        <div className="max-w-3xl overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-900/40">
          <div className="border-b border-zinc-800/60 px-4 py-3">
            <span className="text-[11px] font-bold uppercase tracking-widest text-zinc-500">Team members</span>
          </div>
          <div className="divide-y divide-zinc-800/60">
          {members.map(m => (
            <div key={m.id} className="flex items-center justify-between gap-3 px-4 py-3">
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-8 h-8 rounded-full bg-zinc-800 flex items-center justify-center shrink-0">
                  {m.role === 'owner' ? <ShieldCheck className="w-4 h-4 text-emerald-400" /> : <Users className="w-4 h-4 text-zinc-500" />}
                </div>
                <div className="min-w-0">
                  <p className="text-sm text-zinc-200 truncate">
                    {m.email}
                    {m.is_self && <span className="ml-1.5 text-[10px] text-zinc-500">(you)</span>}
                    {!m.is_active && <span className="ml-1.5 text-[10px] text-red-400">deactivated</span>}
                  </p>
                  <p className="text-[11px] text-zinc-600">Last login {fmtDate(m.last_login)}</p>
                </div>
              </div>
              <div className="flex items-center gap-3 shrink-0">
                <span className="text-[10px] px-1.5 py-0.5 rounded font-medium bg-zinc-800 text-zinc-400">
                  {ROLE_LABEL[m.role] ?? m.role}
                </span>
                {m.is_active && m.role !== 'owner' && !m.is_self && (
                  <button
                    onClick={() => handleDeactivate(m)}
                    className="p-1.5 rounded-lg text-zinc-600 hover:text-red-400 hover:bg-zinc-800 transition-colors"
                    title="Deactivate"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>
          ))}
          </div>
        </div>
      )}
    </div>
  )
}
