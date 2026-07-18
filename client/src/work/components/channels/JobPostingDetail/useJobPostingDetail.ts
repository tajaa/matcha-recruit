import { useState, useEffect } from 'react'
import {
  getJobPosting,
  listApplicants,
  inviteToPosting,
  submitApplication,
  withdrawApplication,
  updateApplicationStatus,
  cancelJobPosting,
  closeJobPosting,
  approveJobPosting,
  rejectJobPosting,
  createJobPostingCheckout,
} from '../../../api/channelJobPostings'
import type { JobPostingDetail as JobPostingDetailData, ApplicationSummary } from '../../../api/channelJobPostings'
import { getMyResume, getApplicantResume, getMyTier, startRecruiterCheckout } from '../../../../api/profileResume'
import type { ProfileResume, TierInfo } from '../../../../api/profileResume'
import { useWorkBrand } from '../../../routes/WorkSurfaceContext'

export function useJobPostingDetail(channelId: string, postingId: string, myRole: string) {
  const brand = useWorkBrand()
  const [posting, setPosting] = useState<JobPostingDetailData | null>(null)
  const [applicants, setApplicants] = useState<ApplicationSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Invite state
  const [inviteInput, setInviteInput] = useState('')
  const [inviting, setInviting] = useState(false)
  const [inviteMsg, setInviteMsg] = useState('')

  // Apply state (for subscribers)
  const [coverLetter, setCoverLetter] = useState('')
  const [applying, setApplying] = useState(false)
  const [applyMsg, setApplyMsg] = useState('')

  // Status update state
  const [updatingId, setUpdatingId] = useState<string | null>(null)
  const [reviewerNotes, setReviewerNotes] = useState('')
  const [notesForApp, setNotesForApp] = useState<string | null>(null)

  // Action state
  const [actionLoading, setActionLoading] = useState(false)

  // Applicant snapshot expansion (recruiter view)
  const [expandedSnapshot, setExpandedSnapshot] = useState<string | null>(null)
  const [liveResumes, setLiveResumes] = useState<Record<string, ProfileResume | null>>({})
  const [liveLoading, setLiveLoading] = useState<string | null>(null)

  // Subscriber's own profile resume — required to apply
  const [myResume, setMyResume] = useState<ProfileResume | null>(null)
  const [myResumeLoaded, setMyResumeLoaded] = useState(false)
  const [showNoResumeModal, setShowNoResumeModal] = useState(false)

  // Recruiter tier state (for managers viewing the applicants list)
  const [tier, setTier] = useState<TierInfo | null>(null)
  const [upgrading, setUpgrading] = useState(false)

  const isManager = myRole === 'owner' || myRole === 'moderator'

  useEffect(() => {
    setLoading(true)
    const promises: Promise<unknown>[] = [
      getJobPosting(channelId, postingId).then(setPosting),
    ]
    if (isManager) {
      promises.push(listApplicants(channelId, postingId).then(setApplicants))
      promises.push(
        getMyTier().then(setTier).catch(() => {})
      )
    } else {
      promises.push(
        getMyResume()
          .then((r) => setMyResume(r))
          .catch(() => {})
          .finally(() => setMyResumeLoaded(true))
      )
    }
    Promise.all(promises)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load posting'))
      .finally(() => setLoading(false))
  }, [channelId, postingId, isManager])

  async function handleInvite() {
    const ids = inviteInput
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
    if (ids.length === 0) return
    setInviting(true)
    setInviteMsg('')
    try {
      await inviteToPosting(channelId, postingId, ids)
      setInviteMsg(`Invited ${ids.length} user${ids.length > 1 ? 's' : ''}`)
      setInviteInput('')
    } catch (err) {
      setInviteMsg(err instanceof Error ? err.message : 'Failed to invite')
    }
    setInviting(false)
  }

  async function handleApply() {
    // Client-side guardrail: require a profile resume before submitting.
    if (!myResume) {
      setShowNoResumeModal(true)
      return
    }
    setApplying(true)
    setApplyMsg('')
    try {
      await submitApplication(channelId, postingId, coverLetter.trim() || undefined)
      setApplyMsg('Application submitted!')
      // Refresh posting to get updated my_application
      const updated = await getJobPosting(channelId, postingId)
      setPosting(updated)
    } catch (err) {
      // Server-side guardrail: 409 no_resume. Wrap with the same modal.
      const msg = err instanceof Error ? err.message : 'Failed to apply'
      if (msg.toLowerCase().includes('no_resume') || msg.toLowerCase().includes('upload your resume')) {
        setShowNoResumeModal(true)
      } else {
        setApplyMsg(msg)
      }
    }
    setApplying(false)
  }

  async function loadLiveResume(applicantId: string) {
    if (liveResumes[applicantId] !== undefined) return
    setLiveLoading(applicantId)
    try {
      const r = await getApplicantResume(applicantId)
      setLiveResumes((prev) => ({ ...prev, [applicantId]: r }))
    } catch {
      setLiveResumes((prev) => ({ ...prev, [applicantId]: null }))
    } finally {
      setLiveLoading(null)
    }
  }

  async function handleWithdraw() {
    setApplying(true)
    try {
      await withdrawApplication(channelId, postingId)
      const updated = await getJobPosting(channelId, postingId)
      setPosting(updated)
    } catch (err) {
      setApplyMsg(err instanceof Error ? err.message : 'Failed to withdraw')
    }
    setApplying(false)
  }

  async function handleStatusUpdate(applicationId: string, status: string) {
    setUpdatingId(applicationId)
    try {
      await updateApplicationStatus(channelId, postingId, applicationId, status, reviewerNotes.trim() || undefined)
      setApplicants((prev) =>
        prev.map((a) => (a.id === applicationId ? { ...a, status, reviewed_at: new Date().toISOString() } : a))
      )
      setNotesForApp(null)
      setReviewerNotes('')
    } catch {}
    setUpdatingId(null)
  }

  async function handleCancel() {
    setActionLoading(true)
    try {
      await cancelJobPosting(channelId, postingId)
      const updated = await getJobPosting(channelId, postingId)
      setPosting(updated)
    } catch {}
    setActionLoading(false)
  }

  async function handleClose() {
    setActionLoading(true)
    try {
      await closeJobPosting(channelId, postingId)
      const updated = await getJobPosting(channelId, postingId)
      setPosting(updated)
    } catch {}
    setActionLoading(false)
  }

  async function handleApprove() {
    setActionLoading(true)
    try {
      await approveJobPosting(channelId, postingId)
      const updated = await getJobPosting(channelId, postingId)
      setPosting(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to approve')
    }
    setActionLoading(false)
  }

  async function handleReject() {
    const reason = window.prompt('Reason for rejection (optional)') ?? undefined
    setActionLoading(true)
    try {
      await rejectJobPosting(channelId, postingId, reason)
      const updated = await getJobPosting(channelId, postingId)
      setPosting(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reject')
    }
    setActionLoading(false)
  }

  async function handleStartCheckout() {
    setActionLoading(true)
    try {
      const { checkout_url } = await createJobPostingCheckout(channelId, postingId)
      window.location.href = checkout_url
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Checkout failed')
      setActionLoading(false)
    }
  }

  async function handleUpgradeRecruiter() {
    setUpgrading(true)
    try {
      const { checkout_url } = await startRecruiterCheckout(
        window.location.href,
        window.location.href,
      )
      window.location.href = checkout_url
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upgrade checkout failed')
      setUpgrading(false)
    }
  }

  return {
    brand,
    posting,
    applicants,
    loading,
    error,
    inviteInput,
    setInviteInput,
    inviting,
    inviteMsg,
    coverLetter,
    setCoverLetter,
    applying,
    applyMsg,
    updatingId,
    reviewerNotes,
    setReviewerNotes,
    notesForApp,
    setNotesForApp,
    actionLoading,
    expandedSnapshot,
    setExpandedSnapshot,
    liveResumes,
    liveLoading,
    myResume,
    myResumeLoaded,
    showNoResumeModal,
    setShowNoResumeModal,
    tier,
    upgrading,
    isManager,
    handleInvite,
    handleApply,
    loadLiveResume,
    handleWithdraw,
    handleStatusUpdate,
    handleCancel,
    handleClose,
    handleApprove,
    handleReject,
    handleStartCheckout,
    handleUpgradeRecruiter,
  }
}

export type JobPostingDetailController = ReturnType<typeof useJobPostingDetail>
