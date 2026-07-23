import { useEffect, useState } from 'react'
import { Download, Loader2, PlayCircle, Upload } from 'lucide-react'
import { Badge, Button, Card, DataTable, FileUpload, useToast } from '../../components/ui'
import type { Column } from '../../components/ui'
import { benefitsApi } from '../../api/benefits/benefits'
import type { EligibilityException, RenewalRiskDimension } from '../../api/benefits/benefits'

const RISK_VARIANT = { critical: 'danger', elevated: 'warning', stable: 'success' } as const

export function EligibilityTab() {
  const { toast } = useToast()
  const [exceptions, setExceptions] = useState<EligibilityException[]>([])
  const [risk, setRisk] = useState<RenewalRiskDimension[]>([])
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)

  async function load() {
    setLoading(true)
    try {
      const [exc, r] = await Promise.all([benefitsApi.eligibilityExceptions(), benefitsApi.renewalRisk()])
      setExceptions(exc.exceptions)
      setRisk(r.dimensions)
    } catch {
      toast('Failed to load eligibility data', 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function runDetection() {
    setRunning(true)
    try {
      await benefitsApi.runDetection()
      await load()
      toast('Detection run complete', 'success')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Detection run failed', 'error')
    } finally {
      setRunning(false)
    }
  }

  async function uploadRoster(files: File[]) {
    if (!files[0]) return
    try {
      await benefitsApi.uploadRoster(files[0])
      await load()
      toast('Roster uploaded', 'success')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Roster upload failed', 'error')
    }
  }

  const excColumns: Column<EligibilityException>[] = [
    { key: 'employee', header: 'Employee', render: (e) => e.employee_name ?? '—' },
    { key: 'type', header: 'Exception', render: (e) => <Badge variant="warning">{e.exception_type.replace(/_/g, ' ')}</Badge> },
    { key: 'days', header: 'Days elapsed', render: (e) => e.days_elapsed ?? '—' },
    { key: 'leak', header: 'Est. monthly leak', render: (e) => e.estimated_monthly_leak ? `$${e.estimated_monthly_leak.toFixed(2)}` : '—' },
    { key: 'status', header: 'Status', render: (e) => <Badge>{e.status}</Badge> },
  ]

  const riskColumns: Column<RenewalRiskDimension>[] = [
    { key: 'dimension', header: 'Scope', render: (r) => r.dimension_type === 'company' ? 'Company-wide' : `${r.dimension_type}: ${r.dimension_value}` },
    { key: 'band', header: 'Risk band', render: (r) => <Badge variant={RISK_VARIANT[r.risk_band as keyof typeof RISK_VARIANT] ?? 'neutral'}>{r.risk_band}</Badge> },
    { key: 'turnover', header: 'Turnover', render: (r) => `${r.turnover_pct.toFixed(1)}%` },
    { key: 'headcount', header: 'Headcount', render: (r) => r.headcount },
    { key: 'triggers', header: 'Triggers', render: (r) => r.triggers.join('; ') || '—' },
  ]

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-2 justify-end">
        <Button variant="ghost" onClick={() => benefitsApi.downloadRosterTemplate()}>
          <Download className="w-4 h-4" /><span className="ml-2">Download CSV template</span>
        </Button>
        <FileUpload accept=".csv" onFiles={uploadRoster}>
          <Button variant="secondary"><Upload className="w-4 h-4" /><span className="ml-2">Upload roster CSV</span></Button>
        </FileUpload>
        <Button onClick={runDetection} disabled={running}>
          {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <PlayCircle className="w-4 h-4" />}
          <span className="ml-2">Run detection</span>
        </Button>
      </div>

      <Card className="p-4">
        <div className="text-sm font-medium text-zinc-300 mb-3">Eligibility exceptions</div>
        <DataTable columns={excColumns} rows={exceptions} rowKey={(e) => e.id} loading={loading} emptyText="No open exceptions." />
      </Card>

      <Card className="p-4">
        <div className="text-sm font-medium text-zinc-300 mb-3">Renewal risk</div>
        <DataTable columns={riskColumns} rows={risk} rowKey={(r) => `${r.dimension_type}:${r.dimension_value}`} loading={loading} emptyText="No renewal-risk data yet." />
      </Card>
    </div>
  )
}
