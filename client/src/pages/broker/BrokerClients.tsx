import { Plus, Loader2, AlertCircle, Upload } from 'lucide-react'
import { Button } from '../../components/ui'
import { HelpHint } from '../../components/broker/HelpHint'
import { BrokerTermsGate } from './BrokerClients/BrokerTermsGate'
import { ClientSetupsTable } from './BrokerClients/ClientSetupsTable'
import { AddClientModal } from './BrokerClients/AddClientModal'
import { CsvUploadModal } from './BrokerClients/CsvUploadModal'
import { useBrokerClients } from './BrokerClients/useBrokerClients'

export default function BrokerClients({ embedded = false }: { embedded?: boolean }) {
  const {
    setups, loading, error, needsTerms,
    showAdd, setShowAdd, form, setForm, saving, addError, setAddError, sendingInvite,
    showCsvUpload, setShowCsvUpload, csvRows, csvFile, csvSubmitting, csvResult, csvError, fileInputRef,
    fetchSetups, handleCreate, sendInvite,
    addLocation, removeLocation, updateLocation,
    handleCsvFile, handleCsvDrop, submitCsvBatch, closeCsvModal,
  } = useBrokerClients()

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
      <div className={`flex items-center ${embedded ? 'justify-end' : 'justify-between'}`}>
        {!embedded && (
          <div>
            <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight text-zinc-100">Client Onboarding <HelpHint text="Bring a company onto Matcha — create the setup, pre-configure their features, and send the invite. Track each one through the pipeline to live." /></h1>
            <p className="mt-1 text-sm text-zinc-500">Create and manage client setups for your referred companies.</p>
          </div>
        )}
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

      <ClientSetupsTable
        setups={setups}
        sendingInvite={sendingInvite}
        onSendInvite={sendInvite}
        onAddClient={() => setShowAdd(true)}
      />

      {/* Add Client Setup Modal */}
      <AddClientModal
        open={showAdd}
        form={form}
        setForm={setForm}
        saving={saving}
        addError={addError}
        onClose={() => { setShowAdd(false); setAddError('') }}
        onSubmit={handleCreate}
        addLocation={addLocation}
        removeLocation={removeLocation}
        updateLocation={updateLocation}
      />

      {/* CSV Upload Modal */}
      <CsvUploadModal
        open={showCsvUpload}
        csvRows={csvRows}
        csvFile={csvFile}
        csvSubmitting={csvSubmitting}
        csvResult={csvResult}
        csvError={csvError}
        fileInputRef={fileInputRef}
        onClose={closeCsvModal}
        onFile={handleCsvFile}
        onDrop={handleCsvDrop}
        onSubmit={submitCsvBatch}
      />
    </div>
  )
}
