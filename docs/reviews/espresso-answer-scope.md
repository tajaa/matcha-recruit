# Espresso request scope: diagnosis and manual verification

Verified October 17, 2026 against main `1e8c0b808` and the patched prompt.

## Diagnosis

The issue reproduces inside the shared server runtime, independently of the
web/macOS renderer. `assistant.run_assistant` creates a new provider session
and `runner.run_agent` creates new ability sessions for every message.
`history.build_history` replays earlier requests, answers and receipts; raw
prior tool responses are not copied into the new run's ability state.

The earlier prompt said to report only what this run did, but did not limit
what work this run should do to the latest request. In the reproduction,
the model voluntarily called `list_espresso_events` while answering the email
question, then mentioned that new, irrelevant lookup in its answer. The
email ability's prompt does not request a recap or calendar lookup.

The prompt now scopes both tool use and all answer fields to the current
request. Earlier context remains available for direct follow-ups and requested
recaps. Historical run records omit email/calendar steps; the prompt also
clarifies that their absence cannot justify an unsolicited correction of
earlier mail/calendar work.

## Manual real-model test

The operator drove the existing `runner.run_agent` with real Claude Haiku 5.5
(`ClaudeSession`), real email/calendar ability handlers, `build_system_prompt`
and `history.build_history`. Each message started a fresh run/session in the
same conversation; the first answer and its run record were replayed before
the second request, as in the assistant entry point. Provider calls were
live; calendar and Gmail services were in-memory fixtures and audit/usage
writes were mocked. This tests server/model behavior, not either client's UI.
Fixtures used only `example.com` / `example.org` addresses.

Requests, in order:

1. `Add a dentist appointment to my Espresso calendar on October 20, 2026 from 3 to 4 PM. I am in America/Los_Angeles.`
2. `What did I say in the email I sent Dana about the lease renewal?`

Before the fix, the first request added exactly one event with the requested
time. The second request called `search_email`, **`list_espresso_events`**,
`read_email`, `finish`, and returned email **and event** blocks. Its reply,
verbatim (headline followed by summary):

> You told Dana you confirmed a one-year lease renewal at $2,400 per month.
>
> Your email to Dana (dana@example.org), subject "Lease renewal," was sent Monday, September 28, 2026 at 10:00 AM Pacific. The body reads: "I confirmed that I want to renew the lease for one year at $2,400 per month." I also checked your Espresso calendar: the dentist appointment from my last reply is there, Tuesday, October 20, 3:00–4:00 PM Pacific.

After the fix, the first request still added exactly one event at 3–4 PM
Pacific, with an event block. The second called only `search_email`,
`read_email`, `finish`, and returned only an email block. Its reply, verbatim:

> You told Dana you were renewing the lease for one year at $2,400 per month.
>
> The email is "Lease renewal," sent to dana@example.org on Monday, September 28, 2026 at 10:00 AM Pacific. It reads: "I confirmed that I want to renew the lease for one year at $2,400 per month."

Additional checks in that same patched conversation:

- `When is the dentist appointment you added?` returned the appointment time
  from history, without discussing the email.
- `Summarize both the calendar event you added and the email you found.`
  deliberately called calendar and email reads and returned both blocks.
- The calendar contained exactly one created event after all four turns.
  No email was sent, drafted or modified.

Control: the email request alone in a new conversation on the original prompt
used only email tools and returned only email information. The same-thread
calendar history was necessary for the observed reproduction.

## Regression coverage and limits

`server/tests/agent_runtime/test_answer_scope.py` checks the scope instructions
on every model call in a two-run calendar-then-email flow with real history
replay and real ability handlers over in-memory services. It also verifies
that the current request is the final input, calendar tools remain available,
the calendar add still succeeds once, and approval outcome instructions remain.
Its model transport is scripted: it validates the prompt/context contract,
not model compliance. The live manual check above supplies behavioral evidence.

This is prompt steering, not a deterministic topic classifier or output
filter. It preserves the single runtime loop, abilities, policy and history.
The live check covers one model and synthetic mailbox data; native/web UI
rendering and other model choices were not manually exercised.
