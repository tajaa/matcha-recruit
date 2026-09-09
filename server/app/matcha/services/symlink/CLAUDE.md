# Sym-link — feature spec

Root `CLAUDE.md` keeps a one-line summary + `→ full spec:` pointer here. Default matches `DEFAULT_COMPANY_FEATURES["symlink"]` (❌).

## `symlink` (default ❌)

**Bounded, guided task links.** A sender picks a kind (`credential_upload` / `manager_review` / `info_update` / `custom`), names a recipient, and sends a per-task link (`/sym/{token}`). The recipient unlocks it with the company's **weekly-rotating passcode**, and a Gemini "tunnel chat" (`chat.py` — the same stateless-turn shape as `services/ir/ir_chat_intake.py`) asks one question at a time until every required field + attachment in the link's *spec* is collected, then lands on an editable review step. Submitting **stages** a `symlink_submissions` row; the sender applies or rejects it from `/app/symlink/<id>`. Nothing is written to a domain table until Apply.

Separate from IR on purpose: own flag, own tables (migration `symlink01`), own routers (`routes/symlink.py` at `/symlink`, gated; `routes/intake/symlink_public.py` public, token-validated), own sidebar entry. Reuses the IR public-route hardening pattern, `_shared/uploads.read_upload_capped`, `storage.upload_private_file`, and `PublicPageShell` on the client. Default off; admin-toggle; NOT in any tier overlay; composable in `/admin/products`.

### Invariants

- **Completion is deterministic.** `chat.is_complete(fields, present_slots, spec)` looks only at required fields + required attachment slots. The model proposes values and the next question; it never decides "done" and never submits. `submissions.stage` re-runs the check server-side, so a hand-edited review form can't skip an item.
- **A turn only adds or refines.** `chat.coerce_fields` never blanks a known value and drops keys not in the spec (mirrors `_coerce_public_chat_fields`).
- **Confirm-first.** `submissions.apply` is the sole path into a domain table and re-asserts role ∈ {client, admin} + the `symlink` flag per call (`evaluate_apply`, same posture as `huume/actions.py:evaluate_huume_action`). Per kind: `credential_upload` copies the S3 object into `employee-credentials/{company}/{employee}` + inserts `credential_documents` (`uploaded_via='symlink'`) + queues the portal's Gemini extraction; `info_update` PATCHes only `employees.phone/address/emergency_contact`; `manager_review` / `custom` are record-only.
- **Passcode grace rule** (decided with the product owner): `passcode.verify` accepts the CURRENT code only, constant-time (`hmac.compare_digest`) over a normalized (upper, no spaces/dashes) entry. A rotation never touches `symlink_unlocks` — an unlocked recipient keeps working; returning after a rotation needs the new code. Revoke / expire DO revoke unlock rows.
- **Passcode is plaintext in `symlink_passcodes.code`** — the admin UI must display it. It is a low-entropy insider proof; the per-task token is the real credential. It is never included in the invite email (`core/services/email/symlink.py` has no passcode parameter on purpose).
- **Public gate reads the RAW stored flag with an OFF default** — `symlink_public._symlink_allowed` is `features.get("symlink", False)`. Unlike `ir_magic_links`, a missing key means off, so no preset re-assertion is needed.
- **Unlock state is an opaque random token**, sha256-hashed at rest, sent as `X-Symlink-Unlock`; never a JWT, never a cookie shared across links. The browser keeps it in `sessionStorage` keyed by the link token.
- **Recipient sees only**: company name, title, instructions, the public spec (`kinds.public_spec` strips `document_type`), and their own transcript. Employee linkage is sender-side only.
- **No pooled connection across the Gemini call or an email send** — `symlink_chat_turn` reads state, releases, calls `next_turn`, reopens to persist; `create_link` / `resend_link` send mail with no connection held and persist the rotated token only after the send succeeded (`info_requests.py` pattern).
- `services/_shared/public_links.build_public_link` is the URL builder; `routes/ir_incidents/_shared._build_public_link` is now an alias over it (so this feature doesn't boot the IR package to mint a URL).

### Package map

| Module | Owns |
|---|---|
| `kinds.py` | Built-in kind registry (`_BUILTIN`), `materialize_spec(kind, overrides)` (the only spec writer; enforces ≥1 required item, unique keys, valid `document_type` mirrored from the portal's `_VALID_DOC_TYPES` — `tests/symlink/test_kinds.py` parses that file with `ast` to keep them equal), `public_spec`, `kind_catalog` |
| `passcode.py` | `generate_code` (6 chars, no 0/O/1/I), `normalize`, `verify`, `format_code` (`ABC-234`), `next_rotation(now, weekday)` (06:00 UTC), `due_for_rotation`; DB: `ensure_passcode` (lazy create, ON CONFLICT), `rotate_passcode` |
| `chat.py` | `build_prompt`, `coerce_fields`, `missing_items`, `is_complete`, `next_turn` (flash-lite, JSON mime, 20 s timeout, never raises; `MAX_TURNS=20`) |
| `links.py` | `symlinks` / `symlink_unlocks` service: `fetch_by_token` (RLS-free), `effective_status` (expiry derived at read time), `create_link`, `rotate_token`, `revoke`, `record_unlock` / `verify_unlock`, `save_turn`, `log_audit` |
| `attachments.py` | `stage_upload` (S3 before the txn), `insert_attachment` (one live file per slot), `discard`, `read_bytes`, `presigned_url` |
| `submissions.py` | `stage`, `apply` (per-kind dispatch + `evaluate_apply`), `reject`, `run_credential_extraction` (post-commit) |
| `notify.py` | `send_invite`, `send_submitted`, `sender_contact`, `announce_rotation` (system `channel_messages` row, `sender_id NULL`, same shape as EMS; worker-side so no WS fan-out) |

### Workers (`workers/tasks/symlink.py`, both seeded disabled in `scheduler_settings`)

- `symlink_passcode_rotation` — rotates every `symlink_passcodes` row past `next_rotation_at` for companies with the flag on, then announces in `announce_channel_id` when the company also has `matcha_ops`. Manual "Rotate now" (`POST /symlink/passcode/rotate`) is the same write and is safe to race.
- `symlink_sweep` — expires open links past `expires_at` (+ revokes their unlocks) and sends the **one-shot** 3-day reminder, claimed atomically on `symlinks.reminder_sent_at` (`onboarding_reminders` pattern; a failed send releases the slot).

### Client

- Admin: `pages/app/symlink/{SymLinks,SymLinkDetail,SymLinkSettings}.tsx`, api `api/symlink/symlink.ts`, types `types/symlink.ts`. Sidebar entry in `ClientSidebar` (HR Ops), `IrSidebar`, `MatchaXSidebar` (People); routes under `/app/symlink*` behind `<FeatureGate feature="symlink">`.
- Public: `pages/shared/SymLink.tsx` at `/sym/:token` → `hooks/symlink/useSymLinkSession.ts` (stages `validating|invalid|closed|locked|chat|review|submitting|submitted`) + `components/symlink/GuidedChat.tsx` (bubble/composer markup copied from `IRPublicChatIntake`; the review form is rendered from `spec.fields`). `IRPublicChatIntake` is untouched — its review form is hard-coded to IR fields.

### Tests

`cd server && python3 -m pytest tests/symlink -q` — passcode math, kind materialization, field coercion / completion / prompt, `next_turn` with a patched `genai_env_client` on the defining module, and a route-table smoke that loads both routers by file path (never through `app.matcha.routes`, whose `__init__` boots the zoo).
