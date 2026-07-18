import { Loader2 } from 'lucide-react'
import { useOshaLogs } from './OshaLogsPanel/useOshaLogs'
import { OshaToolbar } from './OshaLogsPanel/OshaToolbar'
import { ItaFilingPanel } from './OshaLogsPanel/ItaFilingPanel'
import { ItaValidationErrors, DataQualityWarnings } from './OshaLogsPanel/AlertPanels'
import { Summary300ACards } from './OshaLogsPanel/Summary300ACards'
import { Summary300AForm } from './OshaLogsPanel/Summary300AForm'
import { PrivacyCaseList } from './OshaLogsPanel/PrivacyCaseList'
import { Log300Table } from './OshaLogsPanel/Log300Table'
import { ExportAttestModal } from './OshaLogsPanel/ExportAttestModal'

export function OshaLogsPanel() {
  const osha = useOshaLogs()

  if (osha.loading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="animate-spin text-zinc-500" size={20} />
      </div>
    )
  }

  if (osha.locations.length === 0) {
    return (
      <div className="bg-zinc-900/40 border border-white/[0.06] rounded-lg p-8 text-center">
        <p className="text-sm text-zinc-300">No business locations defined.</p>
        <p className="text-[11px] text-zinc-600 mt-1">
          OSHA 300A summaries and ITA filings are per establishment. Add a location under Compliance to begin.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <OshaToolbar
        locations={osha.locations}
        locationId={osha.locationId}
        setLocationId={osha.setLocationId}
        year={osha.year}
        setYear={osha.setYear}
        years={osha.years}
        itaBusy={osha.itaBusy}
        onExport300Csv={osha.onExport300Csv}
        onExport300aCsv={osha.onExport300aCsv}
        onExport300aPdf={osha.onExport300aPdf}
        onExportIta={osha.exportIta}
        onSubmitIta={osha.submitIta}
      />

      <ItaFilingPanel
        itaCredConfigured={osha.itaCredConfigured}
        showTokenInput={osha.showTokenInput}
        setShowTokenInput={osha.setShowTokenInput}
        itaTokenInput={osha.itaTokenInput}
        setItaTokenInput={osha.setItaTokenInput}
        saveItaToken={osha.saveItaToken}
        savingToken={osha.savingToken}
        itaSubmitMsg={osha.itaSubmitMsg}
        itaSubmissions={osha.itaSubmissions}
      />

      <ItaValidationErrors itaProblems={osha.itaProblems} />

      <DataQualityWarnings summary={osha.summary} />

      <Summary300ACards summary={osha.summary} />

      <Summary300AForm
        summary={osha.summary}
        hours={osha.hours}
        setHours={osha.setHours}
        avgEmp={osha.avgEmp}
        setAvgEmp={osha.setAvgEmp}
        certBy={osha.certBy}
        setCertBy={osha.setCertBy}
        certTitle={osha.certTitle}
        setCertTitle={osha.setCertTitle}
        certDate={osha.certDate}
        setCertDate={osha.setCertDate}
        save300a={osha.save300a}
        saving={osha.saving}
        saveMsg={osha.saveMsg}
      />

      <PrivacyCaseList
        canRevealNames={osha.canRevealNames}
        entries={osha.entries}
        privacyNames={osha.privacyNames}
        setPrivacyNames={osha.setPrivacyNames}
        revealConfidentialNames={osha.revealConfidentialNames}
        revealing={osha.revealing}
      />

      <Log300Table entries={osha.entries} year={osha.year} navigate={osha.navigate} />

      <ExportAttestModal
        attestExport={osha.attestExport}
        setAttestExport={osha.setAttestExport}
        attestChecked={osha.attestChecked}
        setAttestChecked={osha.setAttestChecked}
        attestBusy={osha.attestBusy}
        confirmExport={osha.confirmExport}
      />
    </div>
  )
}
