# Matcha Edge Protection

Edge posture for the **public token** surfaces on `hey-matcha.com` — sym-link
(`/sym/:token`) and IR magic links (`/report/:token`, `/intake/:token`). It is not
a deploy or migration procedure. Nothing here runs automatically.

The Cappe cutover runbook is `docs/ops/CAPPE_EDGE.md`; read it first, because
matcha now shares that distribution and that ACL.

## Current Topology

Verified 2026-09-09 with `aws cloudfront list-distributions` and
`aws wafv2 get-web-acl`. **One distribution fronts both product families:**

```text
E2DR5ZV7O32BE   dburfxi3p5e15.cloudfront.net
  aliases: gummfit.com, *.gummfit.com, hey-matcha.com, www.hey-matcha.com
  origin:  origin.gummfit.com  (54.177.107.107)
  WAF:     arn:aws:wafv2:us-east-1:010438494410:global/webacl/cappe-public-edge/22a33df3-77c4-492b-8a21-9c6b054a17d7
  origin custom headers: X-Cappe-Origin-Verify, X-Matcha-Origin-Verify
```

Two consequences that are easy to miss:

- The ACL is still **named** `cappe-public-edge`. It governs `hey-matcha.com`
  too. Editing it for Cappe reasons changes matcha's edge, and the reverse.
- `client_ip` (`core/services/redis_cache.py`) counts the CloudFront hop when
  **either** origin-verify header authenticates, so every matcha per-IP rate
  limit keys on the real viewer address. If the distributions are ever split,
  set `MATCHA_CLOUDFRONT_ORIGIN_SECRET` in the backend environment to the value
  of the new distribution's `X-Matcha-Origin-Verify` header — otherwise every
  per-IP limit silently starts keying on the CloudFront POP address, which
  buckets unrelated strangers together and exempts a real attacker.

## Where The Governors Live

**The WAF is a volumetric backstop, not the cost control.** For sym-link the real
governors are in the application, because only an authenticated sender can mint a
token:

| Layer | Bound |
|---|---|
| `chat.MAX_TURNS` | 20 model turns per link, absolute |
| `LINK_BUDGETS` per link, hourly | turn 40, upload 24, delete 24, submit 6, validate 60 |
| `LINK_BUDGETS` per company, hourly | turn 600, upload 200, delete 200, submit 120, validate 600 |
| `UNLOCK_PER_LINK_HOURLY` / `UNLOCK_FAILURES_PER_COMPANY_HOURLY` | 12 attempts per link; 100 *failed* attempts per company — per hour |
| `IP_LIMITS` per IP | flood backstop only — see below |
| App body ceiling | 64 KiB JSON (`MAX_PUBLIC_CHAT_BODY_BYTES`), 10 MB per file |

Per-IP ceilings are sized against one written-down design load, not tuned by
feel: `OFFICE_RECIPIENTS` (20) recipients of one bulk send, all behind one NAT
address, each finishing their whole task inside the hour (`PER_RECIPIENT_NEED`,
e.g. `chat.MAX_TURNS` turns each — 400 turns for the office). With every window
normalised to requests/hour, `tests/symlink/test_routes_smoke.py` asserts
per-link ≥ one recipient's need, per-IP ≥ the office's need, per-link < per-IP,
and per-company > per-IP. Every `IP_LIMITS` key must map to a kind, so none is
silently exempt. A 200/hr turn ceiling once 429'd exactly that office
mid-conversation; do not "harden" these without changing the design load.

Unlock is governed differently, on purpose: the passcode is company-wide, so a
per-company budget on unlock *attempts* would let anyone holding one leaked link
lock every legitimate recipient of the tenant out. Instead only **failed**
attempts count per company (100/hr, peeked before the verify so a correct code
never spends it). An office's typos stay far below it; an attacker holding many
leaked links gets at most 100 guesses per tenant per hour however many addresses
they use (against 32^6 ≈ 1.07e9 codes, rotated weekly). The price: that attacker
can block *new* unlocks for the tenant for up to an hour — already-unlocked
recipients keep working.

