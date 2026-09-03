/** One definition of the role picker's rules, shared by the two places a
 *  manager can create a shift: the day-column quick form on the schedule page
 *  and the week-grid inspector in the editor.
 *
 *  They drifted immediately when each spelled its own: three wordings for one
 *  validation failure, and two copies of the label-derivation expression. */
import type { ScheduleJob, Shift } from '../../../types/employeeSchedule'

/** The one wording for "you have to pick a role". Reused as the message, and
 *  never as a state flag — components track the failure with a boolean, so
 *  rewording this cannot silently break aria-invalid. */
export const ROLE_REQUIRED_MESSAGE = 'Select a role for this shift'

export const NO_ROLES_MESSAGE = "No roles are available for this location. Add one in the schedule editor's Jobs tab."

export const ROLE_PLACEHOLDER = 'Select a role…'

/** What a legacy shift's role select shows for "this shift has no job". Only
 *  offered when editing — a new shift must pick one. */
export const NO_ROLE_OPTION = 'No assigned role (legacy)'

/** The label to persist for a chosen job.
 *
 *  `role` mirrors the job, so clearing the job clears the label too. Falling
 *  back to the shift's stored role there would save "Barista" on a shift the
 *  UI just said has no role — and the backend would then read it as an
 *  ungated shift wearing a job's name. */
export function roleLabelForJob(
  jobId: string,
  jobs: ScheduleJob[],
  shift?: Shift | null,
): string | null {
  if (!jobId) return null
  return jobs.find((job) => job.id === jobId)?.name ?? shift?.role ?? null
}

/** True when the shift's current job is not in the location's job list — a
 *  job that was deleted, or scoped to another location. The select keeps
 *  showing it so an unrelated edit cannot silently drop it. */
export function isJobMissingFromList(jobId: string, jobs: ScheduleJob[]): boolean {
  return !!jobId && !jobs.some((job) => job.id === jobId)
}
