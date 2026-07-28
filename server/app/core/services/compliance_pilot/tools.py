"""The Compliance Pilot loop's vocabulary — a Gemini function-calling registry.

Structural mirror of `matcha/services/huume/tools.py` (frozen-dataclass entries +
a name lookup + `tool_declarations()`), reimplemented here because core/ must not
import matcha/. `tool_declarations()` is the single source of truth that both the
loop (`agent.py`) and the prompt (`prompt.py`) read, so a tool's name and
description can't drift between what the model is offered and what it is told.

Kinds:
  read   — no side effect. Answers "what does the catalog already hold?"
  staged — proposes an action row (status='proposed'); nothing runs until the
           admin confirms on a LATER turn.
  write  — acts on something ALREADY staged (confirm / cancel). Not a new write
           surface: the confirm-first gate is what authorizes it.
  finish — ends the turn.

Deliberately absent: any tool that writes catalog rows directly. Every path into
`jurisdiction_requirements` goes through a staged research/approve action, so the
admin's confirmation is structurally unavoidable rather than prompt-enforced.
"""

from __future__ import annotations

from dataclasses import dataclass

from google.genai import types

# The kinds a tool may declare, mirrored by the loop's dispatch.
READ, STAGED, WRITE, FINISH = "read", "staged", "write", "finish"


@dataclass(frozen=True)
class PilotTool:
    name: str
    kind: str  # read | staged | write | finish
    declaration: types.FunctionDeclaration


def _tool(name: str, kind: str, description: str, *,
          properties: dict | None = None,
          required: list[str] | None = None) -> PilotTool:
    return PilotTool(
        name=name,
        kind=kind,
        declaration=types.FunctionDeclaration(
            name=name,
            description=description,
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties=properties or {},
                required=required or [],
            ),
        ),
    )


_STATE = types.Schema(type=types.Type.STRING,
                      description="Two-letter US state code, e.g. 'CA'.")
_CITY = types.Schema(type=types.Type.STRING,
                     description="City name, e.g. 'Los Angeles'. Omit for the state level.")


