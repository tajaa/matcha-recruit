import { useState, useEffect } from 'react'
import { Button, Input, Modal, Textarea } from '../../ui'
import {
  CATEGORY_LABELS,
  CATEGORY_SHORT_LABELS,
  CATEGORY_GROUPS,
  ALL_CATEGORY_KEYS,
  type CategoryGroup,
} from '../../../generated/complianceCategories'
import type { IndustryProfile } from './types'

type Props = {
  open: boolean
  onClose: () => void
  profiles: IndustryProfile[]
  onCreate: (data: Omit<IndustryProfile, 'id' | 'created_at' | 'updated_at'>) => Promise<IndustryProfile>
  onUpdate: (id: string, data: Partial<Omit<IndustryProfile, 'id' | 'created_at' | 'updated_at'>>) => Promise<IndustryProfile>
  onDelete: (id: string) => Promise<void>
}

const RATE_TYPE_OPTIONS = [
  'general', 'tipped', 'exempt_salary', 'hotel', 'fast_food', 'healthcare', 'large_employer', 'small_employer',
]

const GROUP_LABELS: Record<CategoryGroup | 'supplementary', string> = {
  labor: 'Labor',
  healthcare: 'Healthcare',
  oncology: 'Oncology',
  medical_compliance: 'Medical Compliance',
  life_sciences: 'Life Sciences',
  manufacturing: 'Manufacturing',
  supplementary: 'Supplementary',
}

const GROUP_ORDER: (CategoryGroup | 'supplementary')[] = [
  'labor', 'healthcare', 'oncology', 'medical_compliance', 'life_sciences', 'manufacturing', 'supplementary',
]

type EditState = {
  name: string
  description: string
  focused_categories: string[]
  rate_types: string[]
  category_order: string[]
  category_evidence: Record<string, { confidence: number; reason: string }>
}

const EMPTY: EditState = {
  name: '',
  description: '',
  focused_categories: [],
  rate_types: [],
  category_order: [],
  category_evidence: {},
}

