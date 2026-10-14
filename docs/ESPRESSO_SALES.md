# Espresso sales campaigns

In a collab workspace, open **Kanban → Pipeline**. The chip next to the mode picker
switches between **Campaigns** and **Manual deals** (the previous ticket-based deal
board); the choice is remembered, and a project that already has deals opens on
Manual deals. Ordinary tasks no longer appear as leads. All board columns keep a
240-point width and single-line headers, including empty Done columns. Narrow
panes still stack columns vertically.

## Use

1. Create a campaign with a target audience and the offer/call to action. Open
   **Settings** and write the **footer**: how to opt out (for example "reply
   unsubscribe") and your business's postal address. Commercial email needs both,
   so a campaign can't send until the footer is filled in.
2. Import CSV/TSV or paste one email per line (1 MB input, 1,000 prospects per
   campaign). Recognised headers: `email`, `name`, `company`, `website`, `notes`,
   plus common CRM spellings (`Email Address`, `First Name` + `Last Name`,
   `Company Name`, `Website URL`, …). Other columns are ignored. Quoted fields,
   escaped quotes, multiline notes, BOM and CRLF are supported. Malformed rows
   reject the import; existing campaign emails and anyone marked **Do not
   contact** are skipped. Leads without an email can be saved for later research.
3. **Research and draft with Espresso** opens a new named private session with
   campaign/workspace identifiers prefilled. Enable **Sales** in Espresso's
   abilities and send the request. Espresso uses the existing web tools to find
   prospects and research their own public sites, saves source links and writes
   individual drafts. It only saves an email address you typed, or one printed on
   a page it fetched in that run; it never guesses one. It works in bounded chat
   runs; ask it to continue the same campaign for remaining prospects.
4. Alternatively, **Draft with template** renders `{{name}}`, `{{company}}`,
   `{{research}}`, `{{website}}` for all editable prospects. From the desktop it
   explicitly replaces existing editable drafts. When Espresso uses a template
   (only when you ask for one) it fills only prospects that have no draft yet.
   Approved, in-progress, sent, unconfirmed and opted-out messages stay frozen.
5. Open a prospect to read research/sources, edit its email/draft or change stage.
   Select up to 50 drafts, **Review and send**, check the sender and every message
   (body and footer), then approve the batch. Each recipient gets one individual
   email.
6. When someone asks to be left alone, open them and choose **Do not contact**.
   The address joins your suppression list: every campaign you run skips it, at
   import, at approval and right before sending. **Delete** removes a prospect or
   a whole campaign (not while a message is in progress); the suppression entry is
   kept so the opt-out is still honoured.

Campaigns are private to their creating user within the workspace. Other editors
see a summary of them (title, creator, status, counts) under **Other campaigns in
this workspace**, never their contacts or drafts. Viewers see neither. A campaign
never uses another collaborator's Gmail. Research/drafting needs a personal
Espresso assistant account and the Sales AI disclosure. Manual imports, templates
and review/send do not require AI consent. The desktop provides campaign
review/send; the web assistant can work on the same saved campaigns, but its old
pipeline has no campaign review interface.

## Delivery and recovery

`mw_sales_campaigns` serializes imports/edits/queue transitions with row locks;
reads don't lock. `mw_sales_prospects` stores stages, sourced research, drafts and
per-recipient outcomes. `mw_sales_suppressions` is the per-sender do-not-contact
list. Migrations: `mwsales01` (follows `mwcal02`) adds the two campaign tables;
`mwsales02` adds the suppression table, the campaign footer and the `opted_out`
status. Neither changes existing rows. Downgrading `mwsales02` turns opted-out
prospects back into prospects and drops the suppression list; downgrading
`mwsales01` drops campaign history. Do not downgrade while deliveries are in
flight. Roll out the migrations before API/worker code and restart workers with
the registered sales tasks. No provider environment variables or Google scopes
are added: existing user Gmail compose access is used.

Gmail's per-person ceilings (5 messages/minute, 50/hour, 100 recipients/hour,
200/day) are shared with every other email feature. A campaign uses at most
**35 sends/hour and 150 recipients/day** of them, so you can still reply to the
people who answer. The queue paces messages every 15 seconds and waits when the
campaign's share is spent or Gmail says it is rate-limiting. A batch of hundreds
therefore takes days. Progress is saved server-side and continues after closing
the app. The app polls a light status every 15 seconds and reloads full drafts
only when something changed.

The worker checks current account activity, workspace access/editor role, the
suppression list and the frozen Gmail sender before each delivery. It claims a
message durably before the provider call. What happens next depends on Gmail's
answer:

| Gmail answer | Recipient | Campaign |
|---|---|---|
| Message id | sent | continues |
| 400-type refusal of this message | failed | continues |
| 429, or 403 rate/quota reason | stays approved | waits, then continues |
| 401, other 403 | stays approved | **pauses**: reconnect Gmail, then Resume |
| 5xx, transport error, no id, expired claim | **unconfirmed** | **pauses** |
| Reserved test address | failed | continues |

Unconfirmed messages are never replayed automatically, and the pause means one
Gmail incident costs at most one of them. Check Gmail Sent, then mark the message
**Mark sent** or **Not sent: redraft** (which needs a new review), and Resume.
Provider success followed by a database failure leaves the claim intact; after
ten minutes it becomes unconfirmed.

**Pause** stops future claims; a message already claimed may finish.
**Resume / Recover queue** redispatches approved pending messages with a new
queue token. Every worker start also does this for each sending campaign, so a
worker killed mid-chain doesn't leave a campaign stuck on Sending. Long waits are
split into countdowns under the broker's one-hour visibility timeout, so a wait
never duplicates the queue. Broker dispatch failures pause the campaign and
retain approvals. **Release pending drafts** pauses the batch and unfreezes only
messages not yet claimed. **Review failed again** returns definite failures to
draft; sending them needs another review. The footer can't change while approved
messages are pending, because it is part of what was reviewed.

No test or validation command sends actual email or applies a migration to a live
database. `tests/matcha_work/test_sales_realdb.py` exercises the queue against a
real Postgres inside a rolled-back transaction; run it manually against local dev
after applying the migrations.
