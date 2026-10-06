# Cappe payments — what happens after money moves

Runbook for the storefront (Stripe **Connect**) and platform (domains, plans)
money paths. The payment core — signature checks, event dedupe, `payment_status`
gating, connected-account ownership joins — is described in the code it lives
in (`routes/payments.py`, `routes/domains.py`). This file covers the parts that
need something done *outside* the code: Stripe dashboard configuration, the
migration, and what to check in test mode before trusting a path.

Background: the 2026-10 payments review. Every item below traces to a finding
in it.

## 1. Stripe dashboard — events that must be enabled

Nothing local can tell you an event type is not subscribed: the handler simply
never runs. Check both endpoints by hand.

**Connect endpoint** — `https://<app>/api/cappe/payments/webhook`
(secret `CAPPE_STRIPE_WEBHOOK_SECRET`; "Listen to events on Connected accounts")

| Event | What breaks without it |
|---|---|
| `checkout.session.completed` | no order is ever marked paid |
| `checkout.session.async_payment_succeeded` / `.async_payment_failed` | ACH/SEPA/Klarna orders never settle or release |
| `checkout.session.expired` | abandoned carts hold stock until the reaper (2h) |
| `charge.refunded` | **a refund made in the Stripe dashboard leaves the order `paid`**: download stays live, stock never returns, a collab installment stays `paid` |
| `charge.dispute.created` / `.updated` / `.closed` | a chargeback is invisible on the Orders page; a lost one never closes the order |
| `invoice.paid`, `invoice.payment_failed`, `customer.subscription.updated` / `.deleted` | shopper subscriptions |
| `account.updated` | "can accept card payments" goes stale |

**Platform endpoint** — `https://<app>/api/cappe/domains/webhook`
(secret `CAPPE_PLATFORM_WEBHOOK_SECRET`; events on **your** account)

| Event | What breaks without it |
|---|---|
| `checkout.session.completed`, `.async_payment_succeeded`, `.async_payment_failed` | domain purchases, manual domain renewals, plan checkout |
| `customer.subscription.created` / `.updated` / `.deleted` | **a "cancel at period end" never drops the plan** |
| `invoice.paid`, `invoice.payment_failed` | intro-trial → first real payment is never reconciled |
| `charge.refunded` | **a refunded domain keeps renewing** (ours and Porkbun's) |

## 2. Migration

`zzzzcappe38_payments_hardening` — additive columns on `cappe_orders`,
`cappe_collab_payments` and `cappe_domains`. `migrate-dev.sh`, then
`migrate-prod.sh`. The backend deploy refuses to swap while it is pending, and
the order list selects the new columns, so there is no "deploy first" order.

## 3. Verify in Stripe TEST mode before relying on it

These paths are covered by unit tests against a fake Stripe. None of them has
been run against the real API from this codebase. Do each once:

1. **Refund a storefront order** from the Orders page (card order, test card
   `4242…`). Expect: refund appears on the *connected* account with the
   application fee reversed; order → `refunded`; stock back. This is the one
   most worth checking — it depends on the platform being allowed to refund a
   direct charge on a Standard connected account (`refund_connected_charge`).
2. **Refund the same kind of order from the Stripe dashboard** instead. Expect
   the order to follow within seconds (needs `charge.refunded`, §1).
3. **Domain renewal.** Buy a test domain with card `4242…`, set its
   `expires_at` to a week out, enable the `cappe_domain_renewals` scheduler row
   and run the task. Expect `expires_at` +1 year and a succeeded PaymentIntent
   that names a payment method. Then repeat with a customer whose only card is
   `4000 0000 0000 0341` (attaches, then declines): expect one "Action needed"
   email, `renewal_failed_at` set, the domain still `active`.
4. **Renew by hand** — "Renew now" in the domain panel for that same domain,
   pay with a good card. Expect +1 year, failure fields cleared, and the new
   card stored for next time.
5. **Collab double pay.** Open checkout for an installment, open it again in a
   second tab, try to pay the FIRST tab. Expect Stripe to say the session
   expired. (If it somehow completes, the webhook refunds it — look for
   "refunded automatically" in Admin → Server Errors.)
6. **Declined upgrade.** With a subscription whose card is `4000 0000 0000
   0341`, change to a higher plan. Expect a 402 and the old plan, not a 200.

## 4. Behaviour worth knowing

- **`refunded` is an action.** `PATCH /orders/{id}` refuses it; only
  `POST /orders/{id}/refund` (which refunds at Stripe first) and the
  `charge.refunded` webhook reach it. An order paid outside Stripe is only
  *recorded* as refunded — the owner returns the money themselves, and the
  confirmation says so.
- **A refund never tears a live domain down.** It switches auto-renew off (ours
  and Porkbun's); the domain serves to the end of its term and then lapses
  like any other unrenewed domain.
- **A collab charge that cannot be applied is refunded automatically** on the
  creator's connected account — stale checkout tab, cancelled offer, or a
  session that is not the one we created for that installment. Each is an
  ERROR in Admin → Server Errors. "MANUAL REFUND REQUIRED" in that log means
  the automatic refund itself failed.
- **Dunning.** A refused renewal is retried every 3 days, the tenant is emailed
  once per cycle, and the domain lapses 7 days past expiry. A Stripe *outage*
  counts against nobody.
- **Stale manual orders.** A `pending` order that never went to Stripe (a store
  without Connect) and that nobody has accepted or touched for 7 days is
  cancelled and its stock returned by `cappe_order_reaper`.
- **Log lines to alert on:** `MANUAL REFUND REQUIRED`, `CANCEL IT MANUALLY`,
  `refund owed`.

## 5. Known gaps (deliberately not done)

- The $1 intro's card fingerprint is now **recorded and reported**, not
  enforced. Ending a trial the customer was shown at checkout would charge a
  price they did not agree to; what to do about serial sign-ups is a product
  decision.
- A refunded collab installment is marked `refunded` but the offer's own
  status is not rewound.
- Subscription storefront orders are refunded from the Stripe dashboard (the
  webhook syncs them); the Orders page has no button for them.
- The dashboard's settings forms still have no unsaved-changes guard.