TOOLS: tuple[PilotTool, ...] = (
    # ---- Reads ------------------------------------------------------------- #
    _tool(
        "coverage_snapshot", READ,
        "What the catalog already holds for a coordinate: how many core-labor "
        "categories are covered / researched-and-nothing-applies / never "
        "checked, how many active rows sit on the federal→state→city chain, and "
        "(when an industry is named) the per-category ledger status for that "
        "industry. Call this before proposing research — researching a category "
        "already marked covered or empty spends money for nothing.",
        properties={"state": _STATE, "city": _CITY,
                    "industry": types.Schema(
                        type=types.Type.STRING,
                        description="Industry name or tag, e.g. 'healthcare'. Omit for the core-labor axis only.")},
        required=["state"],
    ),
    _tool(
        "search_catalog", READ,
        "Semantic search over the requirements already in the catalog. Returns "
        "matching rows as citable `req:` records — the ONLY requirement ids you "
        "may cite. Use this to answer a regulatory question from what's on file, "
        "and to check whether a topic is already covered before researching it.",
        properties={
            "query": types.Schema(type=types.Type.STRING,
                                  description="What to look for, e.g. 'tipped minimum wage' or 'medical waste disposal'."),
            "state": _STATE, "city": _CITY,
        },
        required=["query"],
    ),
    _tool(
        "uncodified_backlog", READ,
        "The scope registry's research worklist for a chain: enumerated, "
        "human-confirmed legal obligations that apply here but have no catalog "
        "row yet ('keyed' — researchable now) plus those still missing a "
        "regulation key ('unkeyed' — not researchable until a key is minted). "
        "This is the grounded answer to 'what should we build next', as opposed "
        "to coverage_snapshot's category-level view. Note the registry corpus is "
        "federal + California only today — read the note the tool returns before "
        "drawing conclusions about any other state.",
        properties={"state": _STATE, "city": _CITY},
    ),
    _tool(
        "readiness", READ,
        "The onboarding-readiness verdict for an industry in a jurisdiction: "
        "READY / NOT_READY plus the subscores (completeness, accuracy, "
        "authority, freshness, tagging, scope), what's blocking, and the "
        "specific missing regulation keys. Unmeasured suites score null, never "
        "100 — a null is 'never measured', not 'fine'. Use it to answer "
        "'could we onboard a customer in this vertical here yet?'",
        properties={
            "industry": types.Schema(type=types.Type.STRING,
                                     description="Industry name or tag, e.g. 'manufacturing'."),
            "state": _STATE, "city": _CITY,
        },
        required=["industry"],
    ),
    _tool(
        "authority_status", READ,
        "The state of the authority indexes the scope registry enumerates — per "
        "index: how many items are ingested, how many still lack a confirmed "
        "classification (that count IS the remaining scoping work), whether the "
        "index is enumerable (a completeness claim is mechanically checkable) or "
        "curated (it is NOT — 'nothing unclassified' means the curated list is "
        "done, never that all of that state's law is scoped), and when it was "
        "last ingested.",
    ),
    _tool(
        "list_actions", READ,
        "Every action in this session with its id, kind, status and headline "
        "result — proposals awaiting confirmation, runs in flight, and finished "
        "runs. Use it to recover an action_id you need, or to check what you "
        "already proposed before staging something new.",
    ),
    _tool(
        "action_status", READ,
        "One action's current status and full result — for a finished research "
        "run, the staged policies with each one's codify-gate verdict and "
        "reason. Research runs take minutes: call this to see whether one you "
        "confirmed has finished before you talk about its results.",
        properties={"action_id": types.Schema(type=types.Type.STRING)},
        required=["action_id"],
    ),
    # ---- Staged actions ---------------------------------------------------- #
    _tool(
        "stage_research", STAGED,
        "Propose a research run: one Gemini pass per category over an industry × "
        "jurisdiction coordinate, staging its findings as PENDING rows for "
        "review. This STAGES the run for the admin's confirmation — nothing "
        "researches and nothing is spent until they confirm on a LATER turn. "
        "Scope tightly: each category is its own paid research pass, so name "
        "just the categories the admin actually asked about. Omit `categories` "
        "ONLY when they explicitly asked for all/every requirement.",
        properties={
            "industry": types.Schema(type=types.Type.STRING,
                                     description="Industry name or tag, e.g. 'healthcare'."),
            "state": _STATE, "city": _CITY,
            "categories": types.Schema(
                type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING),
                description="Category topics to research, e.g. ['clinical_safety']. Omit for the full catalog sweep.",
            ),
            "rationale": types.Schema(type=types.Type.STRING,
                                      description="One sentence on why this gap is worth the spend."),
        },
        required=["industry", "state"],
    ),
    _tool(
        "stage_check_sources", STAGED,
        "Propose a source-link audit: fetch every citation URL on a "
        "jurisdiction chain and flag the dead ones (genuinely dead links are "
        "marked; timeouts are left alone). This STAGES the run for the admin's "
        "confirmation — it does not start until they confirm on a LATER turn.",
        properties={
            "state": _STATE, "city": _CITY,
            "rationale": types.Schema(type=types.Type.STRING),
        },
        required=["state"],
    ),
    _tool(
        "stage_approve", STAGED,
        "Propose committing a finished research run's staged policies: activate "
        "them, then make each AUTHORITATIVE where it passes the deterministic "
        "codify gate (a regulation key + a statute citation from research + a "
        "live PRIMARY government source). This STAGES the commit for the "
        "admin's confirmation — nothing is activated until they confirm on a "
        "LATER turn. Omit `ids` to commit only the gate-passing rows, which is "
        "the right default. Passing `ids` explicitly may include gate-failing "
        "rows: those go live but stay uncodified, with the reason recorded — say "
        "so plainly if the admin asks for them.",
        properties={
            "from_action_id": types.Schema(
                type=types.Type.STRING,
                description="The finished research action whose staged policies to commit."),
            "ids": types.Schema(
                type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING),
                description="Specific staged requirement ids. Omit for every row that passes the codify gate.",
            ),
        },
        required=["from_action_id"],
    ),
    # ---- Acting on what's already staged ----------------------------------- #
    _tool(
        "confirm_action", WRITE,
        "Execute an action the admin has now explicitly confirmed. Only call "
        "this when they said to go ahead in a message LATER than the one that "
        "staged it — never in the same turn you staged it. Pass the action_id "
        "exactly as it appears in 'Currently staged'. Research and commit runs "
        "take minutes: this starts the run and returns immediately, so report "
        "it as started, not finished, and use action_status to follow up.",
        properties={"action_id": types.Schema(type=types.Type.STRING)},
        required=["action_id"],
    ),
    _tool(
        "cancel_action", WRITE,
        "Void a proposed action the admin has decided against, so a stale "
        "proposal isn't left sitting there. Only a proposal can be cancelled — "
        "a run already in flight or finished cannot be undone from here.",
        properties={"action_id": types.Schema(type=types.Type.STRING)},
        required=["action_id"],
    ),
    _tool(
        "finish", FINISH,
        "End the turn with a plain-language summary of what actually happened — "
        "what you looked up, what you staged and are waiting on, and what you "
        "started. Never describe a staged action as done, and never describe a "
        "started run as finished.",
        properties={"message": types.Schema(type=types.Type.STRING)},
        required=["message"],
    ),
)

TOOLS_BY_NAME: dict[str, PilotTool] = {t.name: t for t in TOOLS}


def tool_declarations() -> list[types.FunctionDeclaration]:
    return [t.declaration for t in TOOLS]
