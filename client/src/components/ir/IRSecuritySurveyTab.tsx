import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { Badge, Button, Select } from '../ui'
import { CheckCircle2, XCircle, MinusCircle, Plus, ChevronLeft, Loader2, ShieldCheck } from 'lucide-react'

type ResponseVal = 'yes' | 'no' | 'na'
type Responses = Record<string, ResponseVal>

interface Question {
  id: string
  text: string
}

interface Category {
  id: string
  label: string
  questions: Question[]
}

const SURVEY_CATEGORIES: Category[] = [
  {
    id: 'physical',
    label: 'Physical Security',
    questions: [
      { id: 'p1', text: 'Exterior lighting is adequate at all entrances and parking areas' },
      { id: 'p2', text: 'Security cameras are installed and operational' },
      { id: 'p3', text: 'Access control system is in place (key cards, codes, or similar)' },
      { id: 'p4', text: 'All exterior doors have functioning, secure locks' },
      { id: 'p5', text: 'Visitor sign-in/sign-out procedure is enforced' },
    ],
  },
  {
    id: 'emergency',
    label: 'Emergency Preparedness',
    questions: [
      { id: 'e1', text: 'Evacuation plan is posted in multiple visible locations' },
      { id: 'e2', text: 'Emergency contact list is accessible to all employees' },
      { id: 'e3', text: 'First aid kits are fully stocked and accessible' },
      { id: 'e4', text: 'Fire extinguishers are inspected, current, and accessible' },
      { id: 'e5', text: 'All emergency exits are clearly marked and unobstructed' },
    ],
  },
  {
    id: 'violence',
    label: 'Workplace Violence Prevention',
    questions: [
      { id: 'v1', text: 'Written workplace violence prevention policy exists and is communicated to staff' },
      { id: 'v2', text: 'Employees have received workplace violence prevention training in the past year' },
      { id: 'v3', text: 'Clear, accessible process exists for reporting threats or suspicious behavior' },
      { id: 'v4', text: 'Panic button or emergency notification system is available and tested regularly' },
    ],
  },
  {
    id: 'environment',
    label: 'Environmental Safety',
    questions: [
      { id: 'n1', text: 'Floors and walkways are free of hazards (spills, cables, clutter)' },
      { id: 'n2', text: 'Equipment safety guards are in place and functioning' },
      { id: 'n3', text: 'Hazardous materials are properly stored, labeled, and inventoried' },
      { id: 'n4', text: 'Adequate PPE is available and accessible for all required tasks' },
    ],
  },
  {
    id: 'culture',
    label: 'Security Culture',
    questions: [
      { id: 'c1', text: 'Employees feel comfortable reporting safety concerns without fear of retaliation' },
      { id: 'c2', text: 'Near-miss incidents are consistently reported, reviewed, and documented' },
      { id: 'c3', text: 'Regular security walkthroughs or inspections are conducted' },
      { id: 'c4', text: 'Previous security incidents have been reviewed and corrective actions implemented' },
    ],
  },
]

const ALL_QUESTIONS = SURVEY_CATEGORIES.flatMap((c) => c.questions)
const TOTAL_QUESTIONS = ALL_QUESTIONS.length

type LocationRow = {
  id: string
  name: string | null
  city: string
  state: string
}

type SurveyRecord = {
  id: string
  location_id: string | null
  location_name: string | null
  conducted_at: string
  score: number | null
  notes: string | null
  responses: Responses
}

function calcScore(responses: Responses): number | null {
  const applicable = ALL_QUESTIONS.filter((q) => responses[q.id] !== 'na')
  if (applicable.length === 0) return null
  const yes = applicable.filter((q) => responses[q.id] === 'yes').length
  return Math.round((yes / applicable.length) * 100)
}

function calcCategoryScore(cat: Category, responses: Responses): number | null {
  const applicable = cat.questions.filter((q) => responses[q.id] !== 'na')
  if (applicable.length === 0) return null
  const yes = applicable.filter((q) => responses[q.id] === 'yes').length
  return Math.round((yes / applicable.length) * 100)
}

function scoreVariant(score: number | null): 'success' | 'warning' | 'danger' | 'neutral' {
  if (score === null) return 'neutral'
  if (score >= 80) return 'success'
  if (score >= 60) return 'warning'
  return 'danger'
}

