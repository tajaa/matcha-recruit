# Agent Architecture

```
┌─────────────────────────────────────────────────────────┐
│  HOST (your machine)                                    │
│                                                         │
│  run.sh                                                 │
│    │                                                    │
│    ├─ docker build → matcha-agent image                 │
│    │                                                    │
│    └─ docker run (or tmux for daemon)                   │
│         │                                               │
│         │  --read-only        (no writes to rootfs)     │
│         │  --cap-drop ALL     (no linux capabilities)   │
│         │  --user $(id -u)    (runs as your UID)        │
│         │  --memory 512m      (resource cap)            │
│         │  -e GEMINI_API_KEY  (only env var passed)     │
│         │                                               │
│         │  VOLUME MOUNT (only I/O boundary):            │
│         │  workspace/ ←→ /workspace                     │
│         │                                               │
│ ┌───────┼──── workspace/ ─────────────────────────┐     │
│ │       │                                         │     │
│ │  HEARTBEAT.md  ← you toggle skills on/off       │     │
│ │  feeds.yaml    ← you add/remove RSS feeds       │     │
│ │  inbox/        ← you drop files here            │     │
│ │  processed/    ← agent moves originals here     │     │
│ │  output/       ← agent writes summaries here    │     │
│ │                                                 │     │
│ └─────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  DOCKER CONTAINER                                       │
│                                                         │
│  agent.py  (heartbeat loop)                             │
│    │                                                    │
│    ├─ reads HEARTBEAT.md → which skills are enabled?    │
│    │                                                    │
│    ├─ [x] rss_briefing                                  │
│    │    │                                               │
│    │    ├─ reads feeds.yaml                             │
│    │    ├─ SandboxedFetcher ──→ fetch RSS (whitelist)   │
│    │    │    ✓ news.ycombinator.com                     │
│    │    │    ✓ feeds.arstechnica.com                    │
│    │    │    ✗ anything else → SandboxViolation         │
│    │    ├─ feedparser → extract articles                │
│    │    ├─ SandboxedGemini → summarize                  │
│    │    └─ SandboxedFS → write output/briefing-DATE.md  │
│    │                                                    │
│    ├─ [x] file_inbox                                    │
│    │    │                                               │
│    │    ├─ SandboxedFS → list inbox/                    │
│    │    ├─ SandboxedFS → read each file                 │
│    │    ├─ SandboxedGemini → summarize                  │
│    │    ├─ SandboxedFS → write output/processed-*.md    │
│    │    └─ SandboxedFS → move original to processed/    │
│    │                                                    │
│    └─ sleep(interval) → repeat                          │
│                                                         │
│  SANDBOX LAYERS:                                        │
│  ┌────────────────────────────────────────────┐         │
│  │ SandboxedFetcher  — URL whitelist          │         │
│  │ SandboxedFS       — path jail to /workspace│         │
│  │ SandboxedGemini   — logged API wrapper     │         │
│  └────────────────────────────────────────────┘         │
│  + Docker: read-only rootfs, no caps, no .env,          │
│    no DATABASE_URL, no host filesystem access            │
└─────────────────────────────────────────────────────────┘
```

## Two Layers of Sandboxing

1. **Docker** (OS-level) — even if the Python code is exploited, the container can't touch host files, the database, or escalate privileges
2. **Python sandbox** (app-level) — defense-in-depth: URL whitelist, filesystem jail, logged Gemini calls

## Human Interface

The workspace folder is the only boundary between you and the agent:

| File/Dir | Direction | Purpose |
|---|---|---|
| `HEARTBEAT.md` | you → agent | Toggle skills on/off with `[x]` / `[ ]` |
| `feeds.yaml` | you → agent | Add/remove RSS feeds |
| `inbox/` | you → agent | Drop files for processing |
| `output/` | agent → you | Read briefings and summaries |
| `processed/` | agent → you | Originals moved here after processing |

## Usage

```bash
cd server/agent
./run.sh                        # one-shot
./run.sh --daemon               # heartbeat loop in tmux (30min)
./run.sh --daemon --interval 5  # every 5 minutes
```
