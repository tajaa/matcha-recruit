import { Loader2 } from 'lucide-react'
import IRCopilotCard from './IRCopilotCard'
import { IRRequestInfoModal } from './IRRequestInfoModal'
import { CopilotHeader } from './IRCopilotPanel/CopilotHeader'
import { CopilotInput } from './IRCopilotPanel/CopilotInput'
import { InfoRequestsList } from './IRCopilotPanel/InfoRequestsList'
import { TranscriptMessage } from './IRCopilotPanel/TranscriptMessage'
import { useCopilotPanel } from './IRCopilotPanel/useCopilotPanel'
import { type Props } from './IRCopilotPanel/types'

export default function IRCopilotPanel(props: Props) {
  const {
    incidentId,
    reportedByName,
    reportedByEmail,
    onOpenDocuments,
    messages,
    currentCards,
    openQuestions,
    progress,
    evidence,
    loading,
    streaming,
    busyCardMessageId,
    busyStage,
    input,
    setInput,
    error,
    closingIncident,
    requestInfoOpen,
    setRequestInfoOpen,
    bottomRef,
    incidentIsClosed,
    infoRequests,
    refreshInfoRequests,
    handleSubmitInput,
    handleAccept,
    handleCloseIncident,
    handleSkip,
    handleResendInfoRequest,
    handleRevokeInfoRequest,
    cardsByMessageId,
    emergencyAlertActive,
    acceptedCardIds,
  } = useCopilotPanel(props)

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-sm text-zinc-500">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading…
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <CopilotHeader
        streaming={streaming}
        incidentIsClosed={incidentIsClosed}
        closingIncident={closingIncident}
        emergencyAlertActive={emergencyAlertActive}
        progress={progress}
        evidence={evidence}
        onRequestInfo={() => setRequestInfoOpen(true)}
        onCloseIncident={() => { void handleCloseIncident() }}
      />

      <div className="flex-1 overflow-y-auto px-5 py-4">

      <InfoRequestsList
        infoRequests={infoRequests}
        onResend={(id) => { void handleResendInfoRequest(id) }}
        onRevoke={(id) => { void handleRevokeInfoRequest(id) }}
      />

      <IRRequestInfoModal
        open={requestInfoOpen}
        onClose={() => setRequestInfoOpen(false)}
        incidentId={incidentId}
        openQuestions={openQuestions}
        defaultRecipientName={reportedByName}
        defaultRecipientEmail={reportedByEmail}
        onSent={() => { void refreshInfoRequests() }}
      />

      {busyStage && (
        <div className="mb-4 max-w-[65ch] rounded-md border border-emerald-500/30 bg-emerald-500/5 px-3 py-2 text-sm text-emerald-200 flex items-center gap-2">
          <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
          <span className="leading-snug">{busyStage}</span>
        </div>
      )}

      {error && (
        <div className="mb-4 max-w-[65ch] rounded-md border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Transcript */}
      <div className="space-y-3">
        {messages.map((m) => (
          <TranscriptMessage key={m.id} m={m} />
        ))}

        {/* Current actionable cards */}
        {currentCards.length > 0 && (
          <div className="max-w-[65ch] space-y-2">
            {currentCards.map((c) => {
              const mid = cardsByMessageId.get(c.id) || ''
              const accepted = acceptedCardIds.has(c.id)
              return (
                <IRCopilotCard
                  key={c.id}
                  messageId={mid}
                  card={c}
                  accepted={accepted}
                  busy={busyCardMessageId === mid}
                  onAccept={handleAccept}
                  onSkip={(id) => void handleSkip(id, c.id)}
                  onOpenDocuments={onOpenDocuments}
                />
              )
            })}
          </div>
        )}

        {openQuestions.length > 0 && (
          <div className="max-w-[65ch] rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-sm">
            <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-amber-400/80 mb-1.5">
              Open questions
            </div>
            <ul className="text-zinc-200 space-y-1 list-disc pl-5">
              {openQuestions.map((q, i) => (
                <li key={i}>{q}</li>
              ))}
            </ul>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
      </div>

      {/* Input */}
      <CopilotInput
        input={input}
        setInput={setInput}
        streaming={streaming}
        emergencyAlertActive={emergencyAlertActive}
        onSubmit={() => { void handleSubmitInput() }}
      />
    </div>
  )
}
