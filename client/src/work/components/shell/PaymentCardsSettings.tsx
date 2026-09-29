import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { CreditCard, Loader2, Trash2 } from 'lucide-react'
import {
  addPaymentCard,
  agentErrorMessage,
  deletePaymentCard,
  listPaymentCards,
} from '../../api/matchaWork'
import type { PaymentCard } from '../../types'

const BRAND: Record<PaymentCard['brand'], string> = {
  visa: 'Visa',
  mastercard: 'Mastercard',
  amex: 'Amex',
  discover: 'Discover',
  card: 'Card',
}

/**
 * Saved cards for agent-card purchases. When Espresso asks "want me to buy
 * it?" in a project chat, you pick one of these by its last 4 digits.
 *
 * The number is sent once and never shown again. There is no security-code
 * field, and card numbers never go through chat.
 */
export default function PaymentCardsSettings({ isAdmin = false }: { isAdmin?: boolean }) {
  const [state, setState] = useState<{ enabled: boolean; configured: boolean; cards: PaymentCard[] } | null>(null)
  const [number, setNumber] = useState('')
  const [expiry, setExpiry] = useState('')
  const [label, setLabel] = useState('')
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
      await addPaymentCard({ number, exp_month: Number(match[1]), exp_year: year, label })
      setNumber('')
      setExpiry('')
      setLabel('')
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
      <section className="rounded-xl border border-w-line bg-w-surface p-5">
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
    <section className="rounded-xl border border-w-line bg-w-surface p-5">
      <h2 className="mb-1 flex items-center gap-2 text-sm font-semibold text-w-text">
        <CreditCard className="h-4 w-4" /> Payment cards
      </h2>
      <p className="mb-4 text-xs text-w-dim">
        For agent-card purchases. When Espresso asks in a project chat whether to buy something, reply with a card's
        last 4 digits. Numbers are encrypted and never shown again. Never paste a card number in chat.
      </p>

      {state.cards.length > 0 && (
        <ul className="mb-4 divide-y divide-w-line rounded-lg border border-w-line">
          {state.cards.map((card) => (
            <li key={card.id} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
              <span className="text-w-text">
                {BRAND[card.brand] ?? 'Card'} ending {card.last4}
                {card.label && <span className="text-w-dim"> · {card.label}</span>}
                <span className="text-xs text-w-faint">
                  {' '}
                  · {String(card.exp_month).padStart(2, '0')}/{String(card.exp_year).slice(-2)}
                </span>
              </span>
              <button
                type="button"
                onClick={() => void remove(card)}
                aria-label={`Remove card ending ${card.last4}`}
                className="rounded p-1 text-w-dim hover:bg-w-surface2 hover:text-w-text"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
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
