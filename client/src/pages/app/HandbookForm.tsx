import { useEffect, useState, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { handbooks } from '../../api/client'
import { Button, Input, Select, FileUpload } from '../../components/ui'
import { HandbookWizardProgress } from '../../components/handbook/HandbookWizardProgress'
import { HandbookWizardCard } from '../../components/handbook/HandbookWizardCard'
import { HandbookStateSelector } from '../../components/handbook/HandbookStateSelector'
import { HandbookProfileForm } from '../../components/handbook/HandbookProfileForm'
import { HandbookPolicyPack } from '../../components/handbook/HandbookPolicyPack'
import { HandbookCustomSections } from '../../components/handbook/HandbookCustomSections'
import { HandbookReviewStep } from '../../components/handbook/HandbookReviewStep'
import { useMe } from '../../hooks/useMe'
import type {
  HandbookMode,
  HandbookSourceType,
  CompanyHandbookProfileInput,
  HandbookSectionInput,
  HandbookGuidedDraftResponse,
  HandbookGuidedSectionSuggestion,
  HandbookWizardDraftState,
  WorkbookType,
} from '../../types/handbook'
import {
  HEALTHCARE_WORKBOOK_TYPES,
  GENERAL_WORKBOOK_TYPES,
  WORKBOOK_TYPE_LABELS,
} from '../../types/handbook'

const STEPS = ['Business Profile', 'Workbook Type', 'State Scope', 'Company Profile', 'Policy Setup', 'Review']

const DEFAULT_PROFILE: CompanyHandbookProfileInput = {
  legal_name: '',
  dba: null,
  ceo_or_president: '',
  headcount: null,
  remote_workers: false,
  minors: false,
  tipped_employees: false,
  union_employees: false,
  federal_contracts: false,
  group_health_insurance: false,
  background_checks: false,
  hourly_employees: true,
  salaried_employees: false,
  commissioned_employees: false,
  tip_pooling: false,
}

export default function HandbookForm() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const isEdit = !!id
  const { isHealthcare } = useMe()

  // Wizard state
  const [step, setStep] = useState(0)
  const [title, setTitle] = useState('')
  const [mode, setMode] = useState<HandbookMode>('single_state')
  const [sourceType, setSourceType] = useState<HandbookSourceType>('template')
  const [industry, setIndustry] = useState('general')
  const [workbookType, setWorkbookType] = useState<WorkbookType | null>(null)
  const [states, setStates] = useState<string[]>([])
  const [autoDetected, setAutoDetected] = useState<string[]>([])
  const [profile, setProfile] = useState<CompanyHandbookProfileInput>(DEFAULT_PROFILE)
  const [customSections, setCustomSections] = useState<HandbookSectionInput[]>([])
  const [guidedResult, setGuidedResult] = useState<HandbookGuidedDraftResponse | null>(null)
  const [guidedAnswers, setGuidedAnswers] = useState<Record<string, string>>({})
  const [suggestedSections, setSuggestedSections] = useState<HandbookGuidedSectionSuggestion[]>([])
  const [file, setFile] = useState<File | null>(null)
  const [fileUrl, setFileUrl] = useState<string | null>(null)
  const [fileName, setFileName] = useState<string | null>(null)

  // UI state
  const [building, setBuilding] = useState(false)
  const [creating, setCreating] = useState(false)
  const [draftStatus, setDraftStatus] = useState<'saved' | 'saving' | 'unsaved'>('unsaved')
  const [loadingDraft, setLoadingDraft] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const saveTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  const workbookOptions = isHealthcare ? HEALTHCARE_WORKBOOK_TYPES : GENERAL_WORKBOOK_TYPES

  // Build draft state for save/restore
  const buildDraftState = useCallback((): HandbookWizardDraftState => ({
    step, title, mode, sourceType, industry, workbookType, states, profile,
    customSections, guidedAnswers, suggestedSections,
    fileUrl, fileName,
  }), [step, title, mode, sourceType, industry, workbookType, states, profile, customSections, guidedAnswers, suggestedSections, fileUrl, fileName])

  function restoreDraft(s: HandbookWizardDraftState) {
    if (s.step != null) setStep(s.step as number)
    if (s.title) setTitle(s.title as string)
    if (s.mode) setMode(s.mode as HandbookMode)
    if (s.sourceType) setSourceType(s.sourceType as HandbookSourceType)
    if (s.industry) setIndustry(s.industry as string)
    if (s.workbookType) setWorkbookType(s.workbookType as WorkbookType)
    if (s.states) setStates(s.states as string[])
    if (s.profile) setProfile(s.profile as CompanyHandbookProfileInput)
    if (s.customSections) setCustomSections(s.customSections as HandbookSectionInput[])
    if (s.guidedAnswers) setGuidedAnswers(s.guidedAnswers as Record<string, string>)
    if (s.suggestedSections) setSuggestedSections(s.suggestedSections as HandbookGuidedSectionSuggestion[])
    if (s.fileUrl) setFileUrl(s.fileUrl as string)
    if (s.fileName) setFileName(s.fileName as string)
  }

  // Load existing draft or handbook for editing
  useEffect(() => {
    async function init() {
      try {
        if (isEdit) {
          const hb = await handbooks.get(id!)
          setTitle(hb.title)
          setMode(hb.mode)
          setSourceType(hb.source_type)
          if (hb.workbook_type) setWorkbookType(hb.workbook_type)
          setStates(hb.scopes.map((s) => s.state))
          setProfile({
            legal_name: hb.profile.legal_name,
            dba: hb.profile.dba,
            ceo_or_president: hb.profile.ceo_or_president,
            headcount: hb.profile.headcount,
            remote_workers: hb.profile.remote_workers,
            minors: hb.profile.minors,
            tipped_employees: hb.profile.tipped_employees,
            union_employees: hb.profile.union_employees,
            federal_contracts: hb.profile.federal_contracts,
            group_health_insurance: hb.profile.group_health_insurance,
            background_checks: hb.profile.background_checks,
            hourly_employees: hb.profile.hourly_employees,
            salaried_employees: hb.profile.salaried_employees,
            commissioned_employees: hb.profile.commissioned_employees,
            tip_pooling: hb.profile.tip_pooling,
          })
          if (hb.file_url) setFileUrl(hb.file_url)
          if (hb.file_name) setFileName(hb.file_name)
        } else {
          // Try to restore wizard draft
          const draft = await handbooks.getWizardDraft()
          if (draft?.state && Object.keys(draft.state).length > 0) {
            restoreDraft(draft.state)
            setDraftStatus('saved')
          }
          // Load saved profile
          try {
            const existingProfile = await handbooks.getProfile()
            if (existingProfile.legal_name) {
              setProfile((prev) => ({
                ...prev,
                legal_name: prev.legal_name || existingProfile.legal_name,
                dba: prev.dba || existingProfile.dba,
                ceo_or_president: prev.ceo_or_president || existingProfile.ceo_or_president,
                headcount: prev.headcount ?? existingProfile.headcount,
              }))
            }
          } catch {
            // No existing profile
          }
        }
      } catch {
        // Ignore load errors
      } finally {
        setLoadingDraft(false)
      }
    }
    init()
  }, [id, isEdit])

  // Auto-save draft every 5s
  useEffect(() => {
    if (isEdit || loadingDraft) return
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    setDraftStatus('unsaved')
    saveTimerRef.current = setTimeout(async () => {
      setDraftStatus('saving')
      try {
        await handbooks.saveWizardDraft(buildDraftState())
        setDraftStatus('saved')
      } catch {
        setDraftStatus('unsaved')
      }
    }, 5000)
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    }
  }, [step, title, mode, sourceType, industry, workbookType, states, profile, customSections, guidedAnswers, suggestedSections, fileUrl, fileName, isEdit, loadingDraft, buildDraftState])

  async function handleAutoDetect() {
    try {
      const scopes = await handbooks.getAutoScopes()
      const detected = scopes.map((s) => s.state)
      setAutoDetected(detected)
      if (detected.length > 0 && states.length === 0) {
        setStates(detected)
      }
    } catch {
      // Ignore
    }
  }

  async function handleBuildPolicyPack() {
    setBuilding(true)
    setError(null)
    try {
      const result = await handbooks.generateGuidedDraft({
        title: title || undefined,
        mode,
        scopes: states.map((s) => ({ state: s })),
        profile,
        industry: industry || undefined,
        answers: guidedAnswers,
        existing_custom_sections: suggestedSections,
      })
      setGuidedResult(result)
      if (result.suggested_sections.length > 0) {
        setSuggestedSections(result.suggested_sections)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to build policy pack')
    } finally {
      setBuilding(false)
    }
  }

  async function handleFileUpload(files: File[]) {
    const f = files[0]
    if (!f) return
    setFile(f)
    try {
      const res = await handbooks.uploadFile(f)
      setFileUrl(res.url)
      setFileName(res.filename)
    } catch {
      setError('File upload failed')
    }
  }

  async function handleCreate() {
    setCreating(true)
    setError(null)
    try {
      if (isEdit) {
        await handbooks.update(id!, {
          title,
          mode,
          scopes: states.map((s) => ({ state: s })),
          profile,
          sections: customSections.length > 0 ? customSections : undefined,
          file_url: fileUrl,
          file_name: fileName,
          workbook_type: workbookType,
        })
      } else {
        // Add conditional sections based on profile flags
        const conditionalSections: HandbookSectionInput[] = []
        if (profile.remote_workers) {
          conditionalSections.push({
            section_key: 'remote_work_policy',
            title: 'Remote Work Policy',
            content: '',
            section_order: 400,
            section_type: 'custom',
          })
        }
        if (profile.group_health_insurance) {
          conditionalSections.push({
            section_key: 'group_health_insurance_policy',
            title: 'Group Health Insurance Policy',
            content: '',
            section_order: 401,
            section_type: 'custom',
          })
        }

        await handbooks.create({
          title,
          mode,
          source_type: sourceType,
          industry: industry || undefined,
          scopes: states.map((s) => ({ state: s })),
          profile,
          custom_sections: [...customSections, ...conditionalSections],
          guided_answers: guidedAnswers,
          file_url: fileUrl ?? undefined,
          file_name: fileName ?? undefined,
          create_from_template: sourceType === 'template',
          workbook_type: workbookType,
        })
        // Clear draft on success
        await handbooks.clearWizardDraft().catch(() => {})
      }
      navigate('/app/handbooks')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create handbook')
    } finally {
      setCreating(false)
    }
  }

  // Validation per step
  function canAdvance(): boolean {
    switch (step) {
      case 0: return title.trim().length >= 2
      case 1: return workbookType !== null
      case 2: return states.length >= (mode === 'multi_state' ? 2 : 1)
      case 3: return profile.legal_name.trim().length > 0 && profile.ceo_or_president.trim().length > 0
      case 4: return sourceType === 'upload' ? !!fileUrl : true
      case 5: return true
      default: return false
    }
  }

  if (loadingDraft) return <p className="text-sm text-zinc-500">Loading...</p>

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-2xl font-semibold text-zinc-100 mb-4">
        {isEdit ? 'Edit Handbook' : 'Create Handbook'}
      </h1>

      <HandbookWizardProgress currentStep={step} draftStatus={isEdit ? undefined : draftStatus} />

      {error && (
        <div className="mb-4 p-3 rounded-lg border border-red-800/50 bg-red-900/20 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* Step 0: Business Profile */}
      {step === 0 && (
        <HandbookWizardCard stepLabel="Step 1" title="Handbook Details" description="Name your handbook and choose its configuration." required>
          <div className="space-y-3">
            <Input
              id="hb-title"
              label="Title"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. 2026 Employee Handbook"
            />
            <Select
              id="hb-mode"
              label="Mode"
              value={mode}
              onChange={(e) => {
                const v = e.target.value as HandbookMode
                setMode(v)
                if (v === 'single_state' && states.length > 1) setStates([states[0]])
              }}
              options={[
                { value: 'single_state', label: 'Single State' },
                { value: 'multi_state', label: 'Multi-State' },
              ]}
            />
            <Select
              id="hb-source"
              label="Source"
              value={sourceType}
              onChange={(e) => setSourceType(e.target.value as HandbookSourceType)}
              options={[
                { value: 'template', label: 'Generate from compliance template' },
                { value: 'upload', label: 'Upload existing PDF' },
              ]}
            />
          </div>
        </HandbookWizardCard>
      )}

      {/* Step 1: Workbook Type */}
      {step === 1 && (
        <HandbookWizardCard stepLabel="Step 2" title="Workbook Type" description="Select the category for this handbook." required>
          <div className="grid grid-cols-2 gap-3">
            {workbookOptions.map((wt) => (
              <button
                key={wt}
                type="button"
                onClick={() => setWorkbookType(wt)}
                className={`text-left p-3 rounded-lg border transition-colors ${
                  workbookType === wt
                    ? 'border-emerald-500 bg-emerald-500/10 ring-2 ring-emerald-500'
                    : 'border-zinc-700 bg-zinc-800/50 hover:border-zinc-600'
                }`}
              >
                <span className={`text-sm font-medium ${workbookType === wt ? 'text-emerald-400' : 'text-zinc-200'}`}>
                  {WORKBOOK_TYPE_LABELS[wt]}
                </span>
              </button>
            ))}
          </div>
        </HandbookWizardCard>
      )}

      {/* Step 2: State Scope */}
      {step === 2 && (
        <HandbookWizardCard stepLabel="Step 3" title="State Scope" description="Select the states your handbook will cover." required>
          <HandbookStateSelector
            selected={states}
            onChange={setStates}
            autoDetected={autoDetected}
            onAutoDetect={handleAutoDetect}
            multi={mode === 'multi_state'}
          />
        </HandbookWizardCard>
      )}

      {/* Step 3: Company Profile */}
      {step === 3 && (
        <HandbookWizardCard stepLabel="Step 4" title="Company Profile" description="Enter your company details and workforce profile." required>
          <HandbookProfileForm profile={profile} onChange={setProfile} />
        </HandbookWizardCard>
      )}

      {/* Step 4: Policy Setup */}
      {step === 4 && (
        <HandbookWizardCard stepLabel="Step 5" title="Policy Setup" description={sourceType === 'upload' ? 'Upload your existing handbook PDF.' : 'Build your policy pack using AI guidance.'}>
          {sourceType === 'upload' ? (
            <div className="space-y-3">
              <FileUpload accept=".pdf" onFiles={handleFileUpload}>
                {file || fileName ? (
                  <p className="text-sm text-zinc-300">{fileName || file?.name}</p>
                ) : (
                  <p>Drop a PDF here or <span className="text-emerald-400 underline">browse</span></p>
                )}
              </FileUpload>
            </div>
          ) : (
            <div className="space-y-4">
              <HandbookPolicyPack
                industry={industry}
                onIndustryChange={setIndustry}
                guidedResult={guidedResult}
                guidedAnswers={guidedAnswers}
                onAnswerChange={(qid, val) => setGuidedAnswers((prev) => ({ ...prev, [qid]: val }))}
                onBuildPolicyPack={handleBuildPolicyPack}
                building={building}
                suggestedSections={suggestedSections}
              />
              <div className="border-t border-zinc-800 pt-4">
                <h4 className="text-sm font-medium text-zinc-300 mb-2">Custom Sections</h4>
                <HandbookCustomSections sections={customSections} onChange={setCustomSections} />
              </div>
            </div>
          )}
        </HandbookWizardCard>
      )}

      {/* Step 5: Review */}
      {step === 5 && (
        <HandbookWizardCard stepLabel="Step 6" title="Review" description="Review your handbook configuration before creating.">
          <HandbookReviewStep
            title={title}
            mode={mode}
            sourceType={sourceType}
            industry={industry}
            workbookType={workbookType}
            states={states}
            profile={profile}
            customSections={customSections}
            suggestedSections={suggestedSections}
            fileName={fileName}
          />
        </HandbookWizardCard>
      )}

      {/* Navigation */}
      <div className="flex items-center justify-between mt-4">
        <Button
          size="sm"
          variant="ghost"
          onClick={() => step > 0 ? setStep(step - 1) : navigate('/app/handbooks')}
        >
          {step > 0 ? 'Back' : 'Cancel'}
        </Button>
        <div className="flex items-center gap-2">
          {step < STEPS.length - 1 ? (
            <Button size="sm" onClick={() => setStep(step + 1)} disabled={!canAdvance()}>
              Next
            </Button>
          ) : (
            <Button size="sm" onClick={handleCreate} disabled={creating || !canAdvance()}>
              {creating ? 'Creating...' : isEdit ? 'Save Changes' : 'Create Handbook'}
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
