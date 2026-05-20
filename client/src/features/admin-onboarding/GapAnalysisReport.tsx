/**
 * Onboarding Gap-Analysis report — the team's durable handoff doc for a
 * compliance-complex company. Loads the assembled dossier from
 * GET /admin/onboarding/sessions/:id/report and renders it gaps-first,
 * with PDF / markdown export.
 */
import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Download, FileText, Loader2 } from 'lucide-react'

import { adminOnboarding } from '../../api/adminOnboarding'
import type { GapAnalysisDossier } from '../../api/adminOnboarding'

function Count({ label, value, alert }: { label: string; value: number; alert?: boolean }) {
  return (
    <div className="flex flex-col">
      <span className={`text-2xl font-semibold ${alert && value > 0 ? 'text-amber-300' : 'text-zinc-100'}`}>
        {value}
      </span>
      <span className="text-[11px] uppercase tracking-wider text-zinc-500">{label}</span>
    </div>
  )
}

function jurisdiction(item: Record<string, unknown>): string {
  const city = (item.city as string) || ''
  const county = (item.county as string) || ''
  const state = (item.state as string) || ''
  const parts = [city, county, state].filter(Boolean)
  return parts.length ? parts.join(', ') : 'Federal'
}

function Section({ title, count, children }: { title: string; count?: number; children: React.ReactNode }) {
  return (
    <section className="mb-8">
      <h3 className="text-sm font-semibold text-zinc-100 mb-2 flex items-center gap-2">
        {title}
        {count !== undefined && (
          <span className="text-xs font-normal text-zinc-500">({count})</span>
        )}
      </h3>
      {children}
    </section>
  )
}

