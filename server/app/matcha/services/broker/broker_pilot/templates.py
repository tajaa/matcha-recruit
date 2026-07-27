"""The analysis-mode template catalog (PILOT_TEMPLATES) and its lookup /
public-projection helpers. Pure data + pure functions.
"""
import logging


logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Starter templates ("modes")
# --------------------------------------------------------------------------- #
# A mode is a named starting point for a session. It carries a default `title`,
# tailored `starters` (surfaced in the console, pre-filled into the composer —
# never auto-sent), and a `focus` directive that is appended to the analyst
# system prompt on EVERY turn of the session (persisted via
# broker_pilot_sessions.template_key). The `focus` strings deliberately name the
# corpus cid namespaces (`platform:` / `clause:` / `doc:` / `docfig:` — see the
# module header) so the model grounds where the mode intends. Mirrors Legal
# Pilot's matter-type-keyed starters + Analysis Pilot's `_DOMAIN_LENSES`.
#
# A session with NO template_key keeps the generic behavior (the frontend falls
# back to its default starter list) — the catalog is additive.

PILOT_TEMPLATES: tuple[dict, ...] = (
    {
        "key": "contract_review",
        "label": "Client contract review",
        "description": "Check the client's contractual insurance and indemnity "
                       "requirements against the coverage they carry.",
        "title": "Contract review",
        "focus": (
            "Center the analysis on the "
            "client's contractual risk transfer: the extracted indemnity clauses "
            "(`clause:` records) and the coverage lines the client carries "
            "(`platform:limits.*`). Assess whether carried limits meet each "
            "contract's required limits, whether required endorsements "
            "(additional insured, waiver of subrogation, primary & "
            "non-contributory) appear to be in place, and the insurability of "
            "each indemnity form. A recorded clause verdict is a starting point "
            "for counsel — report it as such and never state that a clause is or "
            "is not enforceable. Insurance and risk-transfer terms only. The "
            "`jur:` records are the client's codified EMPLOYMENT-law obligations "
            "(final pay, leave, pay transparency, anti-discrimination) — cite "
            "them only where an employment-practices exposure is genuinely at "
            "issue; they do not speak to contractual insurance requirements, so "
            "never stretch one to cover a limits or endorsement question."
        ),
        "starters": [
            "Do the limits this client carries meet what their contracts require? Flag every gap.",
            "Which indemnity clauses create uninsurable or likely-void exposure, and why?",
            "Which contracts require endorsements (additional insured / waiver of subrogation / primary & non-contributory) the client may not carry?",
        ],
        "required_docs": (
            {
                "doc_type": "contract",
                "label": "Client contract",
                "hint": "The agreement whose insurance and indemnity requirements you want checked — "
                        "a customer contract, lease, MSA, or subcontract. On-platform clients: adding "
                        "it under the client's Contracts page gives full clause extraction and "
                        "insurability verdicts instead of a basic read.",
                "required": True,
                "platform_source": "clauses",
            },
            {
                "doc_type": "dec_page",
                "label": "Current dec page",
                "hint": "The limits the client actually carries today — what the contract's "
                        "requirements get measured against.",
                "required": False,
                "platform_source": "limits",
            },
        ),
    },
    {
        "key": "mid_year",
        "label": "Mid-year check-in",
        "description": "Mid-term review of loss activity and emerging exposures "
                       "since the policy bound.",
        "title": "Mid-year check-in",
        "focus": (
            "This is a mid-term account review. "
            "Center on what has CHANGED since the policy bound: recent loss "
            "development (`platform:lossdev.*`), open vs. closed claims, new "
            "safety or employee-relations activity (`incident:` / `er_case:` "
            "records), and exposure shifts (headcount, new locations, property, "
            "venue). Surface what the broker should raise with the client now "
            "rather than waiting for renewal."
        ),
        "starters": [
            "What has changed on this account since the policy bound that I should flag now?",
            "How is loss development trending mid-term — is anything developing adversely?",
            "Any new exposures — locations, headcount, contracts — that affect the current program?",
        ],
        "required_docs": (
            {
                "doc_type": "loss_run",
                "label": "Current loss run",
                "hint": "Mid-term loss activity. Satisfied automatically when the client already has "
                        "loss-development history on the platform.",
                "required": True,
                "platform_source": "lossdev",
            },
        ),
    },
    {
        "key": "renewal_90",
        "label": "90 days before renewal",
        "description": "Pre-renewal readiness: loss development, submission "
                       "completeness, and likely underwriter questions.",
        "title": "90-day renewal check-in",
        "focus": (
            "Renewal is roughly 90 days "
            "out. Center on renewal readiness: reserve and loss development with "
            "projected ultimates (`platform:lossdev.*`), submission-data "
            "completeness (`platform:readiness`), the controls story "
            "(`platform:controls`), and the workers'-comp / EPL metrics an "
            "underwriter will scrutinize (`platform:wc`, `platform:epl.*`), and "
            "the codified employment-law obligations that shape the EPL exposure "
            "(`jur:` records). End "
            "every analysis with the concrete data the broker should gather "
            "before marketing the account."
        ),
        "starters": [
            "Give me a pre-renewal read: reserve development, biggest exposures, and pricing pressure.",
            "What's missing from the submission data, and what will the underwriter ask for first?",
            "Summarize the controls and readiness story I can lead the renewal narrative with.",
        ],
        "required_docs": (
            {
                "doc_type": "loss_run",
                "label": "Valued loss run",
                "hint": "The loss run the market will price off. Satisfied automatically when the "
                        "client already has loss-development history on the platform.",
                "required": True,
                "platform_source": "lossdev",
            },
            {
                "doc_type": "dec_page",
                "label": "Expiring dec page",
                "hint": "The expiring terms the renewal gets compared against.",
                "required": False,
                "platform_source": "limits",
            },
        ),
    },
    {
        "key": "new_business",
        "label": "New business appetite read",
        "description": "Prospect appetite read for a new client from the "
                       "documents and data on file.",
        "title": "New business appetite read",
        "focus": (
            "This is a new-business / "
            "prospect evaluation. Center on how a carrier would view the account: "
            "the risk profile from available data (industry, headcount, venue, "
            "property), what the uploaded documents (loss runs, current dec "
            "pages) reveal (`doc:` / `docfig:`), and the account's strengths and "
            "red flags from a market's point of view. Be explicit about what is "
            "not yet known and would need to be obtained to market the account."
        ),
        "starters": [
            "From what's on file, how would a carrier view this prospect's appetite and risk quality?",
            "What are the strengths I can lead with, and the red flags I need to get ahead of?",
            "What information is missing to market this account, and what should I request first?",
        ],
        # Nothing hard-required: an appetite read is exactly the conversation a
        # broker has BEFORE the prospect hands over paper.
        "required_docs": (
            {
                "doc_type": "loss_run",
                "label": "Prior-carrier loss runs",
                "hint": "The single biggest driver of how a market views the account.",
                "required": False,
                "platform_source": "lossdev",
            },
            {
                "doc_type": "dec_page",
                "label": "Current dec page",
                "hint": "What the prospect carries today — the program you'd be competing against.",
                "required": False,
                "platform_source": "limits",
            },
        ),
    },
    {
        "key": "loss_run",
        "label": "Loss-run deep dive",
        "description": "Focused analysis of the uploaded loss runs — frequency, "
                       "severity, development, and large claims.",
        "title": "Loss-run deep dive",
        "focus": (
            "Center the analysis on the "
            "uploaded loss-run documents (`doc:` / `docfig:`) alongside the "
            "platform loss development on file (`platform:lossdev.*`). Break down "
            "frequency, severity, paid vs. reserved, open claims, and any large "
            "or adversely developing losses. Reconcile the uploaded loss runs "
            "against the platform loss data and call out any discrepancies "
            "explicitly, citing both sides."
        ),
        "starters": [
            "Break down the uploaded loss runs: frequency, severity, and any large or open claims.",
            "How do the uploaded loss runs reconcile with the platform loss development on file?",
            "Which claims are developing adversely, and what does that imply for the reserves?",
        ],
        # No `platform_source`, deliberately: this mode's whole point is the
        # claim-level carrier document. Platform loss triangles are aggregates —
        # they can't answer "which claims are developing adversely", so they must
        # NOT quietly satisfy the requirement the way they do for mid_year/renewal.
        "required_docs": (
            {
                "doc_type": "loss_run",
                "label": "Carrier loss run",
                "hint": "The claim-level document itself. Platform loss triangles don't substitute — "
                        "this mode reconciles the two against each other.",
                "required": True,
                "platform_source": None,
            },
        ),
    },
    {
        "key": "quote_comparison",
        "label": "Quote comparison",
        "description": "Compare competing quotes against each other and against "
                       "the loss history.",
        "title": "Quote comparison",
        "focus": (
            "The broker is comparing carrier "
            "quotes. Center on the uploaded quote documents (`doc:` / `docfig:`): "
            "premium, limits, retentions, and — critically — the coverage "
            "differences, sublimits, and exclusions between them. Test whether "
            "the pricing is supported by the loss history (`platform:lossdev.*` "
            "and uploaded loss runs). Flag any coverage a lower premium may be "
            "quietly buying away. All terms must be verified against actual "
            "policy forms."
        ),
        "starters": [
            "Compare the uploaded quotes side by side: premium, limits, retentions, and key exclusions.",
            "Is the quoted pricing supported by the loss history, or is a cheaper quote buying less coverage?",
            "What coverage differences or sublimits between these quotes should I flag to the client?",
        ],
        # One quote clears the gate — comparing a single quote against the expiring
        # program is a real comparison. `single_quote_note` tells the analyst it is
        # working from one, so it can't silently narrate a head-to-head that isn't there.
        "required_docs": (
            {
                "doc_type": "quote",
                "label": "Carrier quote",
                "hint": "Upload every quote you want compared. One quote works — it gets compared "
                        "against the expiring program — but the mode is at its best with two or more.",
                "required": True,
                "platform_source": None,
            },
            {
                "doc_type": "dec_page",
                "label": "Expiring dec page",
                "hint": "The incumbent's terms, so a cheaper quote's coverage cuts show up.",
                "required": False,
                "platform_source": "limits",
            },
        ),
    },
)


