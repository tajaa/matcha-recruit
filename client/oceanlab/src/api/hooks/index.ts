import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../client'

export interface Artist {
  id: string
  name: string
  sort_name?: string | null
  country?: string | null
  spotify_id?: string | null
  apple_music_id?: string | null
  notes?: string | null
}

export interface Contributor {
  id: string
  name: string
  legal_name?: string | null
  ipi_number?: string | null
  pro_affiliation?: string | null
  email?: string | null
  notes?: string | null
}

export type CodeSource = 'own' | 'distributor'

export interface LabelSettings {
  default_artist_id: string | null
  default_contributor_id: string | null
  default_genre: string | null
  default_territories: string
  c_line_template: string
  p_line_template: string
  isrc_source: CodeSource
  upc_source: CodeSource
}

export interface Release {
  id: string
  title: string
  release_type: 'album' | 'ep' | 'single'
  status: 'draft' | 'ready' | 'packaged' | 'delivered' | 'released'
  upc?: string | null
  catalog_number?: string | null
  release_date?: string | null
  original_release_date?: string | null
  label_name?: string | null
  c_line?: string | null
  p_line?: string | null
  primary_artist_id: string
  genre?: string | null
  subgenre?: string | null
  territories?: string | null
  notes?: string | null
}

export interface Recording {
  id: string
  title: string
  version?: string | null
  isrc?: string | null
  primary_artist_id: string
  explicit?: boolean | null
  language?: string | null
  recording_year?: number | null
  audio_file_id?: string | null
  duration_seconds?: string | null
  sample_rate?: number | null
  bit_depth?: number | null
  channels?: number | null
  audio_format?: string | null
}

// Fields the server's TrackRead schema actually returns.
export interface TrackBase {
  id: string
  release_id: string
  recording_id: string
  disc_number: number
  position: number
  title_override?: string | null
}

// list_tracks additionally joins in the recording's title/isrc.
export interface Track extends TrackBase {
  recording_title: string
  recording_isrc?: string | null
}

interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export function useArtists() {
  return useQuery({
    queryKey: ['artists'],
    // TODO Phase 2: typeahead/pagination past 200
    queryFn: async () => (await apiClient.get<Page<Artist>>('/artists', { params: { limit: 200 } })).data,
  })
}

export function useCreateArtist() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { name: string }) => (await apiClient.post<Artist>('/artists', payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['artists'] }),
  })
}

export function useUpdateArtist(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { name: string; sort_name?: string | null; country?: string | null; notes?: string | null }) =>
      (await apiClient.patch<Artist>(`/artists/${id}`, payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['artists'] }),
  })
}

export function useContributors() {
  return useQuery({
    queryKey: ['contributors'],
    queryFn: async () => (await apiClient.get<Page<Contributor>>('/contributors', { params: { limit: 200 } })).data,
  })
}

export function useLabelSettings() {
  return useQuery({
    queryKey: ['settings', 'label'],
    queryFn: async () => (await apiClient.get<LabelSettings>('/settings/label')).data,
  })
}

export function useUpdateLabelSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: Partial<LabelSettings>) =>
      (await apiClient.put<LabelSettings>('/settings/label', payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings', 'label'] }),
  })
}

export interface ReleaseFilters {
  status?: string
  artist_id?: string
  q?: string
}

export function useReleases(filters: ReleaseFilters = {}) {
  return useQuery({
    queryKey: ['releases', filters],
    // TODO Phase 2: typeahead/pagination past 200
    queryFn: async () =>
      (await apiClient.get<Page<Release>>('/releases', { params: { ...filters, limit: 200 } })).data,
  })
}

export function useRelease(id: string | undefined) {
  return useQuery({
    queryKey: ['releases', id],
    queryFn: async () => (await apiClient.get<Release>(`/releases/${id}`)).data,
    enabled: !!id,
  })
}

export function useCreateRelease() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: {
      title: string
      release_type: string
      primary_artist_id: string
    }) => (await apiClient.post<Release>('/releases', payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['releases'] }),
  })
}

