import { useEffect, useState, useRef } from 'react'
import { Building2, Plus, Loader2, Send, AlertCircle, FileCheck, Upload, X, MapPin } from 'lucide-react'
import { Button, Input, Modal, Badge } from '../../components/ui'
import { api } from '../../api/client'
import { createBatchClientSetups } from '../../api/broker'
import type { BrokerBatchCreateResponse } from '../../types/broker'

type ClientSetup = {
  id: string
  company_name: string
  contact_name: string | null
  contact_email: string | null
  status: string
  invite_token: string | null
  invite_expires_at: string | null
  created_at: string
  notes?: string
  locations?: { city: string; state: string; type: string }[]
  onboarding_stage?: 'submitted' | 'under_review' | 'configuring' | 'live'
}

type LocationEntry = { city: string; state: string; type: string }

function BrokerTermsGate({ onAccepted }: { onAccepted: () => void }) {
  const [accepting, setAccepting] = useState(false)
  const [agreed, setAgreed] = useState(false)
  const [error, setError] = useState('')

  async function handleAccept() {
    setAccepting(true)
    setError('')
    try {
      await api.post('/auth/broker/accept-terms', {})
      onAccepted()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to accept terms')
    } finally {
      setAccepting(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto py-8 px-4">
      <div className="flex items-center gap-3 mb-4">
        <FileCheck className="h-8 w-8 text-emerald-500" />
        <h2 className="text-lg font-semibold text-zinc-100">Broker Partner Terms of Service</h2>
      </div>
      <p className="text-sm text-zinc-400 mb-4">
        Please review the following terms before managing clients on the Matcha platform.
      </p>

      <div className="border border-zinc-700 rounded-lg bg-zinc-900/60 p-5 mb-5 max-h-80 overflow-y-auto text-sm text-zinc-300 leading-relaxed space-y-3">
        <p className="font-medium text-zinc-200">1. Scope of Services</p>
        <p>As a Matcha broker partner, you may refer client companies to the Matcha platform, assist with their onboarding, and access compliance and HR data for companies under your management. You act as an intermediary — Matcha's contractual relationship is with each client company directly.</p>

        <p className="font-medium text-zinc-200">2. Data Privacy &amp; Confidentiality</p>
        <p>You will have access to sensitive employee and company data for your referred clients. You agree to keep all client data confidential, use it only for the purposes of providing brokerage services, and comply with all applicable data protection regulations including CCPA and any state-specific privacy laws.</p>

        <p className="font-medium text-zinc-200">3. Client Relationship</p>
        <p>You may onboard clients by creating client setups and sending invitations. You must obtain proper authorization from each client company before accessing their data. Matcha reserves the right to revoke broker access to any client account if the client requests it.</p>

        <p className="font-medium text-zinc-200">4. Compliance Obligations</p>
        <p>You agree not to misrepresent Matcha's services, alter compliance recommendations, or provide legal advice to clients. Compliance data and policy suggestions provided through the platform are informational and do not constitute legal counsel.</p>

        <p className="font-medium text-zinc-200">5. Termination</p>
        <p>Either party may terminate this broker partnership at any time. Upon termination, your access to client data through the platform will be revoked. Existing client relationships with Matcha will continue independently.</p>
      </div>

      <div className="flex items-start gap-2 mb-4">
        <input
          type="checkbox"
          id="agree-terms"
          checked={agreed}
          onChange={(e) => setAgreed(e.target.checked)}
          className="mt-0.5 rounded border-zinc-600 bg-zinc-800 text-emerald-600 focus:ring-emerald-500"
        />
        <label htmlFor="agree-terms" className="text-sm text-zinc-400">
          I have read and agree to the Matcha Broker Partner Terms of Service
        </label>
      </div>

      {error && <p className="text-sm text-red-400 mb-4">{error}</p>}
      <Button size="sm" onClick={handleAccept} disabled={accepting || !agreed}>
        {accepting ? 'Accepting...' : 'Accept Terms & Continue'}
      </Button>
    </div>
  )
}

type SetupForm = {
  company_name: string
  contact_name: string
  contact_email: string
  contact_phone: string
  industry: string
  company_size: string
  headcount: string
  invite_immediately: boolean
  locations: LocationEntry[]
  notes: string
}

const EMPTY_SETUP: SetupForm = {
  company_name: '',
  contact_name: '',
  contact_email: '',
  contact_phone: '',
  industry: '',
  company_size: '',
  headcount: '1',
  invite_immediately: true,
  locations: [],
  notes: '',
}

const EMPTY_LOCATION: LocationEntry = { city: '', state: '', type: 'headquarters' }

const US_STATES = [
  'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA','KS','KY','LA','ME','MD',
  'MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM','NY','NC','ND','OH','OK','OR','PA','RI','SC',
  'SD','TN','TX','UT','VT','VA','WA','WV','WI','WY','DC',
]

const LOCATION_TYPES = ['headquarters', 'branch', 'remote']

const statusBadge = (status: string) => {
  if (status === 'active' || status === 'registered') return <Badge variant="success">{status}</Badge>
  if (status === 'invited' || status === 'pending') return <Badge variant="warning">{status}</Badge>
  if (status === 'expired') return <Badge variant="danger">Expired</Badge>
  return <Badge variant="warning">{status}</Badge>
}

const onboardingStageBadge = (stage?: string) => {
  if (!stage) return <span className="text-zinc-600">—</span>
  const config: Record<string, { dot: string; label: string }> = {
    submitted: { dot: 'bg-zinc-400', label: 'Submitted' },
    under_review: { dot: 'bg-blue-500', label: 'Under Review' },
    configuring: { dot: 'bg-amber-500', label: 'Configuring' },
    live: { dot: 'bg-emerald-500', label: 'Live' },
  }
  const c = config[stage]
  if (!c) return <span className="text-zinc-600">—</span>
  return (
    <span className="flex items-center gap-1.5 text-xs text-zinc-300">
      <span className={`h-2 w-2 rounded-full ${c.dot}`} />
      {c.label}
    </span>
  )
}

function locationSummary(locations?: { city: string; state: string; type: string }[]) {
  if (!locations || locations.length === 0) return null
  if (locations.length === 1) {
    const l = locations[0]
    return `${l.city}${l.state ? ', ' + l.state : ''}`
  }
  return `${locations.length} locations`
}

// --- CSV Upload types ---
type CsvRow = {
  company_name: string
  contact_name: string
  contact_email: string
  contact_phone: string
  industry: string
  company_size: string
  headcount: string
  notes: string
}

function parseCsv(text: string): CsvRow[] {
  const lines = text.split('\n').map((l) => l.trim()).filter(Boolean)
  if (lines.length < 2) return []
  const headers = lines[0].split(',').map((h) => h.trim().toLowerCase().replace(/\s+/g, '_'))
  return lines.slice(1).map((line) => {
    const values: string[] = []
    let current = ''
    let inQuotes = false
    for (const ch of line) {
      if (ch === '"') { inQuotes = !inQuotes; continue }
      if (ch === ',' && !inQuotes) { values.push(current.trim()); current = ''; continue }
      current += ch
    }
    values.push(current.trim())
    const row: any = {}
    headers.forEach((h, i) => { row[h] = values[i] || '' })
    return {
      company_name: row.company_name || '',
      contact_name: row.contact_name || '',
      contact_email: row.contact_email || '',
      contact_phone: row.contact_phone || '',
      industry: row.industry || '',
      company_size: row.company_size || '',
      headcount: row.headcount || '',
      notes: row.notes || '',
    } as CsvRow
  })
}

export default function BrokerClients() {
  const [setups, setSetups] = useState<ClientSetup[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [needsTerms, setNeedsTerms] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState<SetupForm>(EMPTY_SETUP)
  const [saving, setSaving] = useState(false)
  const [addError, setAddError] = useState('')
  const [sendingInvite, setSendingInvite] = useState<string | null>(null)

  // CSV upload state
  const [showCsvUpload, setShowCsvUpload] = useState(false)
  const [csvRows, setCsvRows] = useState<CsvRow[]>([])
  const [csvFile, setCsvFile] = useState<File | null>(null)
  const [csvSubmitting, setCsvSubmitting] = useState(false)
  const [csvResult, setCsvResult] = useState<BrokerBatchCreateResponse | null>(null)
  const [csvError, setCsvError] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  function fetchSetups() {
    setLoading(true)
    setNeedsTerms(false)
    api.get<{ setups: ClientSetup[] }>('/brokers/client-setups')
      .then((res) => setSetups(res.setups))
      .catch((err) => {
        const msg = err instanceof Error ? err.message : ''
        if (msg.toLowerCase().includes('terms')) {
          setNeedsTerms(true)
        } else {
          setError('Unable to load client setups')
        }
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchSetups() }, [])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setAddError('')
    setSaving(true)
    try {
      await api.post('/brokers/client-setups', {
        company_name: form.company_name.trim(),
        contact_name: form.contact_name.trim() || undefined,
        contact_email: form.contact_email.trim() || undefined,
        contact_phone: form.contact_phone.trim() || undefined,
        industry: form.industry.trim() || undefined,
        company_size: form.company_size.trim() || undefined,
        headcount: parseInt(form.headcount, 10) || undefined,
        invite_immediately: form.invite_immediately,
        locations: form.locations.length > 0 ? form.locations.filter((l) => l.city || l.state) : undefined,
        notes: form.notes.trim() || undefined,
      })
      setShowAdd(false)
      setForm(EMPTY_SETUP)
      fetchSetups()
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Failed to create client setup')
    } finally {
      setSaving(false)
    }
  }

  async function sendInvite(setupId: string) {
    setSendingInvite(setupId)
    try {
      await api.post(`/brokers/client-setups/${setupId}/invite`, { expires_days: 14 })
      fetchSetups()
    } catch {}
    setSendingInvite(null)
  }

  // Location helpers
  function addLocation() {
    setForm({ ...form, locations: [...form.locations, { ...EMPTY_LOCATION }] })
  }

  function removeLocation(idx: number) {
    setForm({ ...form, locations: form.locations.filter((_, i) => i !== idx) })
  }

  function updateLocation(idx: number, field: keyof LocationEntry, value: string) {
    const locs = [...form.locations]
    locs[idx] = { ...locs[idx], [field]: value }
    setForm({ ...form, locations: locs })
  }

  // CSV handlers
  function handleCsvFile(file: File) {
    setCsvFile(file)
    setCsvResult(null)
    setCsvError('')
    const reader = new FileReader()
    reader.onload = (e) => {
      const text = e.target?.result as string
      const rows = parseCsv(text)
      setCsvRows(rows)
    }
    reader.readAsText(file)
  }

  function handleCsvDrop(e: React.DragEvent) {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file && file.name.endsWith('.csv')) handleCsvFile(file)
  }

  async function submitCsvBatch() {
    setCsvSubmitting(true)
    setCsvError('')
    try {
      const clients = csvRows.map((r) => ({
        company_name: r.company_name,
        contact_name: r.contact_name || undefined,
        contact_email: r.contact_email || undefined,
        contact_phone: r.contact_phone || undefined,
        industry: r.industry || undefined,
        company_size: r.company_size || undefined,
        headcount: parseInt(r.headcount, 10) || undefined,
        notes: r.notes || undefined,
      }))
      const result = await createBatchClientSetups(clients)
      setCsvResult(result)
      fetchSetups()
    } catch (err) {
      setCsvError(err instanceof Error ? err.message : 'Batch upload failed')
    } finally {
      setCsvSubmitting(false)
    }
  }

  function closeCsvModal() {
    setShowCsvUpload(false)
    setCsvRows([])
    setCsvFile(null)
    setCsvResult(null)
    setCsvError('')
  }

  if (needsTerms) {
    return <BrokerTermsGate onAccepted={fetchSetups} />
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 text-zinc-500 animate-spin" />
      </div>
    )
  }

  if (error && setups.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-zinc-500">
        <AlertCircle className="h-8 w-8 mb-2" />
        <p className="text-sm">{error}</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight">Client Onboarding</h1>
          <p className="text-sm text-zinc-500 mt-1">Create and manage client setups for your referred companies.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="ghost" onClick={() => setShowCsvUpload(true)}>
            <Upload size={14} className="mr-1" />
            Upload CSV
          </Button>
          <Button size="sm" onClick={() => setShowAdd(true)}>
            <Plus size={14} className="mr-1" />
            Add Client
          </Button>
        </div>
      </div>

      {setups.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-zinc-500 border border-zinc-800 rounded-xl border-dashed">
          <Building2 className="h-10 w-10 mb-3 text-zinc-600" />
          <p className="text-sm font-medium text-zinc-400">No client setups yet</p>
          <p className="text-xs mt-1">Create a client setup to start onboarding a company.</p>
          <Button size="sm" className="mt-4" onClick={() => setShowAdd(true)}>
            Add Your First Client
          </Button>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-zinc-800">
          <table className="w-full text-sm text-left">
            <thead className="bg-zinc-900/50 text-zinc-400">
              <tr>
                <th className="px-4 py-3 font-medium">Company</th>
                <th className="px-4 py-3 font-medium">Contact</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Onboarding</th>
                <th className="px-4 py-3 font-medium">Created</th>
                <th className="px-4 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {setups.map((s) => {
                const locText = locationSummary(s.locations)
                return (
                  <tr key={s.id} className="text-zinc-300">
                    <td className="px-4 py-3">
                      <p className="font-medium text-zinc-100">{s.company_name}</p>
                      {locText && (
                        <p className="text-xs text-zinc-500 flex items-center gap-1 mt-0.5">
                          <MapPin size={10} />
                          {locText}
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <p className="text-zinc-300">{s.contact_name || '—'}</p>
                      <p className="text-xs text-zinc-500">{s.contact_email || ''}</p>
                    </td>
                    <td className="px-4 py-3">{statusBadge(s.status)}</td>
                    <td className="px-4 py-3">{onboardingStageBadge(s.onboarding_stage)}</td>
                    <td className="px-4 py-3 text-xs text-zinc-500">
                      {new Date(s.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {(s.status === 'draft' || s.status === 'expired') && s.contact_email && (
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={sendingInvite === s.id}
                          onClick={() => sendInvite(s.id)}
                        >
                          <Send size={12} className="mr-1" />
                          {sendingInvite === s.id ? 'Sending...' : 'Send Invite'}
                        </Button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Add Client Setup Modal */}
      <Modal open={showAdd} onClose={() => { setShowAdd(false); setAddError('') }} title="Add Client" width="lg">
        <form onSubmit={handleCreate} className="space-y-4">
          <div>
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium mb-2">Company Info</p>
            <div className="grid grid-cols-2 gap-3">
              <Input
                label="Company Name"
                value={form.company_name}
                onChange={(e) => setForm({ ...form, company_name: e.target.value })}
                required
              />
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Industry</label>
                <select
                  value={form.industry}
                  onChange={(e) => setForm({ ...form, industry: e.target.value })}
                  className="w-full bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
                >
                  <option value="">Select industry...</option>
                  <option value="healthcare">Healthcare</option>
                  <option value="manufacturing">Manufacturing</option>
                  <option value="technology">Technology</option>
                  <option value="retail">Retail</option>
                  <option value="hospitality">Hospitality</option>
                  <option value="construction">Construction</option>
                  <option value="finance">Finance</option>
                  <option value="education">Education</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Company Size</label>
                <select
                  value={form.company_size}
                  onChange={(e) => setForm({ ...form, company_size: e.target.value })}
                  className="w-full bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
                >
                  <option value="">Select size...</option>
                  <option value="1-10">1-10</option>
                  <option value="11-50">11-50</option>
                  <option value="51-200">51-200</option>
                  <option value="201-500">201-500</option>
                  <option value="501-1000">501-1000</option>
                  <option value="1001+">1001+</option>
                </select>
              </div>
              <Input
                label="Headcount"
                type="number"
                value={form.headcount}
                onChange={(e) => setForm({ ...form, headcount: e.target.value })}
              />
            </div>
          </div>

          <div>
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium mb-2">Primary Contact</p>
            <div className="grid grid-cols-2 gap-3">
              <Input
                label="Contact Name"
                value={form.contact_name}
                onChange={(e) => setForm({ ...form, contact_name: e.target.value })}
              />
              <Input
                label="Contact Email"
                type="email"
                value={form.contact_email}
                onChange={(e) => setForm({ ...form, contact_email: e.target.value })}
              />
              <Input
                label="Phone (optional)"
                value={form.contact_phone}
                onChange={(e) => setForm({ ...form, contact_phone: e.target.value })}
              />
            </div>
          </div>

          {/* Locations */}
          <div>
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium mb-2">Locations</p>
            {form.locations.length > 0 && (
              <div className="space-y-2 mb-2">
                {form.locations.map((loc, idx) => (
                  <div key={idx} className="flex items-center gap-2">
                    <Input
                      placeholder="City"
                      value={loc.city}
                      onChange={(e) => updateLocation(idx, 'city', e.target.value)}
                      className="flex-1"
                    />
                    <select
                      value={loc.state}
                      onChange={(e) => updateLocation(idx, 'state', e.target.value)}
                      className="bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
                    >
                      <option value="">State...</option>
                      {US_STATES.map((s) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>
                    <select
                      value={loc.type}
                      onChange={(e) => updateLocation(idx, 'type', e.target.value)}
                      className="bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
                    >
                      {LOCATION_TYPES.map((t) => (
                        <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
                      ))}
                    </select>
                    <button
                      type="button"
                      onClick={() => removeLocation(idx)}
                      className="p-1 text-zinc-500 hover:text-red-400 transition-colors"
                    >
                      <X size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
            <button
              type="button"
              onClick={addLocation}
              className="text-xs text-zinc-400 hover:text-zinc-200 transition-colors flex items-center gap-1"
            >
              <Plus size={12} />
              Add Location
            </button>
          </div>

          {/* Notes */}
          <div>
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium mb-2">Notes</p>
            <textarea
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              placeholder="Additional context about this client, special requirements, timeline notes..."
              rows={3}
              className="w-full bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500 resize-none placeholder:text-zinc-600"
            />
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="invite-immediately"
              checked={form.invite_immediately}
              onChange={(e) => setForm({ ...form, invite_immediately: e.target.checked })}
              className="rounded border-zinc-600 bg-zinc-800 text-emerald-600 focus:ring-emerald-500"
            />
            <label htmlFor="invite-immediately" className="text-sm text-zinc-400">
              Send invitation email immediately
            </label>
          </div>

          {addError && <p className="text-sm text-red-400">{addError}</p>}

          <div className="flex items-center gap-2 pt-2 border-t border-zinc-800">
            <Button type="submit" size="sm" disabled={saving || !form.company_name.trim()}>
              {saving ? 'Creating...' : 'Create Client Setup'}
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => { setShowAdd(false); setAddError('') }}>
              Cancel
            </Button>
          </div>
        </form>
      </Modal>

      {/* CSV Upload Modal */}
      <Modal open={showCsvUpload} onClose={closeCsvModal} title="Upload CSV" width="lg">
        <div className="space-y-4">
          {!csvResult ? (
            <>
              {/* Drop zone */}
              <div
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleCsvDrop}
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-zinc-700 rounded-lg p-8 text-center cursor-pointer hover:border-zinc-500 transition-colors"
              >
                <Upload className="h-8 w-8 text-zinc-500 mx-auto mb-2" />
                <p className="text-sm text-zinc-400">
                  {csvFile ? csvFile.name : 'Drop a CSV file here or click to browse'}
                </p>
                <p className="text-xs text-zinc-600 mt-1">
                  Expected columns: company_name, contact_name, contact_email, contact_phone, industry, company_size, headcount, notes
                </p>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0]
                    if (f) handleCsvFile(f)
                  }}
                />
              </div>

              {/* Preview table */}
              {csvRows.length > 0 && (
                <div className="overflow-x-auto max-h-64 overflow-y-auto rounded-lg border border-zinc-800">
                  <table className="w-full text-xs text-left">
                    <thead className="bg-zinc-900/50 text-zinc-400 sticky top-0">
                      <tr>
                        <th className="px-3 py-2 font-medium">#</th>
                        <th className="px-3 py-2 font-medium">Company</th>
                        <th className="px-3 py-2 font-medium">Contact</th>
                        <th className="px-3 py-2 font-medium">Email</th>
                        <th className="px-3 py-2 font-medium">Industry</th>
                        <th className="px-3 py-2 font-medium">Notes</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-800">
                      {csvRows.map((row, i) => {
                        const missing = !row.company_name.trim()
                        return (
                          <tr key={i} className={missing ? 'bg-red-950/30' : 'text-zinc-300'}>
                            <td className="px-3 py-1.5 text-zinc-500 font-[Space_Grotesk]">{i + 1}</td>
                            <td className={`px-3 py-1.5 ${missing ? 'text-red-400' : ''}`}>
                              {row.company_name || '(missing)'}
                            </td>
                            <td className="px-3 py-1.5">{row.contact_name}</td>
                            <td className="px-3 py-1.5">{row.contact_email}</td>
                            <td className="px-3 py-1.5">{row.industry}</td>
                            <td className="px-3 py-1.5 max-w-[120px] truncate">{row.notes}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              {csvError && <p className="text-sm text-red-400">{csvError}</p>}

              <div className="flex items-center gap-2 pt-2 border-t border-zinc-800">
                <Button
                  size="sm"
                  disabled={csvSubmitting || csvRows.length === 0 || csvRows.every((r) => !r.company_name.trim())}
                  onClick={submitCsvBatch}
                >
                  {csvSubmitting ? (
                    <>
                      <Loader2 size={12} className="mr-1 animate-spin" />
                      Submitting...
                    </>
                  ) : (
                    `Submit All (${csvRows.filter((r) => r.company_name.trim()).length} clients)`
                  )}
                </Button>
                <Button type="button" variant="ghost" size="sm" onClick={closeCsvModal}>
                  Cancel
                </Button>
              </div>
            </>
          ) : (
            /* Results view */
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <Badge variant="success">{csvResult.count} created</Badge>
                {csvResult.errors.length > 0 && (
                  <Badge variant="danger">{csvResult.errors.length} errors</Badge>
                )}
              </div>

              {csvResult.errors.length > 0 && (
                <div className="rounded-lg border border-red-900/50 bg-red-950/20 p-3 space-y-1">
                  {csvResult.errors.map((err, i) => (
                    <p key={i} className="text-xs text-red-400">
                      Row {err.index + 1} ({err.company_name}): {err.error}
                    </p>
                  ))}
                </div>
              )}

              <div className="pt-2 border-t border-zinc-800">
                <Button size="sm" onClick={closeCsvModal}>Done</Button>
              </div>
            </div>
          )}
        </div>
      </Modal>
    </div>
  )
}
