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

export interface Release {
  id: string
  title: string
  release_type: 'album' | 'ep' | 'single'
  status: 'draft' | 'ready' | 'packaged' | 'delivered' | 'released'
  upc?: string | null
  catalog_number?: string | null
  release_date?: string | null
  primary_artist_id: string
  genre?: string | null
}

export interface Recording {
  id: string
  title: string
  version?: string | null
  isrc?: string | null
  primary_artist_id: string
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

export interface ReleaseFilters {
  status?: string
  artist_id?: string
  q?: string
}

export function useReleases(filters: ReleaseFilters = {}) {
  return useQuery({
    queryKey: ['releases', filters],
    queryFn: async () => (await apiClient.get<Page<Release>>('/releases', { params: filters })).data,
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
