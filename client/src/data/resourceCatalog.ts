/**
 * Resolves a pinned `(kind, id)` to a renderable card spec for the
 * Pinned Resources dashboard widget. The 5 resource catalogs are
 * scattered across hardcoded TS arrays (job descriptions, glossary,
 * calculators) and a server endpoint (state guides); this module is
 * the single place that knows how to map any kind+id back to label /
 * route / icon.
 *
 * State-guide labels are fetched lazily on first need and cached in
 * module scope. While the cache is empty the resolver returns the slug
 * as a fallback label so the widget renders something instead of a
 * loading spinner per chip.
 */

import type { ComponentType } from 'react'
import {
  FileText,
  Briefcase,
  BookOpen,
  Calculator,
  MapPin,
} from 'lucide-react'

import type { ResourceKind } from '../api/resourcePins'
import { JOB_DESCRIPTIONS } from '../pages/landing/resources/jobDescriptionsData'
import { GLOSSARY } from '../pages/landing/resources/glossaryData'
import { api } from '../api/client'

export type ResourceCardSpec = {
  kind: ResourceKind
  id: string
  label: string
  description?: string
  /** Path under `/app` so embedded routes resolve correctly. */
  route: string
  Icon: ComponentType<{ className?: string; size?: number }>
}

// Templates — mirror server `ASSETS` dict. Server is the source of truth
// for the file list; this map only carries human labels.
const TEMPLATE_LABELS: Record<string, string> = {
  'offer-letter': 'Offer Letter',
  'pip': 'Performance Improvement Plan',
  'termination-checklist': 'Termination Checklist',
  'interview-scorecard': 'Interview Scorecard',
  'interview-guide': 'Interview Guide',
  'pto-policy': 'PTO Policy Template',
  'workplace-investigation-report': 'Workplace Investigation Report',
  'performance-review': 'Performance Review Template',
  'disciplinary-action': 'Disciplinary Action Form',
  'remote-work-agreement': 'Remote Work Agreement',
  'expense-reimbursement': 'Expense Reimbursement Form',
  'severance-agreement': 'Severance Agreement',
}

const CALCULATOR_LABELS: Record<string, string> = {
  'pto-accrual': 'PTO Accrual',
  'turnover-cost': 'Turnover Cost',
  'overtime': 'Overtime',
  'total-comp': 'Total Compensation',
}

// State guide slug → name. Populated by ensureStateGuideLabels(). Empty
// at first; resolver falls back to slug-as-label until populated.
let _stateLabels: Record<string, string> | null = null
let _stateLabelsPromise: Promise<void> | null = null

type StateListResponse = {
  states: Array<{ slug: string; code: string; name: string }>
}

export function ensureStateGuideLabels(): Promise<void> {
  if (_stateLabels) return Promise.resolve()
  if (_stateLabelsPromise) return _stateLabelsPromise
  _stateLabelsPromise = api
    .get<StateListResponse>('/resources/state-guides')
    .then(d => {
      _stateLabels = Object.fromEntries(d.states.map(s => [s.slug, s.name]))
    })
    .catch(() => {
      _stateLabels = {}
    })
  return _stateLabelsPromise
}

export function resolveResourcePin(kind: ResourceKind, id: string): ResourceCardSpec {
  switch (kind) {
    case 'template':
      return {
        kind, id,
        label: TEMPLATE_LABELS[id] ?? id,
        route: `/app/resources/templates`,
        Icon: FileText,
      }
    case 'job_description': {
      const jd = JOB_DESCRIPTIONS.find(j => j.slug === id)
      return {
        kind, id,
        label: jd?.title ?? id,
        description: jd?.industry,
        route: `/app/resources/templates/job-descriptions/${id}`,
        Icon: Briefcase,
      }
    }
    case 'glossary': {
      const term = GLOSSARY.find(t => t.slug === id)
      return {
        kind, id,
        label: term?.term ?? id,
        description: term?.abbreviation,
        route: `/app/resources/glossary/${id}`,
        Icon: BookOpen,
      }
    }
    case 'calculator':
      return {
        kind, id,
        label: CALCULATOR_LABELS[id] ?? id,
        route: `/app/resources/calculators/${id}`,
        Icon: Calculator,
      }
    case 'state_guide':
      return {
        kind, id,
        // Slug fallback while async fetch is in flight; widget calls
        // ensureStateGuideLabels() on mount so the next render upgrades.
        label: _stateLabels?.[id] ?? id,
        route: `/app/resources/states/${id}`,
        Icon: MapPin,
      }
  }
}
