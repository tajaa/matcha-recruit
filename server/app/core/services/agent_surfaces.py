"""The AI workloads the platform admin can route, grouped by app.

Admin → Settings → *AI models* stores one choice per app (the app default)
and one per surface (a product inside an app), in the `agent_models`
platform setting. A surface set to `inherit` follows its app. A choice is
`default` (the surface's built-in provider, `builtin` below) or a Claude
model id. `anthropic_messages.claude_override(surface)` resolves it.

This registry is the single list: the admin page renders it from the GET
payload, the PUT validates against it, and `test_agent_surfaces` fails when a
call site passes a key that is not here. Add a surface here first, then pass
its constant at the call site.

Matcha Work (business `/work`) is part of Matcha; Espresso is the personal
app. Both run on the matcha-work backend, so the shared call sites pick their
surface per account with `matcha_work.app_surface.work_surface`.
"""

from __future__ import annotations

from dataclasses import dataclass

INHERIT = "inherit"
BUILTIN = "default"
CLAUDE_HAIKU = "claude-haiku-5-5"
CLAUDE_SONNET = "claude-sonnet-5-5"
CLAUDE_CHOICES = (CLAUDE_HAIKU, CLAUDE_SONNET)
MODEL_CHOICES = (BUILTIN, *CLAUDE_CHOICES)
SURFACE_CHOICES = (INHERIT, *MODEL_CHOICES)


@dataclass(frozen=True)
class AppDef:
    key: str
    label: str
    description: str


@dataclass(frozen=True)
class SurfaceDef:
    key: str
    app: str
    label: str
    description: str
    builtin: str  # what `default` runs on, shown in the admin page


MATCHA = "matcha"
ESPRESSO = "espresso"
GUMMFIT = "gummfit"

APPS: tuple[AppDef, ...] = (
    AppDef(MATCHA, "Matcha", "The HR and operations platform, including Huume and Matcha Work for businesses."),
    AppDef(ESPRESSO, "Espresso", "The personal workspace app (personal accounts on matcha-work)."),
    AppDef(GUMMFIT, "Gummfit", "The website builder (Cappe) on gummfit.com."),
)

# ── Matcha ──
MATCHA_HUUME = "matcha.huume"
MATCHA_SCHEDULING = "matcha.scheduling"
MATCHA_IR = "matcha.ir"
MATCHA_HANDBOOKS = "matcha.handbooks"
MATCHA_OPS = "matcha.ops"
MATCHA_INVENTORY = "matcha.inventory"
MATCHA_SYMLINK = "matcha.symlink"
MATCHA_CREDENTIALS = "matcha.credentials"
MATCHA_WORK_CHAT = "matcha.work_chat"
MATCHA_WORK_AGENT_CARDS = "matcha.work_agent_cards"
MATCHA_WORK_PROJECTS = "matcha.work_projects"
MATCHA_SYM_CHAT = "matcha.sym_chat"

# ── Espresso ──
ESPRESSO_CHAT = "espresso.chat"
ESPRESSO_AGENT_CARDS = "espresso.agent_cards"
ESPRESSO_ASSISTANT = "espresso.assistant"
ESPRESSO_PROJECTS = "espresso.projects"

# ── Gummfit (Cappe) ──
GUMMFIT_MERLIN = "gummfit.merlin"
GUMMFIT_MERLIN_ROUTER = "gummfit.merlin_router"
GUMMFIT_DIRECTORY = "gummfit.directory"
GUMMFIT_BOOKING = "gummfit.booking"

_LUNA = "OpenAI Luna"
_GEMINI = "Gemini"

