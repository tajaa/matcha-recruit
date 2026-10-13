# Espresso sales campaigns

In a collab workspace, open **Kanban → Pipeline**. **Manual deals** opens the
previous ticket-based deal board; ordinary tasks no longer appear as leads.
All board columns retain 240-point width and single-line headers, including empty
Done columns. Narrow panes still stack columns vertically.

## Use

1. Create a campaign with a target audience and the offer/call to action.
2. Import CSV/TSV or paste one email per line (1 MB input, 1,000 prospects per
   campaign). Supported headers: `email,name,company,website,notes`. Quoted fields,
   escaped quotes, multiline notes, BOM and CRLF are supported. Malformed rows
   reject the import; existing campaign emails are skipped. Leads without an
   email can be saved for later research.
3. **Research and draft with Espresso** opens a new named private session with
   campaign/workspace identifiers prefilled. Enable **Sales** in Espresso's
   abilities and send the request. Espresso uses the existing web tools to find
   prospects and research their own public sites, saves source links and writes
   individual drafts. It works in bounded chat runs; ask it to continue the same
   campaign for remaining prospects. It does not autonomously research 1,000
   people in a single run. Never infer an email from a person's name.
4. Alternatively, **Draft with template** renders `{{name}}`, `{{company}}`,
   `{{research}}`, `{{website}}` for all editable prospects. It explicitly replaces
   existing editable drafts; approved, in-progress, sent and unconfirmed messages
   stay frozen. Review rendered drafts for missing contact fields.
5. Open a prospect to read research/sources, edit its email/draft or change stage.
   Select drafts, **Review and send**, check the sender and every message, then
   explicitly approve the batch. Each recipient gets one individual email.

Campaigns are private to their creating user within the workspace. They never
appear in another collaborator's campaign list or use that collaborator's Gmail.
Research/drafting needs a personal Espresso assistant account and the Sales AI
disclosure. Manual imports, templates and review/send do not require AI consent.
The desktop provides campaign review/send; the web assistant can work on the
same saved campaigns, but its old pipeline has no campaign review interface.

## Delivery and recovery

`mw_sales_campaigns` serializes imports/edits/queue transitions with row locks.
`mw_sales_prospects` stores stages, sourced research, drafts and per-recipient
outcomes. Migration `mwsales01` follows `mwcal02`; no existing rows change.
Downgrade drops both new tables and their campaign history. Do not downgrade
while deliveries are in flight. Roll out the migration before API/worker code.
Register `app.workers.tasks.sales_campaign` in the worker include list and restart
workers as part of the approved deployment. No provider environment variables or
Google scopes are added: existing user Gmail compose access is used.

Sending preserves existing Gmail ceilings (5 messages/minute, 50/hour,
100 recipients/hour, 200/day), shared with other email features. The queue paces
messages every 15 seconds and waits on quota failures: one minute for minute
limits, an hour for hour/day limits, rechecking until capacity returns. A batch
of hundreds therefore takes hours or days. Progress is saved server-side and
continues after closing the app. Counts refresh every 15 seconds while open.

The worker checks current account activity, workspace access/editor role and the
frozen Gmail sender before each delivery. It claims a message durably before the
provider call. HTTP 4xx refusals are definite failures; transport errors, HTTP
5xx, missing acknowledgment or expired claims are **unconfirmed** and never
replayed automatically. Provider success followed by a database failure leaves
the claim intact. After ten minutes, queue recovery marks it unconfirmed.

**Pause** stops future claims; a message already claimed may finish.
**Resume / Recover queue** redispatches approved pending messages with a new
queue token, without replaying active or uncertain claims. Use it if a worker
crashes before scheduling the next message. Broker dispatch failures pause the
campaign and retain approvals. **Release pending drafts** pauses the batch and
unfreezes only messages not yet claimed. **Review failed again** returns definite
failures to draft; sending them needs another review. Check Gmail Sent manually
for unconfirmed messages before contacting those recipients again.

Reserved RFC test recipients are blocked before delivery. No test or validation
command sends actual email or applies a migration to a live database.