function scoreLabel(score: number | null): string {
  if (score === null) return 'N/A'
  if (score >= 80) return 'Good'
  if (score >= 60) return 'Fair'
  return 'Needs Attention'
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatLocationLabel(loc: LocationRow): string {
  const name = (loc.name || '').trim()
  const place = [loc.city, loc.state].filter(Boolean).join(', ')
  if (name && place) return `${name} — ${place}`
  return name || place || loc.id.slice(0, 8)
}

function ResponseToggle({
  value,
  onChange,
}: {
  value: ResponseVal | undefined
  onChange: (v: ResponseVal) => void
}) {
  return (
    <div className="flex items-center gap-1 shrink-0">
      {(['yes', 'no', 'na'] as ResponseVal[]).map((v) => {
        const active = value === v
        const labels: Record<ResponseVal, string> = { yes: 'Yes', no: 'No', na: 'N/A' }
        const activeClass: Record<ResponseVal, string> = {
          yes: 'bg-emerald-900/60 text-emerald-300 border-emerald-700',
          no: 'bg-red-900/60 text-red-300 border-red-700',
          na: 'bg-zinc-700 text-zinc-300 border-zinc-600',
        }
        return (
          <button
            key={v}
            onClick={() => onChange(v)}
            className={`text-xs px-2.5 py-1 rounded border transition-colors font-medium ${
              active ? activeClass[v] : 'border-zinc-700 text-zinc-500 hover:text-zinc-300 hover:border-zinc-600'
            }`}
          >
            {labels[v]}
          </button>
        )
      })}
    </div>
  )
}

type View = 'list' | 'new' | 'detail'

export function IRSecuritySurveyTab() {
  const [view, setView] = useState<View>('list')
  const [surveys, setSurveys] = useState<SurveyRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [locations, setLocations] = useState<LocationRow[]>([])

  // New survey state
  const [selectedLocation, setSelectedLocation] = useState<string>('')
  const [responses, setResponses] = useState<Responses>({})
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  // Detail view
  const [detailSurvey, setDetailSurvey] = useState<SurveyRecord | null>(null)

  useEffect(() => {
    api.get<LocationRow[]>('/ir-onboarding/locations')
      .then((rows) => setLocations(rows || []))
      .catch(() => setLocations([]))
  }, [])

  const loadSurveys = () => {
    setLoading(true)
    api.get<SurveyRecord[]>('/ir/surveys')
      .then((rows) => setSurveys(rows || []))
      .catch(() => setSurveys([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadSurveys() }, [])

  const answeredCount = ALL_QUESTIONS.filter((q) => responses[q.id] !== undefined).length
  const score = calcScore(responses)

  async function handleSave() {
    setSaving(true)
    setSaveError(null)
    try {
      await api.post('/ir/surveys', {
        location_id: selectedLocation || null,
        responses,
        notes: notes || null,
        score,
      })
      loadSurveys()
      setView('list')
      setResponses({})
      setNotes('')
      setSelectedLocation('')
    } catch {
      setSaveError('Failed to save survey. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  function startNew() {
    setResponses({})
    setNotes('')
    setSelectedLocation('')
    setSaveError(null)
    setView('new')
  }

  function openDetail(s: SurveyRecord) {
    setDetailSurvey(s)
    setView('detail')
  }

  // --- List view ---
  if (view === 'list') {
    return (
      <div className="space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-medium text-zinc-100">Security Surveys</h3>
            <p className="text-xs text-zinc-500 mt-0.5">Assess workplace security posture across {TOTAL_QUESTIONS} checkpoints</p>
          </div>
          <Button size="sm" onClick={startNew}>
            <Plus className="w-3.5 h-3.5 mr-1.5" />
            New Survey
          </Button>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 text-zinc-500 text-sm py-8">
            <Loader2 className="w-4 h-4 animate-spin" />
            Loading surveys...
          </div>
        ) : surveys.length === 0 ? (
          <div className="rounded-xl border border-zinc-800 py-14 flex flex-col items-center gap-3 text-center">
            <ShieldCheck className="w-8 h-8 text-zinc-600" />
            <p className="text-sm text-zinc-400 font-medium">No surveys yet</p>
            <p className="text-xs text-zinc-600 max-w-xs">Run your first security survey to assess your workplace safety posture and identify gaps.</p>
            <Button size="sm" onClick={startNew} className="mt-1">
              <Plus className="w-3.5 h-3.5 mr-1.5" />
              Start First Survey
            </Button>
          </div>
        ) : (
          <div className="rounded-xl border border-zinc-800 overflow-hidden">
            <table className="w-full text-sm text-left">
              <thead className="bg-zinc-900/50 text-zinc-400">
                <tr>
                  <th className="px-4 py-3 font-medium">Date</th>
                  <th className="px-4 py-3 font-medium">Location</th>
                  <th className="px-4 py-3 font-medium">Score</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800">
                {surveys.map((s) => (
                  <tr key={s.id} className="text-zinc-300 hover:bg-zinc-900/30 transition-colors">
                    <td className="px-4 py-3 text-zinc-400 text-xs">{formatDate(s.conducted_at)}</td>
                    <td className="px-4 py-3">{s.location_name || <span className="text-zinc-500 italic">All locations</span>}</td>
                    <td className="px-4 py-3 font-semibold">{s.score !== null ? `${s.score}%` : '—'}</td>
                    <td className="px-4 py-3">
                      <Badge variant={scoreVariant(s.score)}>{scoreLabel(s.score)}</Badge>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Button variant="ghost" size="sm" onClick={() => openDetail(s)}>View</Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    )
  }

  // --- Detail view ---
  if (view === 'detail' && detailSurvey) {
    const s = detailSurvey
    const actionItems = ALL_QUESTIONS.filter((q) => s.responses[q.id] === 'no')
    return (
      <div className="space-y-5">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => setView('list')}>
            <ChevronLeft className="w-3.5 h-3.5 mr-1" />
            Back
          </Button>
          <div>
            <h3 className="text-sm font-medium text-zinc-100">Survey — {formatDate(s.conducted_at)}</h3>
            {s.location_name && <p className="text-xs text-zinc-500">{s.location_name}</p>}
          </div>
        </div>

        {/* Score summary */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          {SURVEY_CATEGORIES.map((cat) => {
            const catScore = calcCategoryScore(cat, s.responses)
            return (
              <div key={cat.id} className="border border-zinc-800 rounded-lg px-3 py-3 text-center">
                <p className="text-lg font-semibold text-zinc-100">{catScore !== null ? `${catScore}%` : 'N/A'}</p>
                <p className="text-[10px] text-zinc-500 uppercase tracking-wide mt-0.5 leading-tight">{cat.label}</p>
              </div>
            )
          })}
        </div>

        <div className="border border-zinc-800 rounded-lg px-4 py-3 flex items-center gap-3">
          <div className="flex-1">
            <p className="text-xs text-zinc-500 uppercase tracking-wide">Overall Score</p>
            <p className="text-2xl font-bold text-zinc-100 mt-0.5">{s.score !== null ? `${s.score}%` : 'N/A'}</p>
          </div>
          <Badge variant={scoreVariant(s.score)} className="text-sm px-3 py-1">{scoreLabel(s.score)}</Badge>
        </div>

        {/* Action items */}
        {actionItems.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Action Items ({actionItems.length})</h4>
            <div className="space-y-1.5">
              {actionItems.map((q) => (
                <div key={q.id} className="flex items-start gap-2.5 bg-red-950/20 border border-red-900/30 rounded-lg px-3 py-2.5">
                  <XCircle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
                  <p className="text-sm text-zinc-300">{q.text}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Full responses by category */}
        <div className="space-y-4">
          {SURVEY_CATEGORIES.map((cat) => (
            <div key={cat.id} className="border border-zinc-800 rounded-xl overflow-hidden">
              <div className="bg-zinc-900/50 px-4 py-2.5 flex items-center justify-between">
                <p className="text-xs font-medium text-zinc-300 uppercase tracking-wide">{cat.label}</p>
                {(() => {
                  const cs = calcCategoryScore(cat, s.responses)
                  return <Badge variant={scoreVariant(cs)}>{cs !== null ? `${cs}%` : 'N/A'}</Badge>
                })()}
              </div>
              <div className="divide-y divide-zinc-800/50">
                {cat.questions.map((q) => {
                  const r = s.responses[q.id]
                  return (
                    <div key={q.id} className="flex items-center justify-between gap-4 px-4 py-3">
                      <p className="text-sm text-zinc-300">{q.text}</p>
                      <div className="shrink-0">
                        {r === 'yes' && <span className="flex items-center gap-1 text-xs text-emerald-400 font-medium"><CheckCircle2 className="w-3.5 h-3.5" />Yes</span>}
                        {r === 'no' && <span className="flex items-center gap-1 text-xs text-red-400 font-medium"><XCircle className="w-3.5 h-3.5" />No</span>}
                        {r === 'na' && <span className="flex items-center gap-1 text-xs text-zinc-500 font-medium"><MinusCircle className="w-3.5 h-3.5" />N/A</span>}
                        {!r && <span className="text-xs text-zinc-600 italic">Not answered</span>}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>

        {s.notes && (
          <div className="border border-zinc-800 rounded-lg px-4 py-3">
            <p className="text-xs text-zinc-500 mb-1">Notes</p>
            <p className="text-sm text-zinc-300">{s.notes}</p>
          </div>
        )}
      </div>
    )
  }

  // --- New survey form ---
  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={() => setView('list')}>
          <ChevronLeft className="w-3.5 h-3.5 mr-1" />
          Back
        </Button>
        <div>
          <h3 className="text-sm font-medium text-zinc-100">New Security Survey</h3>
          <p className="text-xs text-zinc-500">{answeredCount} of {TOTAL_QUESTIONS} answered{score !== null ? ` · Score: ${score}%` : ''}</p>
        </div>
      </div>

      {/* Location selector */}
      {locations.length > 0 && (
        <div className="max-w-sm">
          <Select
            label="Location (optional)"
            value={selectedLocation}
            onChange={(e) => setSelectedLocation(e.target.value)}
            options={[
              { value: '', label: 'All locations' },
              ...locations.map((l) => ({ value: l.id, label: formatLocationLabel(l) })),
            ]}
          />
        </div>
      )}

      {/* Progress bar */}
      <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <div
          className="h-full bg-emerald-600 rounded-full transition-all"
          style={{ width: `${TOTAL_QUESTIONS > 0 ? (answeredCount / TOTAL_QUESTIONS) * 100 : 0}%` }}
        />
      </div>

      {/* Questions by category */}
      <div className="space-y-4">
        {SURVEY_CATEGORIES.map((cat) => (
          <div key={cat.id} className="border border-zinc-800 rounded-xl overflow-hidden">
            <div className="bg-zinc-900/50 px-4 py-2.5 flex items-center justify-between">
              <p className="text-xs font-medium text-zinc-300 uppercase tracking-wide">{cat.label}</p>
              {(() => {
                const cs = calcCategoryScore(cat, responses)
                return cs !== null ? <Badge variant={scoreVariant(cs)}>{cs}%</Badge> : null
              })()}
            </div>
            <div className="divide-y divide-zinc-800/50">
              {cat.questions.map((q) => (
                <div key={q.id} className="flex items-center justify-between gap-4 px-4 py-3">
                  <p className="text-sm text-zinc-300 leading-snug">{q.text}</p>
                  <ResponseToggle
                    value={responses[q.id]}
                    onChange={(v) => setResponses((prev) => ({ ...prev, [q.id]: v }))}
                  />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Notes */}
      <div>
        <label className="block text-xs text-zinc-400 mb-1.5">Notes (optional)</label>
        <textarea
          className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 resize-none"
          rows={3}
          placeholder="Add any additional observations or context..."
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </div>

      {saveError && <p className="text-sm text-red-400">{saveError}</p>}

      <div className="flex items-center gap-3 pb-4">
        <Button
          onClick={handleSave}
          disabled={answeredCount === 0 || saving}
        >
          {saving ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
          Save Survey
        </Button>
        <Button variant="ghost" onClick={() => setView('list')}>Cancel</Button>
        {score !== null && (
          <div className="ml-auto flex items-center gap-2">
            <span className="text-sm text-zinc-400">Current score:</span>
            <Badge variant={scoreVariant(score)}>{score}% — {scoreLabel(score)}</Badge>
          </div>
        )}
      </div>
    </div>
  )
}