function Table({ headers, rows }: { headers: string[]; rows: string[][] }) {
  if (!rows.length) {
    return <div className="text-sm text-zinc-600 italic">None</div>
  }
  return (
    <div className="overflow-x-auto rounded-md border border-zinc-800">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-zinc-900/60">
            {headers.map((h) => (
              <th key={h} className="text-left px-3 py-2 font-medium text-zinc-400 text-xs uppercase tracking-wider">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-zinc-800/70">
              {r.map((c, j) => (
                <td key={j} className="px-3 py-2 text-zinc-300 align-top">{c || '—'}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function GapAnalysisReport() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const [dossier, setDossier] = useState<GapAnalysisDossier | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [exporting, setExporting] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!sessionId) return
    setLoading(true)
    setError(null)
    try {
      setDossier(await adminOnboarding.getReport(sessionId))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load gap analysis')
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function exportAs(kind: 'pdf' | 'md') {
    if (!sessionId) return
    setExporting(kind)
    try {
      const name = (dossier?.company?.name || 'onboarding').trim()
      const slug = name.replace(/[^a-zA-Z0-9]+/g, '-').replace(/^-+|-+$/g, '').toLowerCase() || 'onboarding'
      const filename = `gap-analysis-${slug}.${kind}`
      if (kind === 'pdf') await adminOnboarding.downloadReportPdf(sessionId, filename)
      else await adminOnboarding.downloadReportMarkdown(sessionId, filename)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Export failed')
    } finally {
      setExporting(null)
    }
  }

  if (loading) {
    return (
      <div className="p-6 flex items-center gap-2 text-sm text-zinc-500">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading gap analysis…
      </div>
    )
  }

  if (error || !dossier) {
    return (
      <div className="p-6">
        <div className="rounded-md border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-300">
          {error || 'No gap analysis found.'}
        </div>
        <Link to="/admin/onboarding" className="inline-block mt-3 text-sm text-emerald-300 hover:underline">
          ← Back to onboarding
        </Link>
      </div>
    )
  }

  const co = dossier.company || {}
  const cov = dossier.coverage || { covered: [], gaps: [], ambiguous: [] }
  const counts = dossier.counts
  const sug = dossier.ai_suggestions || {}
  const scope = dossier.scope || {}

  return (
    <div className="p-6 max-w-4xl">
      <Link
        to={`/admin/onboarding/${sessionId}`}
        className="inline-flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 mb-4"
      >
        <ArrowLeft className="w-3 h-3" /> Back to wizard
      </Link>

      <div className="flex items-start justify-between gap-4 mb-1">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">
            Gap Analysis — {co.name || 'Untitled'}
          </h1>
          <p className="text-sm text-zinc-500 mt-0.5">
            {(co.industry || '—')}{co.specialty ? ` · ${co.specialty}` : ''} · {(dossier.locations || []).length} location{(dossier.locations || []).length === 1 ? '' : 's'} · {dossier.status || 'in progress'}
          </p>
        </div>
        <div className="flex gap-2 shrink-0">
          <button
            onClick={() => void exportAs('pdf')}
            disabled={!!exporting}
            className="inline-flex items-center gap-1.5 rounded-md border border-zinc-700 px-3 py-1.5 text-sm text-zinc-200 hover:bg-zinc-900 disabled:opacity-60"
          >
            {exporting === 'pdf' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
            PDF
          </button>
          <button
            onClick={() => void exportAs('md')}
            disabled={!!exporting}
            className="inline-flex items-center gap-1.5 rounded-md border border-zinc-700 px-3 py-1.5 text-sm text-zinc-200 hover:bg-zinc-900 disabled:opacity-60"
          >
            {exporting === 'md' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileText className="w-3.5 h-3.5" />}
            Markdown
          </button>
        </div>
      </div>

      <div className="flex gap-8 rounded-lg border border-zinc-800 bg-zinc-900/30 px-5 py-4 my-5">
        <Count label="Covered" value={counts.covered} />
        <Count label="Gaps" value={counts.gaps} alert />
        <Count label="Ambiguous" value={counts.ambiguous} alert />
        <Count label="Certs" value={counts.certifications} />
        <Count label="Licenses" value={counts.licenses} />
        <Count label="AI flags" value={counts.suggestions} alert />
      </div>

      <Section title="Gaps — need research" count={counts.gaps}>
        <Table
          headers={['Category', 'Scope', 'Jurisdiction', 'Why']}
          rows={(cov.gaps || []).map((g) => [
            g.category_slug || '', g.scope_level || '', jurisdiction(g as unknown as Record<string, unknown>), g.reason || '',
          ])}
        />
      </Section>

      <Section title="Ambiguous — need disambiguation" count={counts.ambiguous}>
        <Table
          headers={['Why', 'Candidates']}
          rows={(cov.ambiguous || []).map((a) => [a.why || '', String((a.candidates || []).length)])}
        />
      </Section>

      <Section title="AI suggestions (safety-net pass)" count={counts.suggestions}>
        {sug.summary && <p className="text-sm text-zinc-400 mb-2">{sug.summary}</p>}
        <div className="space-y-3">
          <Table
            headers={['Category', 'Scope', 'Why']}
            rows={(sug.suggested_compliance_categories || []).map((s) => [s.category_slug, s.scope, s.reason || ''])}
          />
          {(sug.suggested_certifications || []).length > 0 && (
            <Table
              headers={['Cert', 'Name', 'Why']}
              rows={(sug.suggested_certifications || []).map((s) => [s.slug, s.name, s.reason || ''])}
            />
          )}
          {(sug.suggested_licenses || []).length > 0 && (
            <Table
              headers={['License', 'Name', 'Why']}
              rows={(sug.suggested_licenses || []).map((s) => [s.slug, s.name, s.reason || ''])}
            />
          )}
        </div>
      </Section>

      <Section title="Covered — already in the compliance bank" count={counts.covered}>
        <Table
          headers={['Requirement', 'Category', 'Scope', 'Jurisdiction']}
          rows={(cov.covered || []).map((c) => [
            (c.title as string) || '', (c.category_slug as string) || '', (c.scope_level as string) || '',
            jurisdiction(c),
          ])}
        />
      </Section>

      <Section title="Certifications" count={counts.certifications}>
        <Table
          headers={['Name', 'Authority', 'Scope', 'Renewal (mo)']}
          rows={(scope.required_certifications || []).map((c) => [
            c.name, c.issuing_authority || '', c.scope_level, String(c.renewal_period_months ?? ''),
          ])}
        />
      </Section>

      <Section title="Licenses" count={counts.licenses}>
        <Table
          headers={['Name', 'Authority', 'Scope', 'Renewal (mo)']}
          rows={(scope.required_licenses || []).map((l) => [
            l.name, l.issuing_authority || '', l.scope_level, String(l.renewal_period_months ?? ''),
          ])}
        />
      </Section>

      <Section title="Jurisdictions in scope" count={(scope.applicable_jurisdictions || []).length}>
        <Table
          headers={['Jurisdiction']}
          rows={(scope.applicable_jurisdictions || []).map((j) => [
            jurisdiction(j as unknown as Record<string, unknown>),
          ])}
        />
      </Section>

      <Section title="Company profile">
        <div className="text-sm text-zinc-300 space-y-1">
          <div><span className="text-zinc-500">Entity type:</span> {co.entity_type || '—'}</div>
          <div><span className="text-zinc-500">Owner:</span> {co.owner_name || '—'} ({co.owner_email || '—'})</div>
          <div>
            <span className="text-zinc-500">Headcount:</span>{' '}
            FT {String((dossier.headcount as Record<string, unknown>).full_time ?? 0)} ·
            {' '}PT {String((dossier.headcount as Record<string, unknown>).part_time ?? 0)} ·
            {' '}Contractor {String((dossier.headcount as Record<string, unknown>).contractor ?? 0)}
          </div>
          {co.description && <div><span className="text-zinc-500">Description:</span> {co.description}</div>}
        </div>
        <div className="mt-3">
          <Table
            headers={['Name', 'City', 'County', 'State']}
            rows={(dossier.locations || []).map((loc) => [
              (loc.name as string) || '', (loc.city as string) || '', (loc.county as string) || '', (loc.state as string) || '',
            ])}
          />
        </div>
      </Section>
    </div>
  )
}
