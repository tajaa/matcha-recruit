export type ScheduleVoiceCommand = 'confirm' | 'cancel' | 'other'

export interface ScheduleVoiceTranscript {
  available: boolean
  transcript: string | null
  command: ScheduleVoiceCommand
  model: string | null
}
