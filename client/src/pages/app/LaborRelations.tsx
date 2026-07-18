import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Badge, Button, Card, Input, Modal, PillTabs, Select, Textarea } from '../../components/ui'
import { Handshake, Plus, Loader2, AlertTriangle, FileText, CalendarClock } from 'lucide-react'
import { api } from '../../api/client'
import { laborApi } from '../../api/hr/laborClient'
import type { CBA, Grievance, GrievanceDashboard, GrievanceType } from '../../api/hr/laborClient'
import {
  CBA_STATUS_VARIANT, GRIEVANCE_STATUS_LABEL, GRIEVANCE_STATUS_VARIANT,
  GRIEVANCE_TYPE_OPTIONS, personName,
} from '../../data/laborLabels'

type EmployeeRow = { id: string; first_name: string | null; last_name: string | null }
type Tab = 'grievances' | 'cbas'

export default function LaborRelations() {
  const navigate = useNavigate()
  const [tab, setTab] = useState<Tab>('grievances')
  const [dashboard, setDashboard] = useState<GrievanceDashboard | null>(null)
  const [grievances, setGrievances] = useState<Grievance[]>([])
  const [cbas, setCbas] = useState<CBA[]>([])
  const [employees, setEmployees] = useState<EmployeeRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showNewGrievance, setShowNewGrievance] = useState(false)
  const [showNewCba, setShowNewCba] = useState(false)

  async function load() {
    setLoading(true)
    try {
      const [dash, gr, cb] = await Promise.all([
        laborApi.dashboard(),
        laborApi.listGrievances(),
        laborApi.listCbas(),
      ])
      setDashboard(dash)
      setGrievances(gr.grievances)
      setCbas(cb.cbas)
    } catch {
      setError('Failed to load labor relations data.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])
  useEffect(() => {
    api.get<EmployeeRow[]>('/employees').then(setEmployees).catch(() => setEmployees([]))
  }, [])

  if (loading) {
    return <div className="flex justify-center py-20"><Loader2 className="w-6 h-6 animate-spin text-zinc-500" /></div>
  }

  const overdue = dashboard?.overdue ?? []
  const expiring = dashboard?.expiring_cbas ?? []

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-zinc-100">
            <Handshake className="w-5 h-5" />
            Labor Relations
          </h1>
          <p className="text-sm text-zinc-500 mt-1">
            Manage collective bargaining agreements, grievances, and contractual deadlines.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={() => setShowNewCba(true)}>
            <FileText className="w-4 h-4" /><span className="ml-2">New CBA</span>
          </Button>
          <Button onClick={() => setShowNewGrievance(true)}>
            <Plus className="w-4 h-4" /><span className="ml-2">New grievance</span>
          </Button>
        </div>
      </div>

      {error && <Card className="p-4 border border-red-900/50 text-sm text-red-300">{error}</Card>}

      {(overdue.length > 0 || expiring.length > 0) && (
        <div className="grid sm:grid-cols-2 gap-3">
          {overdue.length > 0 && (
            <Card className="p-4 border border-amber-900/50">
              <div className="flex items-center gap-2 text-amber-300 text-sm font-medium">
                <AlertTriangle className="w-4 h-4" /> {overdue.length} grievance step(s) past deadline
              </div>
              <ul className="mt-2 space-y-1">
                {overdue.slice(0, 4).map((o) => (
                  <li key={o.id}>
                    <button
                      className="text-xs text-zinc-400 hover:text-zinc-200"
                      onClick={() => navigate(`/app/labor/grievances/${o.id}`)}
                    >
                      {o.grievance_number} · {o.step_name} · due {o.deadline_to_respond}
                    </button>
                  </li>
                ))}
              </ul>
            </Card>
          )}
          {expiring.length > 0 && (
            <Card className="p-4 border border-amber-900/50">
              <div className="flex items-center gap-2 text-amber-300 text-sm font-medium">
                <CalendarClock className="w-4 h-4" /> {expiring.length} CBA(s) approaching expiration
              </div>
              <ul className="mt-2 space-y-1">
                {expiring.slice(0, 4).map((c) => (
                  <li key={c.id}>
                    <button
                      className="text-xs text-zinc-400 hover:text-zinc-200"
                      onClick={() => navigate(`/app/labor/cbas/${c.id}`)}
                    >
                      {c.union_name} · expires {c.expiration_date}
                    </button>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      )}

      <PillTabs<Tab>
        value={tab}
        onChange={setTab}
        options={[
          { value: 'grievances', label: `Grievances (${grievances.length})` },
          { value: 'cbas', label: `CBAs (${cbas.length})` },
        ]}
      />

      {tab === 'grievances' ? (
        <GrievanceTable grievances={grievances} onOpen={(id) => navigate(`/app/labor/grievances/${id}`)} />
      ) : (
        <CbaTable cbas={cbas} onOpen={(id) => navigate(`/app/labor/cbas/${id}`)} />
      )}

      {showNewGrievance && (
        <NewGrievanceModal
          cbas={cbas}
          employees={employees}
          onClose={() => setShowNewGrievance(false)}
          onCreated={(id) => navigate(`/app/labor/grievances/${id}`)}
        />
      )}
      {showNewCba && (
        <NewCbaModal onClose={() => setShowNewCba(false)} onCreated={(id) => navigate(`/app/labor/cbas/${id}`)} />
      )}
    </div>
  )
}

function GrievanceTable({ grievances, onOpen }: { grievances: Grievance[]; onOpen: (id: string) => void }) {
  if (grievances.length === 0) {
    return <Card className="p-8 text-center text-sm text-zinc-500">No grievances yet.</Card>
  }
  return (
    <Card className="divide-y divide-zinc-800">
      {grievances.map((g) => (
        <button
          key={g.id}
          onClick={() => onOpen(g.id)}
          className="w-full flex items-center justify-between gap-4 px-4 py-3 text-left hover:bg-zinc-900/50"
        >
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono text-zinc-500">{g.grievance_number}</span>
              <span className="text-sm text-zinc-200 truncate">{g.title}</span>
            </div>
            <div className="text-xs text-zinc-500 mt-0.5">
              {personName({ first_name: g.grievant_first_name, last_name: g.grievant_last_name }, 'Class / unassigned')}
              {g.grievance_type ? ` · ${g.grievance_type.replace(/_/g, ' ')}` : ''} · step {g.current_step}
            </div>
          </div>
          <Badge variant={GRIEVANCE_STATUS_VARIANT[g.status]}>{GRIEVANCE_STATUS_LABEL[g.status]}</Badge>
        </button>
      ))}
    </Card>
  )
}

function CbaTable({ cbas, onOpen }: { cbas: CBA[]; onOpen: (id: string) => void }) {
  if (cbas.length === 0) {
    return <Card className="p-8 text-center text-sm text-zinc-500">No CBAs on file. Upload your first agreement.</Card>
  }
  return (
    <Card className="divide-y divide-zinc-800">
      {cbas.map((c) => (
        <button
          key={c.id}
          onClick={() => onOpen(c.id)}
          className="w-full flex items-center justify-between gap-4 px-4 py-3 text-left hover:bg-zinc-900/50"
        >
          <div className="min-w-0">
            <div className="text-sm text-zinc-200 truncate">
              {c.union_name}{c.union_local ? ` · ${c.union_local}` : ''}
            </div>
            <div className="text-xs text-zinc-500 mt-0.5">
              {c.effective_date ? `Effective ${c.effective_date}` : 'No dates'}
              {c.expiration_date ? ` – ${c.expiration_date}` : ''}
              {c.document_filename ? ' · document on file' : ' · no document'}
            </div>
          </div>
          <Badge variant={CBA_STATUS_VARIANT[c.status]}>{c.status.replace(/_/g, ' ')}</Badge>
        </button>
      ))}
    </Card>
  )
}

function NewGrievanceModal({
  cbas, employees, onClose, onCreated,
}: {
  cbas: CBA[]
  employees: EmployeeRow[]
  onClose: () => void
  onCreated: (id: string) => void
}) {
  const [title, setTitle] = useState('')
  const [type, setType] = useState<GrievanceType | ''>('')
  const [cbaId, setCbaId] = useState('')
  const [grievant, setGrievant] = useState('')
  const [steward, setSteward] = useState('')
  const [incidentDate, setIncidentDate] = useState('')
  const [description, setDescription] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  async function submit() {
    if (!title.trim()) { setErr('Title is required.'); return }
    setSaving(true); setErr('')
    try {
      const g = await laborApi.createGrievance({
        title: title.trim(),
        grievance_type: type || undefined,
        cba_id: cbaId || undefined,
        grievant_employee_id: grievant || undefined,
        steward_name_external: steward || undefined,
        incident_date: incidentDate || undefined,
        description: description || undefined,
      })
      onCreated(g.id)
    } catch {
      setErr('Could not create grievance.')
      setSaving(false)
    }
  }

  return (
    <Modal open onClose={onClose} title="New grievance">
      <div className="space-y-3">
        <Input label="Title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Improper overtime assignment" />
        <Select label="Type" value={type} onChange={(e) => setType(e.target.value as GrievanceType)}
          options={[{ value: '', label: 'Select type…' }, ...GRIEVANCE_TYPE_OPTIONS]} />
        <Select label="CBA" value={cbaId} onChange={(e) => setCbaId(e.target.value)}
          options={[{ value: '', label: 'No CBA / default procedure' },
            ...cbas.map((c) => ({ value: c.id, label: c.union_name }))]} />
        <Select label="Grievant (optional)" value={grievant} onChange={(e) => setGrievant(e.target.value)}
          options={[{ value: '', label: 'Class grievance / unassigned' },
            ...employees.map((e) => ({ value: e.id, label: personName(e, e.id.slice(0, 8)) }))]} />
        <Input label="Steward (if not an employee)" value={steward} onChange={(e) => setSteward(e.target.value)} />
        <Input label="Incident date" type="date" value={incidentDate} onChange={(e) => setIncidentDate(e.target.value)} />
        <Textarea label="Description" value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
        {err && <p className="text-sm text-red-400">{err}</p>}
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} disabled={saving}>
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Create'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function NewCbaModal({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const [unionName, setUnionName] = useState('')
  const [unionLocal, setUnionLocal] = useState('')
  const [effective, setEffective] = useState('')
  const [expiration, setExpiration] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  async function submit() {
    if (!unionName.trim()) { setErr('Union name is required.'); return }
    setSaving(true); setErr('')
    try {
      const c = await laborApi.createCba({
        union_name: unionName.trim(),
        union_local: unionLocal || undefined,
        effective_date: effective || undefined,
        expiration_date: expiration || undefined,
      })
      onCreated(c.id)
    } catch {
      setErr('Could not create CBA.')
      setSaving(false)
    }
  }

  return (
    <Modal open onClose={onClose} title="New CBA">
      <div className="space-y-3">
        <Input label="Union name" value={unionName} onChange={(e) => setUnionName(e.target.value)} placeholder="e.g. SEIU" />
        <Input label="Local" value={unionLocal} onChange={(e) => setUnionLocal(e.target.value)} placeholder="e.g. Local 1199" />
        <Input label="Effective date" type="date" value={effective} onChange={(e) => setEffective(e.target.value)} />
        <Input label="Expiration date" type="date" value={expiration} onChange={(e) => setExpiration(e.target.value)} />
        {err && <p className="text-sm text-red-400">{err}</p>}
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} disabled={saving}>
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Create'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