### nginx `limit_req` — the same CloudFront coupling as fail2ban

`deploy/nginx/matcha.conf` rate-limits before the app ever sees the request:

| Location | Zone | Rate |
|---|---|---|
| `/api/` | `matcha_api` | 20r/s, burst 40 |
| `/api/auth/` | `matcha_auth` | 30r/m, burst 20 |
| `/api/ws/` | `matcha_ws` | 8r/m, burst 10 |

The zones, together with `limit_req_status 429` and the `matcha_conn`
connection zone, are defined in `/etc/nginx/conf.d/00-matcha-limits.conf` — a
host-only file that is **not in this repo** (verified with `nginx -T`,
2026-09-11). Request bodies are capped by `client_max_body_size 20m` in the http
block of `/etc/nginx/nginx.conf`, also host-only; the sym-link upload path
inherits it (the app's own cap is 10 MB per file), as does the frontend
container's nginx (`client/nginx.conf`, 20m).

Every one of those zones is `limit_req_zone $binary_remote_addr` — and behind
CloudFront `$remote_addr` is the **POP address**, not the viewer's. The host also
sets `X-Real-IP $remote_addr`, so the frontend container's `real_ip_header`
resolves to the same POP. Only the application layer recovers the true viewer
address, via `client_ip()` reading `X-Forwarded-For` right-to-left past the
trusted proxy count. The same holds for `limit_conn matcha_conn 30`: thirty
concurrent connections **per POP**, shared by everyone routed through it.

So every matcha viewer routed through one edge location shares a single nginx
bucket. This is exactly the coupling that caused the 2026-09-10 outage below,
one layer down: **the origin must never treat its own CDN as a client.** The
current rate (20r/s per POP) is far above real per-POP traffic, so nothing is
tripping today — but it is shared-fate, and tightening it would blackhole a POP
for every user on it.

Every HTTPS server block in `matcha.conf` and `cappe.conf` routes nginx's own
429s to `@rate_limited`: a JSON body plus `Retry-After: 30` on `/api/`, nginx's
built-in 429 page elsewhere. `limit_req` already returned 429 host-wide via
`00-matcha-limits.conf`; the setting is repeated in each block only because
that file is not in the repo. The one that mattered was `limit_conn_status
429`, which nothing set: a tripped `limit_conn` returned 503, landed in
`error_page 502 503 504 = @maintenance`, and told the user "Server is
updating" — an outage misdiagnosis waiting to happen. Keep `error_page` at
server level; `deploy/nginx/README.md` has the inheritance rule that bit
cappe.conf. **These files are hand-applied** (`scp` per that README); confirm
a change is on the box.

**Not yet fixed:** making the nginx zones key per-viewer needs
`set_real_ip_from` for the CloudFront ranges plus `real_ip_header
X-Forwarded-For` in the host `http` block. Do not add it blind — get the ranges
from the managed prefix list, and verify on the box that a viewer cannot then
spoof `X-Forwarded-For` and escape the limiter entirely.

## Rules Covering Matcha

Priorities 5–8 of `cappe-public-edge`. Priorities 1–4 are the AWS managed
KnownBadInputs group (all paths, all hosts) and the Cappe booking-suggestion
rules.

| Priority | Name | Matches |
|---|---|---|
| 5 | `BlockOversizedMatchaIRChatBodies` | POST ∧ IR chat path ∧ body > 8192 |
| 6 | `RateLimitMatchaIRChat` | POST ∧ IR chat path, 20 / 300 s / IP |
| 7 | `BlockOversizedMatchaSymlinkJsonBodies` | POST ∧ sym-link JSON path ∧ body > 8192 |
| 8 | `RateLimitMatchaSymlinkFlood` | sym-link path, 2000 / 300 s / IP |

Regex pattern sets, all `scope=CLOUDFRONT` in `us-east-1`:

```text
matcha-ir-chat-path        7efec52e-5bf2-47e3-9a06-5bef0a3c7977
  ^/api/report/[^/]+/chat/turn$
  ^/api/intake/[^/]+/chat/turn$

matcha-symlink-json-path   175ab28c-0a6f-43a0-9ac5-25db26d6c7bd
  ^/api/sym/[^/]+/(unlock|chat/turn)$

matcha-symlink-path        9f6b8759-b575-4902-b830-50cdc5310b89
  ^/api/sym/[^/]+(/.*)?$
```

### Why the body rule is scoped to two endpoints

`OversizeHandling: MATCH` treats any body past CloudFront's 16 KB inspection
limit as a match. On an 8192-byte block rule that means **every** larger request
is blocked outright, so the rule may only cover endpoints whose legitimate
bodies are tiny:

- `/unlock` — `PublicUnlockRequest`: `passcode` ≤ 32 characters plus the honeypot
  `internal_ref` ≤ 200. A browser sends that as ≤ ~1 KB of UTF-8; a crafted client
  that `\u`-escapes every character tops out near 2.8 KB.
- `/chat/turn` — `PublicTurnRequest.message` ≤ 600 code points
  (`MAX_PUBLIC_CHAT_MESSAGE_CHARS`, enforced server-side). A browser sends ≤ 2.4 KB
  (4 UTF-8 bytes per astral character); a crafted client escaping every astral
  character as a surrogate pair (`\uD83D\uDE00`, 12 bytes) reaches **~7.2 KB —
  inside 8192 with under 1 KB to spare.** Below ~7.3 KB the WAF would reject bodies
  the app accepts; raising `MAX_PUBLIC_CHAT_MESSAGE_CHARS` means raising this rule.

It must **not** cover:

- `/submit` — the review-form fields JSON, which can legitimately approach the
  app's 64 KiB ceiling when a spec has several `long_text` fields.
- `/attachments` — multipart, up to 10 MB per file.

### Why the rate rule is loose

2000 requests per 5 minutes from one address is ~6.7 rps, far above any real
office and well below what would trouble the origin. It exists to shed a flood
before nginx and FastAPI spend a Redis round-trip on it. The tighter, correct
limits are the application's.

## Applying A Rule Change

Never hand-edit in the console — snapshot, edit JSON, update with the lock token.

```bash
ACL_ARGS="--scope CLOUDFRONT --region us-east-1 --name cappe-public-edge --id 22a33df3-77c4-492b-8a21-9c6b054a17d7"
# get-sampled-requests does NOT take --name/--id. It wants the ARN.
ACL_ARN="arn:aws:wafv2:us-east-1:010438494410:global/webacl/cappe-public-edge/22a33df3-77c4-492b-8a21-9c6b054a17d7"

# 1. Snapshot. Keep rules-before.json until the change is verified — it IS the rollback.
aws wafv2 get-web-acl $ACL_ARGS --output json > acl-before.json
python3 -c "import json;json.dump(json.load(open('acl-before.json'))['WebACL']['Rules'],open('rules-before.json','w'),indent=2)"

# Carry the optional fields through verbatim rather than retyping them (see below).
DESC="$(python3 -c "import json;print(json.load(open('acl-before.json'))['WebACL'].get('Description',''))")"
VIS="$(python3 -c "import json;print(json.dumps(json.load(open('acl-before.json'))['WebACL']['VisibilityConfig']))")"

# 2. Edit a copy into rules-after.json.

# 3. Apply. The lock token must be re-read immediately before the update.
aws wafv2 update-web-acl $ACL_ARGS \
  --description "$DESC" \
  --default-action '{"Allow":{}}' \
  --visibility-config "$VIS" \
  --rules file://rules-after.json \
  --lock-token "$(aws wafv2 get-web-acl $ACL_ARGS --query LockToken --output text)"
```

`update-web-acl` **replaces** the ACL. Any optional field omitted from the call
is dropped, so always carry `Description` (and `CustomResponseBodies`,
`CaptchaConfig`, `ChallengeConfig`, `TokenDomains`, `AssociationConfig` if they
are ever set) through from the snapshot. `VisibilityConfig` is on that list and
is the easiest one to get wrong by hand: retyping `MetricName` even slightly
differently orphans every existing CloudWatch metric and dashboard for this ACL,
so read it out of `acl-before.json` (`$VIS` above) instead of pasting a literal.

## Verification

```bash
# Rules landed.
aws wafv2 get-web-acl $ACL_ARGS --query 'WebACL.Rules[].[Priority,Name]' --output text

# Real traffic classification, per rule, last 3 hours.
# NOTE: --web-acl-arn, not the --name/--id in $ACL_ARGS. And `date -v` is
# BSD-only, so the window is computed in python — this block has to run on the
# Amazon Linux app EC2 as well as on a Mac.
NOW=$(python3 -c "import time;print(int(time.time()))")
aws wafv2 get-sampled-requests \
  --scope CLOUDFRONT --region us-east-1 \
  --web-acl-arn "$ACL_ARN" \
  --rule-metric-name BlockOversizedMatchaSymlinkJsonBodies \
  --time-window StartTime=$((NOW-10800)),EndTime=$NOW \
  --max-items 100
```

Then, end to end against a real link:

- A 10 MB credential upload to `/api/sym/<token>/attachments` still succeeds.
- A submit carrying several long_text fields still succeeds.
- Two recipients on one office network can each run a chat to completion without
  a 429.
- `RateLimitMatchaSymlinkFlood` shows no blocked samples during normal use.

## Rollback

```bash
# $DESC and $VIS come from acl-before.json exactly as in the apply block — a
# rollback that retypes them does not actually restore the ACL.
aws wafv2 update-web-acl $ACL_ARGS \
  --description "$DESC" \
  --default-action '{"Allow":{}}' \
  --visibility-config "$VIS" \
  --rules file://rules-before.json \
  --lock-token "$(aws wafv2 get-web-acl $ACL_ARGS --query LockToken --output text)"
```

A regex pattern set cannot be deleted while a rule references it. Remove the rule
first, then:

```bash
aws wafv2 delete-regex-pattern-set --scope CLOUDFRONT --region us-east-1 \
  --name matcha-symlink-json-path --id 175ab28c-0a6f-43a0-9ac5-25db26d6c7bd \
  --lock-token "$(aws wafv2 get-regex-pattern-set --scope CLOUDFRONT --region us-east-1 \
      --name matcha-symlink-json-path --id 175ab28c-0a6f-43a0-9ac5-25db26d6c7bd \
      --query LockToken --output text)"
```

## Origin-Side Banning — Incident 2026-09-10

**The origin must never ban its own CDN.** It did, and it cost a 13-minute
partial outage.

The host runs fail2ban. Its `nginx-404` jail read `/var/log/nginx/access.log`,
matched `^<HOST> -.*" (404|444) .*$`, and banned the **connecting** address with
an iptables REJECT on 80/443 for an hour. Since the CloudFront cutover, that
address is always a CloudFront edge server. A burst of 404s from WAF-rule
testing tripped it:

```text
06:12:38  POST /api/sym/testtoken123/unlock  → 404   (via CloudFront edge 130.176.22.74)
06:12:39  fail2ban.actions [nginx-404] Ban 130.176.22.74
06:26:03  fail2ban.actions [nginx-404] Unban 130.176.22.74   (manual)
```

Every viewer routed through the PHX52 POP got `504 Gateway Timeout` for those 13
minutes; other POPs were unaffected, which is what made it look client-specific.
It is not: an EC2 host on a completely different IP saw the same 504 through that
POP, while the origin access log showed unrelated users being served 200s
through other edges the entire time.

Scale of the false-positive problem, measured against AWS `ip-ranges.json`:

| Addresses the jail had ever banned | Count |
|---|---|
| Inside AWS CloudFront ranges | 140 |
| Everything else | 15 |

All 15 of the non-CloudFront bans are dated on or before **2026-08-21** — the day
the origin gates were installed. The jail caught nothing real in the ~20 days
after, and could not: its filter only matches 404/444, and the gate 403s a
direct-to-origin scanner before it can produce a 404.

**Resolution.** `[nginx-404]` is `enabled = false` in `/etc/fail2ban/jail.local`
as of 2026-09-10, with the reasoning inline in that file. `sshd` (port 22, sees
real client IPs) and `nginx-http-auth` are untouched and still run.

**The coupling this creates.** Disabling the jail costs us protection against
direct-to-origin 404 scanners. That is real, but currently worth zero, because
the gate already 403s them. It only regains value if the gate is ever turned off.
So a change that disables, bypasses, or fails to reinstall
`/etc/nginx/snippets/{matcha,cappe}-cloudfront-origin-gate.conf` must replace the
protection in the same change — re-enable the jail *with* CloudFront ranges in
`ignoreip`, or cover it at the WAF. Root `CLAUDE.md` carries the short form of
this warning next to the blue-green rule.

**If it happens again** (symptom: 504 from some POPs, 200 from others, origin
healthy):

```bash
sudo fail2ban-client status nginx-404          # is anything banned?
sudo iptables -L f2b-nginx-404 -n              # the REJECT rules
sudo fail2ban-client set nginx-404 unbanip <CLOUDFRONT_IP>
```

Anything in `3.172.*`, `18.68.*`, `15.158.*`, `52.46.*`, `130.176.*` is a
CloudFront edge, not an attacker. Confirm with
`https://ip-ranges.amazonaws.com/ip-ranges.json`, service `CLOUDFRONT`.

Three other jails (`nginx-noscript`, `nginx-badbots`, `nginx-noproxy`) are marked
enabled but have never run — their filter files were never installed on this
host, so fail2ban skips them at startup. Do not count them as protection.

## Known Gaps

- **The oversized-body rules do not actually fire, and never have.** Verified
  2026-09-10 against live traffic: 12 KB and 30 KB POSTs (with `Expect:
  100-continue` disabled so the body is really transmitted) to
  `/api/sym/<token>/unlock` and to both IR chat paths all reached the origin
  instead of being blocked, while control requests carrying a Log4j signature or
  hitting `/web-inf/web.xml` returned 403 instantly — so the ACL is definitely
  evaluating the traffic. No per-rule CloudWatch metric has ever existed for any
  of the four body/rate rules on this ACL, which fits: none has ever matched.
  The shared three-clause AND shape (`uri regex` ∧ `SizeConstraint Body > 8192`
  ∧ `Method EXACTLY POST`) is wrong somewhere, and it is wrong for the Cappe and
  IR rules too, not just the sym-link one. To isolate it, add two temporary
  **Count**-mode rules — one matching the URI regex alone, one the body size
  alone — send a test request, read `get-sampled-requests` to see which clause
  fails, then remove them. Count blocks nothing, so this is safe on the live ACL.
  Until that is resolved, treat the 8 KiB ceilings as unenforced and rely on the
  application's own body caps.
- **IR public writes are edge-uncovered.** Only the two chat-turn endpoints are
  in `matcha-ir-chat-path`. `POST /api/report/{token}`, `POST /api/intake/{token}`,
  and both `/voice/parse` endpoints have no targeted rule — and voice-parse takes
  an audio upload and calls Gemini. Application limits are the only guard there
  (`ir_voice_parse_public` 40/hr per IP).
- **The ACL name is misleading.** `cappe-public-edge` governs matcha as well.
  Renaming means recreating the ACL and re-associating the distribution.
- **No AWS-managed common rule set.** Only KnownBadInputs is enabled. Adding
  `AWSManagedRulesCommonRuleSet` needs a count-mode soak first — its SQLi/LFI
  body rules have a history of flagging legitimate prose, which is exactly what
  an incident narrative is.