export function useUpdateRelease(id: string | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: Partial<Release>) => (await apiClient.patch<Release>(`/releases/${id}`, payload)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['releases', id] })
      qc.invalidateQueries({ queryKey: ['releases'] })
    },
  })
}

export function useRecordings(q?: string) {
  return useQuery({
    queryKey: ['recordings', q],
    queryFn: async () => (await apiClient.get<Page<Recording>>('/recordings', { params: { q, limit: 200 } })).data,
  })
}

export interface RecordingCreate {
  title: string
  version?: string | null
  explicit?: boolean | null
  language?: string | null
  recording_year?: number | null
  primary_artist_id: string
}

export function useCreateRecording() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: RecordingCreate) =>
      (await apiClient.post<Recording>('/recordings', payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['recordings'] }),
  })
}

export function useCreateContributor() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { name: string; legal_name?: string; ipi_number?: string; pro_affiliation?: string }) =>
      (await apiClient.post<Contributor>('/contributors', payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['contributors'] }),
  })
}

export function useUpdateContributor(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: Partial<Contributor>) =>
      (await apiClient.patch<Contributor>(`/contributors/${id}`, payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['contributors'] }),
  })
}

export function useCreateWork() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { title: string; language?: string }) =>
      (await apiClient.post<Work>('/works', payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['works'] }),
  })
}

export function useUpdateRecording(id: string | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: Partial<Recording>) =>
      (await apiClient.patch<Recording>(`/recordings/${id}`, payload)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['recordings'] })
      qc.invalidateQueries({ queryKey: ['releases'] })
    },
  })
}

export function useUpdateRecordingSplits(id: string | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: Array<{ contributor_id: string; role?: string | null; share_pct: string }>) =>
      (await apiClient.put(`/recordings/${id}/splits`, payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['recordings', id, 'splits'] }),
  })
}

export function useUpdateRecordingWorks(id: string | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (work_ids: string[]) =>
      (await apiClient.put(`/recordings/${id}/works`, { work_ids })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['recordings', id, 'works'] }),
  })
}

export interface ValidationIssue {
  code: string
  severity: 'error' | 'warning'
  message: string
  field?: string | null
  track_id?: string | null
}

export interface ValidationReport {
  packageable: boolean
  issues: ValidationIssue[]
}

export function useValidation(releaseId: string | undefined) {
  return useQuery({
    queryKey: ['releases', releaseId, 'validation'],
    queryFn: async () => (await apiClient.get<ValidationReport>(`/releases/${releaseId}/validation`)).data,
    enabled: !!releaseId,
  })
}

export function useMarkReleaseReady(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => (await apiClient.post<ValidationReport>(`/releases/${id}/ready`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['releases', id] })
      qc.invalidateQueries({ queryKey: ['releases', id, 'validation'] })
    },
  })
}

export function useStartPackage(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => (await apiClient.post<{ delivery_id: string; job_id: string }>(`/releases/${id}/package`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['releases', id] })
      qc.invalidateQueries({ queryKey: ['releases', id, 'validation'] })
    },
  })
}

export interface MasterSplit {
  id: string
  recording_id: string
  contributor_id: string
  role: string | null
  share_pct: string
  auto_created: boolean
}

export interface Work {
  id: string
  title: string
  language?: string | null
  auto_created: boolean
}

export function useRecordingSplits(recordingId: string | undefined) {
  return useQuery({
    queryKey: ['recordings', recordingId, 'splits'],
    queryFn: async () => (await apiClient.get<MasterSplit[]>(`/recordings/${recordingId}/splits`)).data,
    enabled: !!recordingId,
  })
}

export interface Credit {
  id: string
  recording_id: string
  contributor_id: string
  role: string
  credited_as?: string | null
  position: number
}

export function useRecordingCredits(recordingId: string | undefined) {
  return useQuery({
    queryKey: ['recordings', recordingId, 'credits'],
    queryFn: async () => (await apiClient.get<Credit[]>(`/recordings/${recordingId}/credits`)).data,
    enabled: !!recordingId,
  })
}

export function useUpdateRecordingCredits(id: string | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: Array<{ contributor_id: string; role: string; credited_as?: string | null; position: number }>) =>
      (await apiClient.put(`/recordings/${id}/credits`, payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['recordings', id, 'credits'] }),
  })
}