_TEMPLATE_BY_KEY: dict[str, dict] = {t["key"]: t for t in PILOT_TEMPLATES}


def _lookup_template(key: str | None) -> dict | None:
    """Single resolution point for a stored template_key. None for a blank key
    (open analysis / legacy rows); a truthy key that no longer resolves is a
    stranded session (catalog edit while sessions persist) — warn so it's
    observable rather than silently un-moded."""
    if not key:
        return None
    t = _TEMPLATE_BY_KEY.get(key)
    if t is None:
        logger.warning("broker_pilot: session references unknown template_key %r", key)
    return t


def _public_template(t: dict) -> dict:
    """Public projection (drops the internal `focus`). Copies `starters` and
    `required_docs` (per-row too) so a caller mutating the returned structures
    can't corrupt the module catalog.

    `required_docs` IS public: the frontend renders it as the mode's document
    chips, and `broker_pilot_requirements` computes satisfaction from it — so the
    same dict the picker shows is the one the gate keys on."""
    return {
        "key": t["key"], "label": t["label"], "description": t["description"],
        "title": t["title"], "starters": list(t["starters"]),
        "required_docs": [dict(r) for r in t.get("required_docs") or ()],
    }


def template_catalog() -> list[dict]:
    """Public catalog for the frontend picker (omits the internal `focus`
    directive). Order is the catalog's declared order."""
    return [_public_template(t) for t in PILOT_TEMPLATES]


def get_template(key: str | None) -> dict | None:
    """Public template shape (no `focus`) for a stored key, or None."""
    t = _lookup_template(key)
    return _public_template(t) if t else None


def _mode_focus(key: str | None) -> str:
    """The per-mode system-prompt directive for a stored key, or "" (no mode).
    The `SESSION MODE — <label>.` header is composed here so it can never drift
    from the template's own `label`."""
    t = _lookup_template(key)
    return f"SESSION MODE — {t['label']}. {t['focus']}" if t else ""