export default function ProfileEditorModal({
  open,
  onClose,
  profiles,
  onCreate,
  onUpdate,
  onDelete,
}: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [form, setForm] = useState<EditState>(EMPTY)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [expandedEvidence, setExpandedEvidence] = useState<string | null>(null)

  // Load profile into form when selected
  useEffect(() => {
    setConfirmDelete(false)
    if (!selectedId) {
      setForm(EMPTY)
      return
    }
    const p = profiles.find((pr) => pr.id === selectedId)
    if (p) {
      setForm({
        name: p.name,
        description: p.description || '',
        focused_categories: [...p.focused_categories],
        rate_types: [...p.rate_types],
        category_order: [...p.category_order],
        category_evidence: p.category_evidence ? { ...p.category_evidence } : {},
      })
    }
  }, [selectedId, profiles])

  function toggleCategory(cat: string) {
    setForm((f) => {
      const has = f.focused_categories.includes(cat)
      const focused = has
        ? f.focused_categories.filter((c) => c !== cat)
        : [...f.focused_categories, cat]
      const order = has
        ? f.category_order.filter((c) => c !== cat)
        : [...f.category_order, cat]
      return { ...f, focused_categories: focused, category_order: order }
    })
  }

  function toggleRateType(rt: string) {
    setForm((f) => {
      const has = f.rate_types.includes(rt)
      return {
        ...f,
        rate_types: has ? f.rate_types.filter((r) => r !== rt) : [...f.rate_types, rt],
      }
    })
  }

  function moveCategoryOrder(cat: string, direction: -1 | 1) {
    setForm((f) => {
      const order = [...f.category_order]
      const idx = order.indexOf(cat)
      if (idx < 0) return f
      const targetIdx = idx + direction
      if (targetIdx < 0 || targetIdx >= order.length) return f
      ;[order[idx], order[targetIdx]] = [order[targetIdx], order[idx]]
      return { ...f, category_order: order }
    })
  }

  function updateEvidence(cat: string, field: 'confidence' | 'reason', value: number | string) {
    setForm((f) => ({
      ...f,
      category_evidence: {
        ...f.category_evidence,
        [cat]: {
          confidence: f.category_evidence[cat]?.confidence ?? 0.5,
          reason: f.category_evidence[cat]?.reason ?? '',
          [field]: value,
        },
      },
    }))
  }

  async function handleSave() {
    if (!form.name.trim()) return
    setSaving(true)
    try {
      const data = {
        name: form.name.trim(),
        description: form.description.trim() || null,
        focused_categories: form.focused_categories,
        rate_types: form.rate_types,
        category_order: form.category_order,
        category_evidence: Object.keys(form.category_evidence).length > 0 ? form.category_evidence : null,
      }
      if (selectedId) {
        await onUpdate(selectedId, data)
      } else {
        const created = await onCreate(data)
        setSelectedId(created.id)
      }
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete() {
    if (!selectedId) return
    setDeleting(true)
    try {
      await onDelete(selectedId)
      setSelectedId(null)
    } finally {
      setDeleting(false)
    }
  }

  // Group categories for checkbox grid
  const catsByGroup: Record<string, string[]> = {}
  for (const key of ALL_CATEGORY_KEYS) {
    const g = CATEGORY_GROUPS[key] ?? 'supplementary'
    if (!catsByGroup[g]) catsByGroup[g] = []
    catsByGroup[g].push(key)
  }

  return (
    <Modal open={open} onClose={onClose} title="Industry Profiles" width="xl">
      <div className="flex gap-4 max-h-[70vh]">
        {/* Profile list sidebar */}
        <div className="w-48 shrink-0 border-r border-zinc-800 pr-3 overflow-y-auto">
          <button
            type="button"
            onClick={() => setSelectedId(null)}
            className={`w-full text-left text-xs px-2 py-1.5 rounded mb-1 transition-colors ${
              !selectedId ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:text-zinc-200'
            }`}
          >
            + New Profile
          </button>
          {profiles.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => setSelectedId(p.id)}
              className={`w-full text-left text-xs px-2 py-1.5 rounded mb-0.5 transition-colors truncate ${
                selectedId === p.id
                  ? 'bg-zinc-800 text-zinc-100'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              {p.name}
            </button>
          ))}
        </div>

        {/* Form */}
        <div className="flex-1 overflow-y-auto space-y-4 pr-1">
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Profile Name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="e.g., Healthcare Provider"
            />
            <Input
              label="Description"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="Optional description"
            />
          </div>

          {/* Rate types */}
          <div>
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium mb-1.5">
              Rate Types
            </p>
            <div className="flex flex-wrap gap-1.5">
              {RATE_TYPE_OPTIONS.map((rt) => (
                <button
                  key={rt}
                  type="button"
                  onClick={() => toggleRateType(rt)}
                  className={`text-[10px] px-2 py-1 rounded transition-colors ${
                    form.rate_types.includes(rt)
                      ? 'bg-blue-500/20 text-blue-400'
                      : 'text-zinc-500 bg-zinc-800/50 hover:text-zinc-300'
                  }`}
                >
                  {rt.replace(/_/g, ' ')}
                </button>
              ))}
            </div>
          </div>

          {/* Focused categories by group */}
          <div>
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium mb-1.5">
              Focused Categories
            </p>
            {GROUP_ORDER.filter((g) => catsByGroup[g]?.length).map((group) => (
              <div key={group} className="mb-2">
                <p className="text-[10px] text-zinc-600 mb-1">{GROUP_LABELS[group]}</p>
                <div className="flex flex-wrap gap-1">
                  {catsByGroup[group].map((cat) => (
                    <button
                      key={cat}
                      type="button"
                      onClick={() => toggleCategory(cat)}
                      className={`text-[10px] px-1.5 py-0.5 rounded transition-colors ${
                        form.focused_categories.includes(cat)
                          ? 'bg-emerald-500/20 text-emerald-400'
                          : 'text-zinc-600 bg-zinc-800/30 hover:text-zinc-400'
                      }`}
                    >
                      {CATEGORY_SHORT_LABELS[cat] || cat}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Category order with up/down arrows */}
          {form.category_order.length > 0 && (
            <div>
              <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium mb-1.5">
                Category Order & Evidence
              </p>
              <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
                {form.category_order.map((cat, idx) => (
                  <div key={cat}>
                    <div className="flex items-center gap-2 px-3 py-1.5">
                      <div className="flex flex-col gap-0.5">
                        <button
                          type="button"
                          disabled={idx === 0}
                          onClick={() => moveCategoryOrder(cat, -1)}
                          className="text-[10px] text-zinc-600 hover:text-zinc-300 disabled:opacity-30 transition-colors leading-none"
                        >
                          ▲
                        </button>
                        <button
                          type="button"
                          disabled={idx === form.category_order.length - 1}
                          onClick={() => moveCategoryOrder(cat, 1)}
                          className="text-[10px] text-zinc-600 hover:text-zinc-300 disabled:opacity-30 transition-colors leading-none"
                        >
                          ▼
                        </button>
                      </div>
                      <span className="text-xs text-zinc-300 flex-1">
                        {CATEGORY_LABELS[cat] || cat}
                      </span>
                      <button
                        type="button"
                        onClick={() =>
                          setExpandedEvidence(expandedEvidence === cat ? null : cat)
                        }
                        className="text-[10px] text-zinc-600 hover:text-zinc-400 transition-colors"
                      >
                        {expandedEvidence === cat ? '▾ Evidence' : '▸ Evidence'}
                      </button>
                    </div>
                    {expandedEvidence === cat && (
                      <div className="px-3 pb-2 pl-8 space-y-1.5">
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-zinc-500 w-20">Confidence</span>
                          <input
                            type="range"
                            min={0}
                            max={1}
                            step={0.1}
                            value={form.category_evidence[cat]?.confidence ?? 0.5}
                            onChange={(e) =>
                              updateEvidence(cat, 'confidence', parseFloat(e.target.value))
                            }
                            className="flex-1 h-1 accent-emerald-500"
                          />
                          <span className="text-[10px] font-mono text-zinc-400 w-8">
                            {((form.category_evidence[cat]?.confidence ?? 0.5) * 100).toFixed(0)}%
                          </span>
                        </div>
                        <Textarea
                          label=""
                          placeholder="Reason for including this category..."
                          value={form.category_evidence[cat]?.reason ?? ''}
                          onChange={(e) => updateEvidence(cat, 'reason', e.target.value)}
                          rows={2}
                        />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Confidence Summary */}
          {form.category_order.length > 0 && (() => {
            const catsWithEvidence = form.category_order.filter(c => form.category_evidence[c]?.confidence !== undefined)
            const catsWithoutEvidence = form.category_order.length - catsWithEvidence.length
            const avgConfidence = catsWithEvidence.length > 0
              ? catsWithEvidence.reduce((sum, c) => sum + (form.category_evidence[c]?.confidence ?? 0), 0) / catsWithEvidence.length
              : 0
            const lowConfidence = catsWithEvidence.filter(c => (form.category_evidence[c]?.confidence ?? 0) < 0.7).length
            return (
              <p className="text-[11px] text-zinc-500">
                Avg confidence: <span className="text-zinc-300">{(avgConfidence * 100).toFixed(0)}%</span>
                {lowConfidence > 0 && <span className="text-amber-400 ml-2">{lowConfidence} below 70%</span>}
                {catsWithoutEvidence > 0 && <span className="text-zinc-600 ml-2">{catsWithoutEvidence} no evidence</span>}
              </p>
            )
          })()}

          {/* Actions */}
          <div className="flex items-center gap-2 pt-2 border-t border-zinc-800">
            <Button size="sm" disabled={saving || !form.name.trim()} onClick={() => { setConfirmDelete(false); handleSave() }}>
              {saving ? 'Saving...' : selectedId ? 'Update' : 'Create'}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => { setConfirmDelete(false); onClose() }}>
              Close
            </Button>
            {selectedId && (
              <button
                type="button"
                disabled={deleting}
                onClick={() => {
                  if (confirmDelete) {
                    handleDelete()
                  } else {
                    setConfirmDelete(true)
                  }
                }}
                className={`ml-auto text-xs transition-colors ${
                  confirmDelete
                    ? 'text-red-400 font-medium'
                    : 'text-red-400/60 hover:text-red-400'
                }`}
              >
                {deleting ? 'Deleting...' : confirmDelete ? 'Confirm delete?' : 'Delete Profile'}
              </button>
            )}
          </div>
        </div>
      </div>
    </Modal>
  )
}