SURFACES: tuple[SurfaceDef, ...] = (
    SurfaceDef(MATCHA_HUUME, MATCHA, "Huume", "The Huume agent in Matcha Work threads.", _LUNA),
    SurfaceDef(
        MATCHA_SCHEDULING, MATCHA, "Scheduler",
        "Schedule Pilot's Huume (its own dropdown still wins per chat), shift edits asked for in "
        "Ops channels, and state schedule-rule extraction.",
        f"{_LUNA} · {_GEMINI} for channel edits",
    ),
    SurfaceDef(
        MATCHA_IR, MATCHA, "Incidents (IR)",
        "AI analysis, Copilot guidance, chat intake, consistency, OSHA recordability, interview "
        "questions and similar-incident matching. Voice dictation stays on Gemini.",
        _GEMINI,
    ),
    SurfaceDef(
        MATCHA_HANDBOOKS, MATCHA, "Handbooks",
        "Handbook audit, guided draft, Handbook Pilot and the upload check. Law research that "
        "needs Google Search stays on Gemini.",
        _GEMINI,
    ),
    SurfaceDef(MATCHA_OPS, MATCHA, "Ops channels", "@huume in channels: event logging and questions.",
               f"{_GEMINI} · {_LUNA} for questions"),
    SurfaceDef(MATCHA_INVENTORY, MATCHA, "Inventory",
               "Stock updates from channels, receipt reading, forecast and waste insights.", _GEMINI),
    SurfaceDef(MATCHA_SYMLINK, MATCHA, "Sym-link", "The guided chat on a sym-link.", _GEMINI),
    SurfaceDef(MATCHA_CREDENTIALS, MATCHA, "Credentials",
               "Credential requirement research and role classification.", _LUNA),
    SurfaceDef(
        MATCHA_WORK_CHAT, MATCHA, "Matcha Work chat",
        "Business thread chat. A Gemini pick in the chat picker runs this model; an explicit "
        "Claude pick still wins.",
        f"{_GEMINI} (the picker)",
    ),
    SurfaceDef(MATCHA_WORK_AGENT_CARDS, MATCHA, "Matcha Work agent cards",
               "Kanban agent cards: product research and the purchase flow.", _LUNA),
    SurfaceDef(MATCHA_WORK_PROJECTS, MATCHA, "Matcha Work projects",
               "@espresso repository questions and task drafts in business projects.", _LUNA),
    SurfaceDef(MATCHA_SYM_CHAT, MATCHA, "Sym-chat", "Scheduling and decision micro-chats.", _LUNA),
    SurfaceDef(
        ESPRESSO_CHAT, ESPRESSO, "Chat",
        "Personal thread chat, on web and the Mac app. A Gemini pick in the chat picker runs this "
        "model; an explicit Claude pick still wins.",
        f"{_GEMINI} (the picker)",
    ),
    SurfaceDef(ESPRESSO_AGENT_CARDS, ESPRESSO, "Purchase agent",
               "Agent cards: finding the product. The purchase itself uses no AI.", _LUNA),
    SurfaceDef(ESPRESSO_ASSISTANT, ESPRESSO, "Assistant",
               "The assistant you start from chat: flights, browsing, purchases.", _LUNA),
    SurfaceDef(ESPRESSO_PROJECTS, ESPRESSO, "Projects",
               "@espresso repository questions and task drafts in personal projects.", _LUNA),
    SurfaceDef(
        GUMMFIT_MERLIN, GUMMFIT, "Merlin (single-step edits)",
        "Every Lite turn and other one-shot edits. The tier still sets how hard it thinks "
        "(Lite low, Regular medium, Max high). Merlin's multi-step agent (Regular/Max on a "
        "premium plan) stays on Gemini for now.",
        f"{_GEMINI} Flash Lite (Lite) · Flash",
    ),
    SurfaceDef(
        GUMMFIT_MERLIN_ROUTER, GUMMFIT, "Merlin Auto",
        "Picks Lite, Regular or Max for an Auto request. It has 6 seconds; past that the turn "
        "runs on Regular.",
        f"{_GEMINI} Flash Lite",
    ),
    SurfaceDef(GUMMFIT_DIRECTORY, GUMMFIT, "Directory listing",
               "Suggests a published site's directory category, tags and blurb.", f"{_GEMINI} Flash Lite"),
    SurfaceDef(GUMMFIT_BOOKING, GUMMFIT, "Booking suggestions",
               "Reads the times and staff a visitor asks for when suggesting bookings.", f"{_GEMINI} Flash Lite"),
)

APP_KEYS: frozenset[str] = frozenset(app.key for app in APPS)
SURFACE_BY_KEY: dict[str, SurfaceDef] = {surface.key: surface for surface in SURFACES}


def app_of(surface: str) -> str | None:
    """The app a surface key belongs to, or None for an unknown key."""
    known = SURFACE_BY_KEY.get(surface)
    if known:
        return known.app
    prefix = surface.split(".", 1)[0]
    return prefix if prefix in APP_KEYS else None


def registry_payload() -> list[dict]:
    """The admin page's layout: each app with its surfaces, in order."""
    return [
        {
            "key": app.key,
            "label": app.label,
            "description": app.description,
            "surfaces": [
                {"key": s.key, "label": s.label, "description": s.description, "builtin": s.builtin}
                for s in SURFACES
                if s.app == app.key
            ],
        }
        for app in APPS
    ]
