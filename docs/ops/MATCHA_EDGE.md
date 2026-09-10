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
| `_budget(...)` per link, hourly | turn 40, upload 24, submit 6 |
| `_budget(...)` per company, hourly | turn 240, upload 200, submit 120 |
| `symlink_unlock_link` | 12 passcode attempts per link per hour |
| `IP_LIMITS` per IP | flood backstop only — see below |
| App body ceiling | 64 KiB JSON (`MAX_PUBLIC_CHAT_BODY_BYTES`), 10 MB per file |

Per-IP ceilings are deliberately loose. A bulk send — 20 credential requests to
one employer — puts a whole office behind a single NAT address, so a per-IP
ceiling that binds before the per-link budget just 429s legitimate recipients.
`tests/symlink/test_routes_smoke.py` asserts every hourly per-IP limit stays
above the matching per-link budget. Do not "harden" it by tightening those.

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

- `/unlock` — a passcode, at most 16 characters.
- `/chat/turn` — one message, capped at 600 characters client-side.

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

# 1. Snapshot. Keep rules-before.json until the change is verified — it IS the rollback.
aws wafv2 get-web-acl $ACL_ARGS --output json > acl-before.json
python3 -c "import json;json.dump(json.load(open('acl-before.json'))['WebACL']['Rules'],open('rules-before.json','w'),indent=2)"

# 2. Edit a copy into rules-after.json.

# 3. Apply. The lock token must be re-read immediately before the update.
aws wafv2 update-web-acl $ACL_ARGS \
  --description "$(python3 -c "import json;print(json.load(open('acl-before.json'))['WebACL']['Description'])")" \
  --default-action '{"Allow":{}}' \
  --visibility-config '{"SampledRequestsEnabled":true,"CloudWatchMetricsEnabled":true,"MetricName":"CappePublicEdge"}' \
  --rules file://rules-after.json \
  --lock-token "$(aws wafv2 get-web-acl $ACL_ARGS --query LockToken --output text)"
```

`update-web-acl` **replaces** the ACL. Any optional field omitted from the call
is dropped, so always carry `Description` (and `CustomResponseBodies`,
`CaptchaConfig`, `ChallengeConfig`, `TokenDomains`, `AssociationConfig` if they
are ever set) through from the snapshot.

## Verification

```bash
# Rules landed.
aws wafv2 get-web-acl $ACL_ARGS --query 'WebACL.Rules[].[Priority,Name]' --output text

# Real traffic classification, per rule, last 3 hours.
aws wafv2 get-sampled-requests $ACL_ARGS \
  --rule-metric-name BlockOversizedMatchaSymlinkJsonBodies \
  --time-window StartTime=$(date -u -v-3H +%s),EndTime=$(date -u +%s) \
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
aws wafv2 update-web-acl $ACL_ARGS \
  --description "<from snapshot>" \
  --default-action '{"Allow":{}}' \
  --visibility-config '{"SampledRequestsEnabled":true,"CloudWatchMetricsEnabled":true,"MetricName":"CappePublicEdge"}' \
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

## Known Gaps

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
