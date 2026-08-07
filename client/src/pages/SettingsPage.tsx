import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import { clearToken, getToken, setToken } from '../api/client'
import { MutationError } from '../components/MutationError'

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
  return useMutation({
    mutationFn: async (codes: string[]) =>
      (await apiClient.post<{ added: number; rejected: string[] }>('/upcs', { codes })).data,
  })
}

export function SettingsPage() {
  const { data: isrcConfig } = useIsrcConfig()
  const updateIsrc = useUpdateIsrcConfig()
  const addUpcs = useAddUpcs()
  const [prefix, setPrefix] = useState('')
  const [upcText, setUpcText] = useState('')
  const [tokenInput, setTokenInput] = useState(getToken() ?? '')

  return (
    <div className="p-6 max-w-lg flex flex-col gap-8">
      <h1 className="text-2xl font-semibold">Settings</h1>

      <section>
        <h2 className="font-medium mb-2">ISRC prefix</h2>
        <p className="text-xs text-neutral-500 mb-2">
          Current: {isrcConfig?.registrant_prefix || 'not configured'} · next designation:{' '}
          {isrcConfig?.next_designation ?? '--'} · year {isrcConfig?.year_digits || '--'}
        </p>
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
        {addUpcs.data && <p className="text-xs mt-1">Added {addUpcs.data.added} codes.</p>}
        {addUpcs.data && addUpcs.data.rejected.length > 0 && (
          <p className="text-xs mt-1 text-red-600">Rejected: {addUpcs.data.rejected.join(', ')}</p>
        )}
        <MutationError error={addUpcs.error} />
      </section>

      <section>
        <h2 className="font-medium mb-2">API token</h2>
        <div className="flex gap-2">
          <input
            className="border rounded px-2 py-1 text-sm flex-1"
            type="password"
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
          />
          <button
            className="px-3 py-1.5 rounded bg-black text-white dark:bg-white dark:text-black text-sm"
            onClick={() => {
              setToken(tokenInput)
              window.location.reload()
            }}
          >
            Save
          </button>
          <button
            className="px-3 py-1.5 rounded border text-sm"
            onClick={() => {
              clearToken()
              window.location.reload()
            }}
          >
            Clear
          </button>
        </div>
      </section>
    </div>
  )
}
