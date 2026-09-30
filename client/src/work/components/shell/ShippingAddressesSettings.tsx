import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Loader2, MapPin, Plus, Star, Trash2 } from 'lucide-react'
import {
  addShippingAddress,
  agentErrorMessage,
  deleteShippingAddress,
  listShippingAddresses,
  updateShippingAddress,
} from '../../api/matchaWork'
import type { PostalAddress, ShippingAddress } from '../../types'
import AddressFields from './AddressFields'
import { EMPTY_ADDRESS, addressLine, useScrollToHash } from './addressHelpers'

const MAX_ADDRESSES = 5

function fields(a: ShippingAddress): PostalAddress {
  const { name, line1, line2, city, region, postal_code, country, phone } = a
  return { name, line1, line2, city, region, postal_code, country, phone }
}

/**
 * Where Espresso ships something it buys for you. The default is used unless
 * you name another in chat. Shown to the same accounts as Payment cards.
 */
export default function ShippingAddressesSettings({ isAdmin = false }: { isAdmin?: boolean }) {
  const [state, setState] = useState<{ enabled: boolean; addresses: ShippingAddress[] } | null>(null)
  const [draft, setDraft] = useState<PostalAddress>(EMPTY_ADDRESS)
  const [editing, setEditing] = useState<string | 'new' | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  const load = useCallback(async () => {
    try {
      setState(await listShippingAddresses())
    } catch (e) {
      setMessage(agentErrorMessage(e))
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- async fetch; state is set after it resolves
    void load()
  }, [load])
  useScrollToHash('shipping-addresses', state !== null)

  function startNew() {
    setDraft(EMPTY_ADDRESS)
    setEditing('new')
    setMessage('')
  }

  function startEdit(address: ShippingAddress) {
    setDraft(fields(address))
    setEditing(address.id)
    setMessage('')
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setMessage('')
    try {
      const body = { ...draft, country: draft.country.trim().toUpperCase() }
      if (editing === 'new') await addShippingAddress(body)
      else if (editing) await updateShippingAddress(editing, body)
      setEditing(null)
      setMessage('Address saved.')
      await load()
    } catch (e) {
      setMessage(agentErrorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function makeDefault(address: ShippingAddress) {
    setMessage('')
    try {
      await updateShippingAddress(address.id, { ...fields(address), is_default: true })
      await load()
    } catch (e) {
      setMessage(agentErrorMessage(e))
    }
  }

  async function remove(address: ShippingAddress) {
    setMessage('')
    try {
      await deleteShippingAddress(address.id)
      if (editing === address.id) setEditing(null)
      await load()
    } catch (e) {
      setMessage(agentErrorMessage(e))
    }
  }

  if (!state) {
    if (!isAdmin) return null
    return (
      <section id="shipping-addresses" className="rounded-xl border border-w-line bg-w-surface p-5">
        <h2 className="mb-1 flex items-center gap-2 text-sm font-semibold text-w-text">
          <MapPin className="h-4 w-4" /> Shipping addresses
        </h2>
        {message ? (
          <div className="flex items-center gap-3">
            <p role="status" className="text-xs text-orange-300">Couldn't load your addresses: {message}</p>
            <button
              type="button"
              onClick={() => { setMessage(''); void load() }}
              className="rounded-md border border-w-line px-2 py-1 text-xs text-w-text hover:bg-w-surface2"
            >
              Retry
            </button>
          </div>
        ) : (
          <Loader2 className="h-4 w-4 animate-spin text-w-dim" />
        )}
      </section>
    )
  }
  if (!state.enabled && state.addresses.length === 0) return null

  return (
    <section id="shipping-addresses" className="rounded-xl border border-w-line bg-w-surface p-5">
      <h2 className="mb-1 flex items-center gap-2 text-sm font-semibold text-w-text">
        <MapPin className="h-4 w-4" /> Shipping addresses
      </h2>
      <p className="mb-4 text-xs text-w-dim">
        Where Espresso ships what it buys for you. It uses your default unless you name another, and always shows
        the address before buying.
      </p>

      {state.addresses.length > 0 && (
        <ul className="mb-4 divide-y divide-w-line rounded-lg border border-w-line">
          {state.addresses.map((address) => (
            <li key={address.id} className="flex items-start justify-between gap-2 px-3 py-2 text-sm">
              <span className="min-w-0 text-w-text">
                {addressLine(address)}
                {address.is_default && (
                  <span className="ml-2 rounded-full bg-w-accent/15 px-2 py-0.5 text-[10px] font-semibold text-w-accent">
                    Default
                  </span>
                )}
              </span>
              <span className="flex shrink-0 items-center gap-1">
                {!address.is_default && state.enabled && (
                  <button
                    type="button"
                    onClick={() => void makeDefault(address)}
                    aria-label={`Make ${address.line1} the default`}
                    className="rounded p-1 text-w-dim hover:bg-w-surface2 hover:text-w-text"
                  >
                    <Star className="h-3.5 w-3.5" />
                  </button>
                )}
                {state.enabled && (
                  <button
                    type="button"
                    onClick={() => startEdit(address)}
                    className="rounded px-1.5 py-0.5 text-xs text-w-dim hover:bg-w-surface2 hover:text-w-text"
                  >
                    Edit
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => void remove(address)}
                  aria-label={`Remove address ${address.line1}`}
                  className="rounded p-1 text-w-dim hover:bg-w-surface2 hover:text-w-text"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}

      {state.enabled && editing === null && state.addresses.length < MAX_ADDRESSES && (
        <button
          type="button"
          onClick={startNew}
          className="inline-flex items-center gap-1.5 rounded-md border border-w-line px-3 py-2 text-xs text-w-text hover:bg-w-surface2"
        >
          <Plus className="h-3.5 w-3.5" /> Add an address
        </button>
      )}
      {state.enabled && editing !== null && (
        <form onSubmit={(event) => void save(event)} className="space-y-3">
          <AddressFields value={draft} onChange={setDraft} idPrefix="ship" />
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={busy}
              className="rounded-md bg-w-accent px-3 py-2 text-xs font-semibold text-w-on-accent disabled:opacity-50"
            >
              {busy ? 'Saving…' : 'Save address'}
            </button>
            <button
              type="button"
              onClick={() => setEditing(null)}
              className="rounded-md border border-w-line px-3 py-2 text-xs text-w-text hover:bg-w-surface2"
            >
              Cancel
            </button>
          </div>
        </form>
      )}
      {message && (
        <p role="status" className="mt-3 text-xs text-w-dim">
          {message}
        </p>
      )}
    </section>
  )
}