export function useRecordingWorks(recordingId: string | undefined) {
  return useQuery({
    queryKey: ['recordings', recordingId, 'works'],
    queryFn: async () => (await apiClient.get<Work[]>(`/recordings/${recordingId}/works`)).data,
    enabled: !!recordingId,
  })
}

export interface WorkWriter {
  id: string
  work_id: string
  contributor_id: string
  role: string
  share_pct: string
  publisher_name?: string | null
  publisher_share_pct?: string | null
  auto_created: boolean
}

export function useWorkWriters(workId: string | undefined) {
  return useQuery({
    queryKey: ['works', workId, 'writers'],
    queryFn: async () => (await apiClient.get<WorkWriter[]>(`/works/${workId}/writers`)).data,
    enabled: !!workId,
  })
}

export function useUpdateWorkWriters(workId: string | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: Array<{ contributor_id: string; role: string; share_pct: string; publisher_name?: string | null; publisher_share_pct?: string | null }>) =>
      (await apiClient.put(`/works/${workId}/writers`, payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['works', workId, 'writers'] }),
  })
}

export function useUpdateTrack(trackId: string, releaseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { title_override?: string | null }) =>
      (await apiClient.patch<TrackBase>(`/tracks/${trackId}`, payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['releases', releaseId, 'tracks'] }),
  })
}

export function useTracks(releaseId: string | undefined) {
  return useQuery({
    queryKey: ['releases', releaseId, 'tracks'],
    queryFn: async () => (await apiClient.get<Track[]>(`/releases/${releaseId}/tracks`)).data,
    enabled: !!releaseId,
  })
}

export function useAddTrack(releaseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { recording_id: string; disc_number?: number }) =>
      (await apiClient.post<Track>(`/releases/${releaseId}/tracks`, payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['releases', releaseId, 'tracks'] }),
  })
}

export function useReorderTracks(releaseId: string) {
  const qc = useQueryClient()
  return useMutation({
    // Server returns list[TrackRead] (no recording_title/recording_isrc) —
    // typed as TrackBase[] to match, not Track[]. The body is discarded;
    // the query is invalidated and refetched via list_tracks instead.
    mutationFn: async (payload: { disc_number: number; track_ids: string[] }) =>
      (await apiClient.post<TrackBase[]>(`/releases/${releaseId}/tracks/reorder`, payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['releases', releaseId, 'tracks'] }),
  })
}

export function useDeleteTrack(releaseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (trackId: string) => {
      await apiClient.delete(`/tracks/${trackId}`)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['releases', releaseId, 'tracks'] }),
  })
}

export function useAssignIsrc() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (recordingId: string) =>
      (await apiClient.post<{ isrc: string }>(`/recordings/${recordingId}/assign-isrc`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['recordings'] })
      qc.invalidateQueries({ predicate: (q) => q.queryKey[0] === 'releases' && q.queryKey.includes('tracks') })
    },
  })
}

export function useAssignUpc() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (releaseId: string) =>
      (await apiClient.post<{ upc: string }>(`/releases/${releaseId}/assign-upc`)).data,
    onSuccess: (_data, releaseId) => {
      qc.invalidateQueries({ queryKey: ['releases', releaseId] })
      qc.invalidateQueries({ queryKey: ['upcs'] })
    },
  })
}

export interface UpcRow {
  id: string
  code: string
  status: 'available' | 'assigned'
  release_id: string | null
}

interface UpcsResponse {
  items: UpcRow[]
  available: number
  assigned: number
  total: number
  limit: number
  offset: number
}

export function useUpcs(offset = 0, limit = 50) {
  return useQuery({
    queryKey: ['upcs', offset, limit],
    queryFn: async () => (await apiClient.get<UpcsResponse>('/upcs', { params: { limit, offset } })).data,
  })
}

export function useUnassignUpc() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (upcId: string) => {
      await apiClient.post(`/upcs/${upcId}/unassign`)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['upcs'] })
      qc.invalidateQueries({ queryKey: ['releases'] })
    },
  })
}
