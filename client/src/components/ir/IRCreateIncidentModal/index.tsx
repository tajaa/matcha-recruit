import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../../api/client'
import { Modal } from '../../ui'
import { useMe } from '../../../hooks/useMe'
import { useChatIntake } from '../../../hooks/ir/useChatIntake'
import type { IRIncident } from '../../../types/ir'
import { EMPTY_FORM, applyPrefillToForm, locationLabel, type LocationRow } from './shared'
import { WIZARD_STEPS, nextStepKey, prevStepKey, type WizardFieldKey, type WizardStepKey } from './steps'
import { WizardStep } from './WizardStep'
import { ReviewStep } from './ReviewStep'
import { EntryOptions } from './EntryOptions'
import { ChatThread } from './ChatThread'

type Props = {
  open: boolean
  onClose: () => void
  onCreated: (incident: IRIncident) => void
}

export function IRCreateIncidentModal({ open, onClose, onCreated }: Props) {
  const { me, hasFeature } = useMe()
  const hasRoster = hasFeature('employees')
  const canDictate = hasFeature('ir_voice_intake')
  const canChat = hasFeature('ir_chat_intake')
  // Lite-family tenants without the voice add-on see a purchase teaser
  // instead of nothing — the add-on is self-serve at /app/company#addons.
  const showDictateUpsell =
    !canDictate &&
    (me?.profile?.signup_source === 'matcha_lite' ||
      me?.profile?.signup_source === 'matcha_lite_essentials')

  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [locations, setLocations] = useState<LocationRow[] | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [voiceTranscript, setVoiceTranscript] = useState<string | null>(null)
  const [mode, setMode] = useState<'wizard' | 'chat'>('wizard')
  const [step, setStep] = useState<WizardStepKey>(WIZARD_STEPS[0].key)

  const chat = useChatIntake()

  // Auto-selected single-location tenants never need to answer "where" —
  // skip that step entirely rather than showing a Select with one disabled option.
  const activeSteps = useMemo(
    () => WIZARD_STEPS.filter((s) => s.key !== 'location_id' || (locations?.length ?? 0) !== 1),
    [locations],
  )
  const validLocationIds = useMemo(() => new Set((locations || []).map((l) => l.id)), [locations])

  useEffect(() => {
    if (!open) return
    let cancelled = false
    api.get<LocationRow[]>('/ir-onboarding/locations')
      .then((rows) => {
        if (cancelled) return
        const active = (rows || []).filter((r) => r.is_active)
        setLocations(active)
        if (active.length === 1) {
          setForm((f) => (f.location_id ? f : { ...f, location_id: active[0].id }))
        }
      })
      .catch(() => {
        if (!cancelled) setLocations([])
      })
    return () => {
      cancelled = true
    }
  }, [open])

  // The modal stays mounted across opens (controlled by `open`), so a
  // cancelled draft/dictation/chat must not survive to the NEXT, unrelated
  // incident — including a verbatim voice_transcript, which is attached to
  // whichever incident is submitted next as if it were evidence for THAT one.
  // Shared by both a successful submit and a Cancel/close so the two paths
  // can't drift.
  function resetFormState() {
    setForm(EMPTY_FORM)
    setSubmitError(null)
    setVoiceTranscript(null)
    setMode('wizard')
    setStep(WIZARD_STEPS[0].key)
    chat.reset()
  }

  function handleClose() {
    resetFormState()
    onClose()
  }

  function goNext() {
    setStep((s) => nextStepKey(s, activeSteps))
  }

  function goBack() {
    setStep((s) => prevStepKey(s, activeSteps))
  }

  function goToStep(key: WizardFieldKey) {
    setMode('wizard')
    setStep(key)
  }

  // Shared by voice dictation and AI chat completion: only overwrite a field
  // when the source has a value, then land on the review screen — nothing
  // auto-submits (the user reviews every field before hitting Create).
  function handlePrefill(
    prefill: Parameters<typeof applyPrefillToForm>[1],
    meta?: { voiceTranscript?: string },
  ) {
    setForm((f) => applyPrefillToForm(f, prefill, validLocationIds))
    if (meta?.voiceTranscript) setVoiceTranscript(meta.voiceTranscript)
    setMode('wizard')
    setStep('review')
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSubmitError(null)
    if (!form.location_id) {
      setSubmitError('Pick a location for this incident.')
      return
    }
    if (!form.date_text.trim()) {
      setSubmitError('Add when this happened.')
      return
    }
    if (!form.description.trim()) {
      setSubmitError('Add a description so Intelligent Theme Analysis can categorize the incident.')
      return
    }
    setSaving(true)
    try {
      const selectedLocation = (locations || []).find((l) => l.id === form.location_id)
      const witnesses = form.involved.map((name) => ({ name, contact: null }))
      const created = await api.post<IRIncident>('/ir/incidents', {
        description: form.description.trim(),
        // Free-text date — backend parses with dateutil and falls back to NOW().
        occurred_at: form.date_text.trim(),
        location_id: form.location_id,
        location: selectedLocation ? locationLabel(selectedLocation) : null,
        reported_by_name: form.reported_by_name.trim() || 'Unknown',
        witnesses,
        involved_employee_ids: form.involved_employee_ids,
        category_data: voiceTranscript ? { voice_transcript: voiceTranscript } : undefined,
      })
      resetFormState()
      onCreated(created)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to submit incident'
      setSubmitError(msg)
    } finally {
      setSaving(false)
    }
  }

  const currentStepIndex = activeSteps.findIndex((s) => s.key === step)
  const currentStepConfig = currentStepIndex >= 0 ? activeSteps[currentStepIndex] : null

  function canGoNext(): boolean {
    if (!currentStepConfig) return false
    if (!currentStepConfig.required) return true
    switch (currentStepConfig.key) {
      case 'location_id':
        return !!form.location_id
      case 'description':
        return !!form.description.trim()
      case 'date_text':
        return !!form.date_text.trim()
      case 'reported_by_name':
        return true // reporter name falls back to "Unknown" at submit
      default:
        return true
    }
  }

  return (
    <Modal open={open} onClose={handleClose} title="Report an incident">
      <div className="max-h-[68vh] space-y-5 overflow-y-auto pr-1.5">
        {mode === 'wizard' && step !== 'review' && (
          <EntryOptions
            canDictate={canDictate}
            canChat={canChat}
            showDictateUpsell={showDictateUpsell}
            locations={locations}
            onClose={onClose}
            onPrefill={handlePrefill}
            onOpenChat={() => {
              // A stale `complete=true` from an earlier chat session (user
              // jumped back here via a review-step Edit link) would otherwise
              // fire ChatCompleteBridge instantly and bounce right back.
              if (chat.complete) chat.reset()
              setMode('chat')
            }}
          />
        )}

        {mode === 'chat' && (
          <ChatThread
            messages={chat.messages}
            sending={chat.sending}
            chatError={chat.chatError}
            onSend={chat.send}
            onFinishInForm={() => setMode('wizard')}
          />
        )}

        {mode === 'chat' && chat.complete && (
          <ChatCompleteBridge onDone={() => handlePrefill(chat.fields)} />
        )}

        {mode === 'wizard' && step !== 'review' && currentStepConfig && (
          <WizardStep
            step={currentStepConfig}
            form={form}
            setForm={setForm}
            locations={locations}
            hasRoster={hasRoster}
            stepIndex={currentStepIndex}
            stepCount={activeSteps.length}
            onBack={goBack}
            onNext={goNext}
            canGoNext={canGoNext()}
            isFirstStep={currentStepIndex === 0}
          />
        )}

        {mode === 'wizard' && step === 'review' && (
          <ReviewStep
            form={form}
            locations={locations}
            saving={saving}
            submitError={submitError}
            onEditStep={goToStep}
            onSubmit={handleCreate}
          />
        )}
      </div>
    </Modal>
  )
}

// Fires onDone exactly once when the chat marks itself complete. The ref
// guard (not just an empty dep array) also survives StrictMode's dev-only
// double-invoke of mount effects, matching useVoiceDictation's maxFiredRef.
function ChatCompleteBridge({ onDone }: { onDone: () => void }) {
  const firedRef = useRef(false)
  useEffect(() => {
    if (firedRef.current) return
    firedRef.current = true
    onDone()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return null
}
