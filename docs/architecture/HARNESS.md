# Matcha-Work LLM Harness

The runtime scaffolding that wraps Gemini in the matcha-work chat loop
(`server/app/matcha/routes/matcha_work.py` + `server/app/matcha/services/matcha_work_ai.py`).

```
┌─────────────────────────────────────────────────────────────────────────┐
│  CLIENT (React)                                                         │
│  POST /threads/{id}/messages/stream     ← user types in thread          │
└───────────────────────────┬─────────────────────────────────────────────┘
                            │ SSE
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  send_message_stream()              matcha_work.py:5635                 │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                         │
│    ① PERSIST USER MSG    add_message(thread, "user", content)           │
│                                                                         │
│    ② LOAD CONTEXT  (parallel)                                           │
│       ├── get_thread_messages(limit=20)      ← rolling window           │
│       ├── get_company_profile_for_ai()       ← company + policies       │
│       ├── get_context_summary()              ← prior compaction         │
│       └── compliance/payer RAG (if mode set) ← semantic search          │
│                                                                         │
│    ③ INJECT DOMAIN CONTEXT                                              │
│       _inject_recruiting_project_context()                              │
│       build_node_context / build_compliance_context                     │
│                                                                         │
│    ④ SSE: {type: "status", message: "..."}  ← live progress             │
│                            │                                            │
└────────────────────────────┼────────────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  GeminiProvider.generate()          matcha_work_ai.py:536               │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                         │
│    ⑤ BUILD PROMPT                                                       │
│       ┌──────────────────────────┐  ┌─────────────────────────┐         │
│       │  STATIC (cached)         │  │  DYNAMIC (per-message)  │         │
│       │  • system instructions   │  │  • current_state JSON   │         │
│       │  • company profile       │  │  • valid_fields         │         │
│       │  • today's date          │  │  • context summary      │         │
│       └──────────────────────────┘  └─────────────────────────┘         │
│                 │                            │                          │
│                 ▼                            ▼                          │
│       ┌─── Gemini Context Cache ───┐                                    │
│       │  hit → reuse cached_content │ ← cost discount                   │
│       │  miss → inline static part  │                                   │
│       └─────────────────────────────┘                                   │
│                 │                                                       │
│    ⑥ CALL GEMINI                                                        │
│       genai.Client.models.generate_content(                             │
│         model = gemini-3-flash-preview  (or 3.1-pro-preview heavy)      │
│         contents = [static?, dynamic, ...history[-15:], user_msg]       │
│         tools = [Google Search]                ← only "tool"            │
│         response_mime_type = "application/json" ← forced JSON           │
│         temperature = 0.2                                               │
│       )                                                                 │
│                                                                         │
│    ⑦ PARSE JSON                                                         │
│       { reply, updates, mode, skill, operation, confidence, ... }       │
│       _clean_json_text → json.loads → schema filter by valid_fields     │
└────────────────────────────┬────────────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  BACK IN send_message_stream()                                          │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                         │
│    ⑧ APPLY UPDATES + DISPATCH OPERATION                                 │
│       _apply_ai_updates_and_operations()                                │
│       │                                                                 │
│       ├── merge updates into thread.current_state                       │
│       └── switch (operation):                                           │
│              • offer_letter.save_draft / send_draft / finalize          │
│              • handbook.generate                                        │
│              • review.send_requests                                     │
│              • onboarding.create_employees                              │
│              • recruiting.send_interviews                               │
│              (plain Python handlers — not more LLM calls)               │
│                                                                         │
│    ⑨ PERSIST ASSISTANT MSG + metadata                                   │
│                                                                         │
│    ⑩ ESCALATE  if confidence < threshold → create_escalation()          │
│                                                                         │
│    ⑪ SSE: {type: "result", data: AIResponse}                            │
│    ⑫ WS broadcast to thread collaborators (except sender)               │
│                                                                         │
│    ⑬ MAYBE COMPACT  (async, if >30 msgs)                                │
│       compact_conversation() → gemini-2.0-flash summarizes [:-15]       │
│       → stored as context_summary, reused next turn                     │
└─────────────────────────────────────────────────────────────────────────┘
```

## What's notable about this harness

- **Not a tool-calling loop.** Gemini returns one JSON object per turn; the
  `operation` field drives a Python `switch` statement. No model-driven tool
  selection, no N-step agent loop — one LLM call per user message.
- **Single "tool": Google Search.** Live grounding for compliance facts. No
  function registry.
- **Rolling 20-message window + compaction.** When a thread grows past 30
  messages, older context is summarized by flash into a single string that
  rides along with every subsequent prompt.
- **Two-layer prompt with Gemini context caching.** Static (system + company
  profile) is cached server-side; only the dynamic part and user message move
  across the wire each turn.
- **Single-agent.** Sub-services like `LeadsAgentService` and `LeaveAgent`
  exist but are invoked from HTTP routes, not from this loop — no delegation,
  no spawning.

## Sibling harnesses

Same *shape*, different entry points and model modes:

- `server/app/core/services/ai_chat.py` — WebSocket chat with local Qwen or Gemini
- `server/app/matcha/services/er_analyzer.py` — ER case streaming analysis
- `server/app/matcha/routes/interviews.py` — Gemini Live API for voice interviews

## Agentic system vs. harness

The harness above is the runtime — prompt assembly, cache, call, parse,
dispatch, persist, stream. Swap Claude for Gemini here and the system still
works.

The *agentic system* is everything that makes this product useful: the
domain-specific prompts, the skills (offer letters, handbook, compliance,
recruiting, ER), the state schemas the model fills in, the operation
handlers, the escalation rules, the company/policy/compliance data feeding
every turn. That layer is where the value lives; the harness is plumbing.
