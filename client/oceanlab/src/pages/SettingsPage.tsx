import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import { MutationError } from '../components/MutationError'
import {
  useArtists,
  useContributors,
  useCreateContributor,
  useUpdateContributor,
  useUpdateArtist,
  useLabelSettings,
  useUnassignUpc,
  useUpcs,
  useUpdateLabelSettings,
  type LabelSettings,
} from '../api/hooks'

interface IsrcConfig {
  registrant_prefix: string
  year_digits: string
  next_designation: number
}

function useIsrcConfig() {
  return useQuery({
    queryKey: ['settings', 'isrc'],
    queryFn: async () => (await apiClient.get<IsrcConfig>('/settings/isrc')).data,
  })
}

function useUpdateIsrcConfig() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (registrant_prefix: string) =>
      (await apiClient.put<IsrcConfig>('/settings/isrc', { registrant_prefix })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings', 'isrc'] }),
  })
}

function useAddUpcs() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (codes: string[]) =>
      (await apiClient.post<{ added: number; rejected: string[]; skipped: number }>('/upcs', { codes })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['upcs'] }),
  })
}

export function SettingsPage() {
  const { data: labelSettings, isError: labelSettingsError } = useLabelSettings()
  const { data: artists } = useArtists()
  const { data: contributors } = useContributors()
  const updateLabelSettings = useUpdateLabelSettings()
  const { data: isrcConfig, isError: isrcConfigError } = useIsrcConfig()
  const updateIsrc = useUpdateIsrcConfig()
  const addUpcs = useAddUpcs()
  const [upcOffset, setUpcOffset] = useState(0)
  const upcLimit = 50
  const { data: upcs, isError: upcsError } = useUpcs(upcOffset, upcLimit)
  const unassignUpc = useUnassignUpc()
  const [prefix, setPrefix] = useState('')
  const [upcText, setUpcText] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [passwordMessage, setPasswordMessage] = useState('')
  const [labelDraft, setLabelDraft] = useState<LabelSettings | null>(null)
  const createContributor = useCreateContributor()
  const [newContributorName, setNewContributorName] = useState('')

  useEffect(() => {
    if (labelSettings) setLabelDraft(labelSettings)
  }, [labelSettings])

  const updateLabelDraft = <K extends keyof LabelSettings>(key: K, value: LabelSettings[K]) => {
    setLabelDraft((current) => (current ? { ...current, [key]: value } : current))
  }

  return (
      <div className="p-6 max-w-lg flex flex-col gap-8">
      <h1 className="text-2xl font-semibold">Settings</h1>

      <section>
        <h2 className="font-medium mb-2">Artists and contributors</h2>
        <p className="text-xs text-neutral-500 mb-2">Keep names and rights identities reusable across releases.</p>
        <div className="flex gap-2 mb-3">
          <input className="border rounded px-2 py-1 text-sm flex-1" placeholder="New contributor name" value={newContributorName} onChange={(e) => setNewContributorName(e.target.value)} />
          <button className="px-3 py-1.5 rounded bg-black text-white text-sm disabled:opacity-50" disabled={!newContributorName.trim() || createContributor.isPending} onClick={() => createContributor.mutate({ name: newContributorName.trim() }, { onSuccess: () => setNewContributorName('') })}>Add contributor</button>
        </div>
        <MutationError error={createContributor.error} />
        <div className="flex flex-col gap-2">
          {artists?.items.map((artist) => <ArtistRow key={artist.id} artist={artist} />)}
          {contributors?.items.map((contributor) => <ContributorRow key={contributor.id} contributor={contributor} />)}
        </div>
      </section>

      <section>
        <h2 className="font-medium mb-2">Label defaults</h2>
        {labelSettingsError && <p className="text-xs text-red-600 mb-2">Failed to load label defaults.</p>}
        {labelDraft && (
          <div className="flex flex-col gap-2">
            <label className="text-xs text-neutral-500">
              Default artist
              <select
                className="border rounded px-2 py-1 text-sm w-full text-neutral-900"
                value={labelDraft.default_artist_id ?? ''}
                onChange={(e) => updateLabelDraft('default_artist_id', e.target.value || null)}
              >
                <option value="">None</option>
                {artists?.items.map((artist) => <option key={artist.id} value={artist.id}>{artist.name}</option>)}
              </select>
            </label>
            <label className="text-xs text-neutral-500">
              Default contributor
              <select
                className="border rounded px-2 py-1 text-sm w-full text-neutral-900"
                value={labelDraft.default_contributor_id ?? ''}
                onChange={(e) => updateLabelDraft('default_contributor_id', e.target.value || null)}
              >
                <option value="">None</option>
                {contributors?.items.map((contributor) => (
                  <option key={contributor.id} value={contributor.id}>{contributor.name}</option>
                ))}
              </select>
            </label>
            {([
              ['default_genre', 'Genre'],
              ['default_territories', 'Territories'],
              ['c_line_template', 'C-line template'],
              ['p_line_template', 'P-line template'],
            ] as const).map(([key, label]) => (
              <label key={key} className="text-xs text-neutral-500">
                {label}
                <input
                  className="border rounded px-2 py-1 text-sm w-full text-neutral-900"
                  value={labelDraft[key] ?? ''}
                  onChange={(e) => updateLabelDraft(key, e.target.value)}
                />
              </label>
            ))}
            <div className="flex gap-2">
              <label className="text-xs text-neutral-500 flex-1">
                ISRC source
                <select
                  className="border rounded px-2 py-1 text-sm w-full text-neutral-900"
                  value={labelDraft.isrc_source}
                  onChange={(e) => updateLabelDraft('isrc_source', e.target.value as LabelSettings['isrc_source'])}
                >
                  <option value="distributor">Distributor</option>
                  <option value="own">Own</option>
                </select>
              </label>
              <label className="text-xs text-neutral-500 flex-1">
                UPC source
                <select
                  className="border rounded px-2 py-1 text-sm w-full text-neutral-900"
                  value={labelDraft.upc_source}
                  onChange={(e) => updateLabelDraft('upc_source', e.target.value as LabelSettings['upc_source'])}
                >
                  <option value="distributor">Distributor</option>
                  <option value="own">Own</option>
                </select>
              </label>
            </div>
            <button
              className="self-start px-3 py-1.5 rounded bg-black text-white dark:bg-white dark:text-black text-sm disabled:opacity-50"
              disabled={updateLabelSettings.isPending}
              onClick={() => labelDraft && updateLabelSettings.mutate(labelDraft)}
            >
              Save label defaults
            </button>
            <MutationError error={updateLabelSettings.error} />
          </div>
        )}
      </section>

      <section>
        <h2 className="font-medium mb-2">ISRC prefix</h2>
        {isrcConfigError ? (
          <p className="text-xs text-red-600 mb-2">Failed to load ISRC config.</p>
        ) : (
          <p className="text-xs text-neutral-500 mb-2">
            Current: {isrcConfig?.registrant_prefix || 'not configured'} · next designation:{' '}
            {isrcConfig?.next_designation ?? '--'} · year {isrcConfig?.year_digits || '--'}
          </p>
        )}
        <div className="flex gap-2">
          <input
            className="border rounded px-2 py-1 text-sm flex-1"
            placeholder="e.g. QZABC"
            value={prefix}
            onChange={(e) => setPrefix(e.target.value.toUpperCase())}
          />
          <button
            className="px-3 py-1.5 rounded bg-black text-white dark:bg-white dark:text-black text-sm"
            onClick={() => updateIsrc.mutate(prefix)}
            disabled={!prefix || updateIsrc.isPending}
          >
            Save
          </button>
        </div>
        <MutationError error={updateIsrc.error} />
      </section>

      <section>
        <h2 className="font-medium mb-2">UPC pool</h2>
        <p className="text-xs text-neutral-500 mb-2">One UPC/EAN code per line.</p>
        <textarea
          className="border rounded px-2 py-1 text-sm w-full h-24"
          value={upcText}
          onChange={(e) => setUpcText(e.target.value)}
        />
        <button
          className="mt-2 px-3 py-1.5 rounded bg-black text-white dark:bg-white dark:text-black text-sm"
          onClick={() =>
            addUpcs.mutate(
              upcText
                .split('\n')
                .map((s) => s.trim())
                .filter(Boolean),
              { onSuccess: () => setUpcText('') },
            )
          }
        >
          Add codes
        </button>
        {addUpcs.data && (
          <p className="text-xs mt-1">
            Added {addUpcs.data.added} codes.
            {addUpcs.data.skipped > 0 && ` ${addUpcs.data.skipped} already in the pool, skipped.`}
          </p>
        )}
        {addUpcs.data && addUpcs.data.rejected.length > 0 && (
          <p className="text-xs mt-1 text-red-600">Rejected: {addUpcs.data.rejected.join(', ')}</p>
        )}
        <MutationError error={addUpcs.error} />

        <p className={`text-xs mt-4 mb-2 ${upcsError ? 'text-red-600' : 'text-neutral-500'}`}>
          {upcsError
            ? 'Failed to load UPC pool.'
            : upcs
              ? `${upcs.available} available / ${upcs.assigned} assigned`
              : 'Loading counts…'}
        </p>
        {upcs && upcs.items.length > 0 && (
          <div className="border rounded overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b text-left">
                  <th className="px-2 py-1 font-medium">Code</th>
                  <th className="px-2 py-1 font-medium">Status</th>
                  <th className="px-2 py-1 font-medium">Release</th>
                  <th className="px-2 py-1 font-medium"></th>
                </tr>
              </thead>
              <tbody>
                {upcs.items.map((row) => {
                  const orphaned = row.status === 'assigned' && row.release_id === null
                  return (
                    <tr key={row.id} className="border-b last:border-0">
                      <td className="px-2 py-1 font-mono">{row.code}</td>
                      <td className="px-2 py-1">{orphaned ? 'orphaned' : row.status}</td>
                      <td className="px-2 py-1">{row.release_id ?? '—'}</td>
                      <td className="px-2 py-1 text-right">
                        {row.status === 'assigned' && (
                          <button
                            className="px-2 py-0.5 rounded border text-xs disabled:opacity-50"
                            disabled={unassignUpc.isPending}
                            onClick={() => unassignUpc.mutate(row.id)}
                          >
                            Unassign
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
        {upcs && upcs.total > upcLimit && (
          <div className="flex items-center gap-2 mt-2 text-xs">
            <button
              className="px-2 py-0.5 rounded border disabled:opacity-50"
              disabled={upcOffset === 0}
              onClick={() => setUpcOffset((o) => Math.max(0, o - upcLimit))}
            >
              Prev
            </button>
            <span className="text-neutral-500">
              {upcOffset + 1}–{Math.min(upcOffset + upcLimit, upcs.total)} of {upcs.total}
            </span>
            <button
              className="px-2 py-0.5 rounded border disabled:opacity-50"
              disabled={upcOffset + upcLimit >= upcs.total}
              onClick={() => setUpcOffset((o) => o + upcLimit)}
            >
              Next
            </button>
          </div>
        )}
        <MutationError error={unassignUpc.error} />
      </section>

      <section>
        <h2 className="font-medium mb-2">Change password</h2>
        <div className="flex gap-2">
          <input className="border rounded px-2 py-1 text-sm flex-1" type="password" placeholder="Current password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} />
          <input className="border rounded px-2 py-1 text-sm flex-1" type="password" placeholder="New password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
          <button
            className="px-3 py-1.5 rounded bg-black text-white dark:bg-white dark:text-black text-sm"
            onClick={async () => { const response = await apiClient.post('/auth/change-password', { current_password: currentPassword, new_password: newPassword }); setPasswordMessage(response.data.status === 'password_changed' ? 'Password changed. Log in again next time.' : 'Unable to change password.') }}
          >
            Change
          </button>
        </div>
        {passwordMessage && <p className="text-xs text-neutral-500 mt-2">{passwordMessage}</p>}
      </section>
    </div>
  )
}

function ArtistRow({ artist }: { artist: { id: string; name: string; notes?: string | null } }) {
  const update = useUpdateArtist(artist.id)
  const [name, setName] = useState(artist.name)
  return <label className="flex gap-2 items-center text-xs"><span className="w-20 text-neutral-500">Artist</span><input className="border rounded px-2 py-1 flex-1" value={name} onChange={(e) => setName(e.target.value)} onBlur={() => name !== artist.name && update.mutate({ name })} /></label>
}

function ContributorRow({ contributor }: { contributor: { id: string; name: string } }) {
  const update = useUpdateContributor(contributor.id)
  const [name, setName] = useState(contributor.name)
  return <label className="flex gap-2 items-center text-xs"><span className="w-20 text-neutral-500">Contributor</span><input className="border rounded px-2 py-1 flex-1" value={name} onChange={(e) => setName(e.target.value)} onBlur={() => name !== contributor.name && update.mutate({ name })} /></label>
}
