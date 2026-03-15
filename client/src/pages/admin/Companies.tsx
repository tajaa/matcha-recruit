import { useEffect, useState } from 'react'
import { Badge, Button, Input } from '../../components/ui'
import { api } from '../../api/client'

type Company = {
  id: string
  company_name: string
  industry: string | null
  company_size: string | null
  status: string
  created_at: string
  owner_email: string
  owner_name: string
}

type CompanyListResponse = {
  registrations: Company[]
  total: number
}

const statusBadge = (status: string | null) => {
  if (!status || status === 'approved')
    return <Badge variant="success">Approved</Badge>
  if (status === 'pending')
    return <Badge variant="warning">Pending</Badge>
  return <Badge variant="danger">Rejected</Badge>
}

export default function Companies() {
  const [companies, setCompanies] = useState<Company[]>([])
  const [filter, setFilter] = useState<'all' | 'pending' | 'approved' | 'rejected'>('all')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    const params = filter !== 'all' ? `?status=${filter}` : ''
    api.get<CompanyListResponse>(`/admin/business-registrations${params}`)
      .then((res) => setCompanies(res.registrations))
      .catch(() => setCompanies([]))
      .finally(() => setLoading(false))
  }, [filter])

  const filtered = companies.filter((c) =>
    c.company_name.toLowerCase().includes(search.toLowerCase())
  )

  async function approve(id: string) {
    await api.post(`/admin/business-registrations/${id}/approve`)
    setCompanies((prev) =>
      prev.map((c) => (c.id === id ? { ...c, status: 'approved' } : c))
    )
  }

  async function reject(id: string) {
    const reason = prompt('Rejection reason:')
    if (!reason) return
    await api.post(`/admin/business-registrations/${id}/reject`, { reason })
    setCompanies((prev) =>
      prev.map((c) => (c.id === id ? { ...c, status: 'rejected' } : c))
    )
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold text-zinc-100 font-[Space_Grotesk]">
        Companies
      </h1>
      <p className="mt-2 text-sm text-zinc-500">
        Manage registered businesses and approvals.
      </p>

      {/* Filters */}
      <div className="mt-6 flex items-center gap-3">
        <Input
          label=""
          placeholder="Search companies..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <div className="flex gap-1 ml-auto">
          {(['all', 'pending', 'approved', 'rejected'] as const).map((s) => (
            <Button
              key={s}
              variant={filter === s ? 'primary' : 'ghost'}
              size="sm"
              onClick={() => setFilter(s)}
            >
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </Button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="mt-6">
        {loading ? (
          <p className="text-sm text-zinc-500">Loading...</p>
        ) : filtered.length === 0 ? (
          <p className="text-sm text-zinc-500">No companies found.</p>
        ) : (
          <div className="overflow-hidden rounded-xl border border-zinc-800">
            <table className="w-full text-sm text-left">
              <thead className="bg-zinc-900/50 text-zinc-400">
                <tr>
                  <th className="px-4 py-3 font-medium">Company</th>
                  <th className="px-4 py-3 font-medium">Industry</th>
                  <th className="px-4 py-3 font-medium">Size</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800">
                {filtered.map((c) => (
                  <tr key={c.id} className="text-zinc-300">
                    <td className="px-4 py-3">
                      <p className="font-medium text-zinc-100">{c.company_name}</p>
                      <p className="text-xs text-zinc-500">{c.owner_email}</p>
                    </td>
                    <td className="px-4 py-3">{c.industry ?? '—'}</td>
                    <td className="px-4 py-3">{c.company_size ?? '—'}</td>
                    <td className="px-4 py-3">{statusBadge(c.status)}</td>
                    <td className="px-4 py-3 text-right">
                      {(c.status === 'pending') && (
                        <div className="flex justify-end gap-2">
                          <Button size="sm" onClick={() => approve(c.id)}>
                            Approve
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => reject(c.id)}>
                            Reject
                          </Button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
