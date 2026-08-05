import { Loader2, Sparkles } from 'lucide-react'
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
    loading,
    streaming,
    showStartGate,
    startCopilot,
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
        {showStartGate && (
          <div className="max-w-[65ch] rounded-lg border border-zinc-700/60 bg-zinc-900/40 p-5 flex flex-col items-start gap-3">
            <div className="flex items-center gap-2 text-zinc-200">
              <Sparkles className="w-4 h-4 text-emerald-400" />
              <span className="font-medium text-sm">Copilot hasn't looked at this incident yet</span>
            </div>
            <p className="text-sm text-zinc-400 leading-snug">
              It'll review what's on file and suggest next steps. Nothing runs until you start it —
              you can also just type a question below instead.
            </p>
            <button
              onClick={startCopilot}
              disabled={streaming}
              className="inline-flex items-center gap-1.5 rounded-md bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed px-3.5 py-2 text-sm font-medium text-white transition-colors"
            >
              {streaming ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
              Start Copilot
            </button>
          </div>
        )}

        {messages.map((m) => (
          <TranscriptMessage key={m.id} m={m} />
        ))}

        {/* Current actionable cards */}
        {currentCards.length > 0 && (
          <div className="max-w-[65ch] space-y-2">
            {currentCards.map((c) => {
              const mid = cardsByMessageId.get(c.id) || ''
              const accepted = acceptedCardIds.has(c.id)
              // A card streamed in via SSE lands in `currentCards` before the
              // post-stream refresh() repopulates `messages` (the source of
              // cardsByMessageId), so `mid` is '' for a real window. Treat
              // that as busy too — otherwise Accept/Skip are clickable and
              // post message_id: '' (the route requires a UUID → 422) against
              // a card that becomes perfectly valid a moment later.
              const pendingId = mid === ''
              return (
                <IRCopilotCard
                  key={c.id}
                  messageId={mid}
                  card={c}
                  accepted={accepted}
                  busy={busyCardMessageId === mid || pendingId}
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
