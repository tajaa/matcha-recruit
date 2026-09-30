import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { CreditCard, Loader2, Trash2 } from 'lucide-react'
import {
  addPaymentCard,
  agentErrorMessage,
  deletePaymentCard,
  listPaymentCards,
  setCardBillingAddress,
} from '../../api/matchaWork'
import type { PaymentCard, PostalAddress } from '../../types'
import AddressFields from './AddressFields'
import { EMPTY_ADDRESS, addressLine, useScrollToHash } from './addressHelpers'

/** Change where one saved card bills to: its own address, or the shipping
 *  address. Cards saved before billing addresses existed start as "same as
 *  shipping" and can be given their own here without re-adding them. */
function CardBillingEditor({
  card, onSaved, onCancel,
}: { card: PaymentCard; onSaved: () => Promise<void>; onCancel: () => void }) {
  const [same, setSame] = useState(!card.billing_address)
  const [address, setAddress] = useState<PostalAddress>(card.billing_address ?? EMPTY_ADDRESS)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await setCardBillingAddress(card.id, same ? null : { ...address, country: address.country.trim().toUpperCase() })
      await onSaved()
    } catch (e) {
      setError(agentErrorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} className="mt-2 space-y-3 rounded-lg border border-w-line p-3">
      <label className="flex items-center gap-2 text-xs text-w-dim">
        <input type="checkbox" checked={same} onChange={(event) => setSame(event.target.checked)} className="accent-[var(--color-w-accent)]" />
        Billing address is the same as shipping
      </label>
      {!same && <AddressFields value={address} onChange={setAddress} idPrefix={`card-${card.id}-billing`} />}
      <div className="flex gap-2">
        <button type="submit" disabled={busy} className="rounded-md bg-w-accent px-3 py-1.5 text-xs font-semibold text-w-on-accent disabled:opacity-50">
          {busy ? 'Saving…' : 'Save billing address'}
        </button>
        <button type="button" onClick={onCancel} className="rounded-md border border-w-line px-3 py-1.5 text-xs text-w-text hover:bg-w-surface2">
          Cancel
        </button>
      </div>
      {error && <p role="status" className="text-xs text-orange-300">{error}</p>}
    </form>
  )
}

const BRAND: Record<PaymentCard['brand'], string> = {
  visa: 'Visa',
  mastercard: 'Mastercard',
  amex: 'Amex',
  discover: 'Discover',
  card: 'Card',
}

/**
 * Saved cards for purchases: agent-card buys in a project chat ("want me to
 * buy it?", then a card by its last 4) and the Espresso assistant ("buy it"
 * in your private conversation, confirmed on a card before anything happens).
 *
 * The number is sent once and never shown again. There is no security-code
 * field, and card numbers never go through chat. A card bills to your
 * shipping address unless you give it its own billing address.
 */
export default function PaymentCardsSettings({ isAdmin = false }: { isAdmin?: boolean }) {
  const [state, setState] = useState<{ enabled: boolean; configured: boolean; cards: PaymentCard[] } | null>(null)
  const [number, setNumber] = useState('')
  const [expiry, setExpiry] = useState('')
  const [label, setLabel] = useState('')
  const [sameAsShipping, setSameAsShipping] = useState(true)
  const [billing, setBilling] = useState<PostalAddress>(EMPTY_ADDRESS)
  const [editingBilling, setEditingBilling] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  const load = useCallback(async () => {
    try {
      setState(await listPaymentCards())
    } catch (e) {
      setMessage(agentErrorMessage(e))
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- async fetch; state is set after it resolves
    void load()
  }, [load])
  useScrollToHash('payment-cards', state !== null)

  async function save(event: FormEvent) {
    event.preventDefault()
    const match = /^\s*(\d{1,2})\s*\/\s*(\d{2}|\d{4})\s*$/.exec(expiry)
    if (!match) {
      setMessage('Enter the expiry as MM/YY.')
      return
    }
    const year = Number(match[2].length === 2 ? `20${match[2]}` : match[2])
    setBusy(true)
    setMessage('')
    try {
      await addPaymentCard({
        number, exp_month: Number(match[1]), exp_year: year, label,
        ...(sameAsShipping ? {} : { billing_address: { ...billing, country: billing.country.trim().toUpperCase() } }),
      })
      setNumber('')
      setExpiry('')
      setLabel('')
      setSameAsShipping(true)
      setBilling(EMPTY_ADDRESS)
      setMessage('Card saved.')
      await load()
    } catch (e) {
      setMessage(agentErrorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function remove(card: PaymentCard) {
    setMessage('')
    try {
      await deletePaymentCard(card.id)
      await load()
    } catch (e) {
      setMessage(agentErrorMessage(e))
    }
  }

  if (!state) {
    // Whether this account can buy isn't known until the list loads, so only
    // admins (who always can) see the loading/error state; a failed load says
    // so instead of making the section silently disappear.
    if (!isAdmin) return null
    return (
      <section id="payment-cards" className="rounded-xl border border-w-line bg-w-surface p-5">
        <h2 className="mb-1 flex items-center gap-2 text-sm font-semibold text-w-text">
          <CreditCard className="h-4 w-4" /> Payment cards
        </h2>
        {message ? (
          <div className="flex items-center gap-3">
            <p role="status" className="text-xs text-orange-300">Couldn't load your cards: {message}</p>
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
  if (!state.enabled && state.cards.length === 0) return null

  const input = 'mt-1 block w-full rounded-md border border-w-line bg-w-bg px-3 py-2 text-sm text-w-text outline-none focus:border-w-accent'
  return (
    <section id="payment-cards" className="rounded-xl border border-w-line bg-w-surface p-5">
      <h2 className="mb-1 flex items-center gap-2 text-sm font-semibold text-w-text">
        <CreditCard className="h-4 w-4" /> Payment cards
      </h2>
      <p className="mb-4 text-xs text-w-dim">
        For purchases Espresso makes for you. It always shows the card, item and address and waits for your yes.
        Numbers are encrypted and never shown again. Never paste a card number in chat.
      </p>

      {state.cards.length > 0 && (
        <ul className="mb-4 divide-y divide-w-line rounded-lg border border-w-line">
          {state.cards.map((card) => (
            <li key={card.id} className="px-3 py-2 text-sm">
              <div className="flex items-center justify-between gap-2">
                <span className="text-w-text">
                  {BRAND[card.brand] ?? 'Card'} ending {card.last4}
                  {card.label && <span className="text-w-dim"> · {card.label}</span>}
                  <span className="text-xs text-w-faint">
                    {' '}
                    · {String(card.exp_month).padStart(2, '0')}/{String(card.exp_year).slice(-2)}
                  </span>
                  <span className="block text-xs text-w-faint">
                    Bills to {card.billing_address ? addressLine(card.billing_address) : 'your shipping address'}
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-1">
                  {state.enabled && editingBilling !== card.id && (
                    <button
                      type="button"
                      onClick={() => { setMessage(''); setEditingBilling(card.id) }}
                      aria-label={`Change billing address for card ending ${card.last4}`}
                      className="rounded px-1.5 py-0.5 text-xs text-w-dim hover:bg-w-surface2 hover:text-w-text"
                    >
                      Billing
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => void remove(card)}
                    aria-label={`Remove card ending ${card.last4}`}
                    className="rounded p-1 text-w-dim hover:bg-w-surface2 hover:text-w-text"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </span>
              </div>
              {editingBilling === card.id && (
                <CardBillingEditor
                  card={card}
                  onCancel={() => setEditingBilling(null)}
                  onSaved={async () => { setEditingBilling(null); setMessage('Billing address saved.'); await load() }}
                />
              )}
            </li>
          ))}
        </ul>
      )}

      {state.enabled && !state.configured && (
        <p className="text-xs text-orange-300">Card storage isn't set up on this server yet.</p>
      )}
      {state.enabled && state.configured && (
        <form onSubmit={(event) => void save(event)} className="grid gap-3 sm:grid-cols-[1fr_7rem]">
          <label className="block text-xs text-w-dim sm:col-span-2">
            Card number
            <input
              value={number}
              onChange={(event) => setNumber(event.target.value)}
              inputMode="numeric"
              autoComplete="cc-number"
              required
              className={input}
            />
          </label>
          <label className="block text-xs text-w-dim">
            Label (optional)
            <input value={label} onChange={(event) => setLabel(event.target.value)} maxLength={40} className={input} />
          </label>
          <label className="block text-xs text-w-dim">
            Expiry
            <input
              value={expiry}
              onChange={(event) => setExpiry(event.target.value)}
              placeholder="MM/YY"
              autoComplete="cc-exp"
              required
              className={input}
            />
          </label>
          <label className="flex items-center gap-2 text-xs text-w-dim sm:col-span-2">
            <input
              type="checkbox"
              checked={sameAsShipping}
              onChange={(event) => setSameAsShipping(event.target.checked)}
              className="accent-[var(--color-w-accent)]"
            />
            Billing address is the same as shipping
          </label>
          {!sameAsShipping && (
            <div className="sm:col-span-2">
              <AddressFields value={billing} onChange={setBilling} idPrefix="billing" />
            </div>
          )}
          <div className="sm:col-span-2">
            <button
              type="submit"
              disabled={busy}
              className="rounded-md bg-w-accent px-3 py-2 text-xs font-semibold text-w-on-accent disabled:opacity-50"
            >
              {busy ? 'Saving…' : 'Save card'}
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
