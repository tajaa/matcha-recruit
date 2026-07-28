"""Caps, the cid namespace whitelist, the scheduling-law label/check maps, the
static discipline ladder, and _SUPERVISOR_ONLY_SOURCES (the groups
redact_for_employee strips). Leaf: imports nothing local.
"""
import logging
import re

logger = logging.getLogger(__name__)


_MAX_HR_PILOT_SECTIONS = 60


_MAX_HR_PILOT_POLICIES = 60


# Operational-fact caps (Supervisor Copilot groups). These read live tables that
# change daily, unlike the policy corpus above — the caps keep the prompt bounded
# and every cap that bites emits a truncation note, so the model can never read a
# clipped list as the complete picture.
_SCHEDULE_LOOKAHEAD_DAYS = 7


_MAX_SCHEDULE_SHIFTS = 40


# Jurisdiction research can generate per-state training requirements, so a
# company's program list is not inherently small — it needs a cap like every
# other fetch here.
_MAX_TRAINING_PROGRAMS = 40


_MAX_TRAINING_DETAIL = 15


_MAX_RECENT_INCIDENTS = 15


_INCIDENT_LOOKBACK_DAYS = 90


_MAX_BENEFIT_PLANS = 20


_MAX_SCHEDINT_COVERAGE_RECORDS = 10


_MAX_SCHEDLAW_RECORDS = 30


# rule_key -> (label, unit) — mirrors client/src/components/employees/ScheduleLawPanel.tsx's
# RULE_LABELS so the HR Pilot answer and the admin-facing law panel describe
# the same eleven fields the same way.
_SCHEDLAW_RULE_LABELS: dict[str, tuple[str, str]] = {
    "meal_break_after_hours": ("meal break required after", "h shift"),
    "meal_break_minutes": ("meal break duration", "min"),
    "second_meal_after_hours": ("second meal break after", "h shift"),
    "daily_ot_hours": ("daily overtime after", "h"),
    "daily_doubletime_hours": ("daily double-time after", "h"),
    "weekly_ot_hours": ("weekly overtime after", "h"),
    "min_rest_between_shifts_hours": ("minimum rest between shifts", "h"),
    "minor_u16_day_hours": ("under-16 daily cap", "h"),
    "minor_u16_week_hours": ("under-16 weekly cap", "h"),
    "minor_16_17_day_hours": ("16-17yo daily cap", "h"),
    "minor_16_17_week_hours": ("16-17yo weekly cap", "h"),
}


# rule_key -> the citation-lookup name `schedule_compliance._cite` reads
# (`rules["citations"][name]`) — duplicated from
# `routes/employee_schedule/_compliance.py:_RULE_KEY_TO_CHECK` rather than
# imported, since that lives in a route package and services must not reach
# into routes.
_SCHEDLAW_RULE_KEY_TO_CHECK = {
    "meal_break_after_hours": "meal_break",
    "meal_break_minutes": "meal_break",
    "second_meal_after_hours": "meal_break",
    "daily_ot_hours": "daily_overtime",
    "daily_doubletime_hours": "daily_overtime",
    "weekly_ot_hours": "weekly_overtime",
    "min_rest_between_shifts_hours": "min_rest",
    "minor_u16_day_hours": "minor_hours",
    "minor_u16_week_hours": "minor_hours",
    "minor_16_17_day_hours": "minor_hours",
    "minor_16_17_week_hours": "minor_hours",
}


# Namespaces the audit gate will recognise inside brackets. Deliberately a
# closed list: a bare `[...]` regex also matches markdown link text and the
# `[Handbook — Title]` headers this corpus renders, so unknown brackets must be
# left alone rather than treated as a citation that failed to resolve.
_CID_NAMESPACES = (
    "profile", "law", "handbook", "policy", "playbook", "floor", "ladder",
    # Supervisor Copilot — operational facts, not policy. See the order-of-
    # authority note in matcha_work_mode_contexts: these say who/when/status,
    # they never establish a rule.
    "schedule", "training", "incident",
    # Schedule Intelligence — analytics over the scheduling data (understaffing
    # x incident correlation, Fair Workweek exposure, qualified-coverage gaps).
    # Supervisor-only: see _SUPERVISOR_ONLY_SOURCES.
    "schedint",
    # Benefits enrollment — plan offerings + the open-enrollment window.
    # Company-level and nameless by construction, so (unlike the three above)
    # it is served to BOTH surfaces: "when does open enrollment close?" is a
    # core Ask HR question.
    "benefit",
    # Enforced scheduling-law thresholds (meal break/OT/rest/minor caps) +
    # Fair Workweek ordinances — state-level law, no employee data, served to
    # BOTH surfaces like benefit. See services/schedule_compliance.py.
    "schedlaw",
)


_CITATION_RE = re.compile(
    r"\[(" + "|".join(_CID_NAMESPACES) + r")(:[^\]\s]+)?\]"
)


# Progressive-discipline ladder — static company procedure, cited like any other
# record so "the next step is a written warning" is traceable rather than
# asserted. Replaces the prose _DISCIPLINE_LADDER_SUMMARY this module took over
# from matcha_work_mode_contexts.
_LADDER_STEPS = [
    ("verbal-warning", "Verbal warning",
     "First documented step. Supervisor discusses the issue with the employee and "
     "records that the conversation happened."),
    ("written-warning", "Written warning",
     "Second step. A written record the employee acknowledges, stating the conduct, "
     "the expectation, and the timeframe for improvement."),
    ("final-warning", "Final warning",
     "Third step. States plainly that the next step is a termination review."),
    ("termination-review", "Termination review",
     "Final step. NOT drafted or advised here — a final warning already on file means "
     "the supervisor must be routed to corporate HR."),
]


# Source groups an employee must not see. The first three describe OTHER PEOPLE
# rather than company policy — a supervisor is entitled to them (knowing who is
# on shift and who is overdue on training is the job), an employee is not: they
# name coworkers, their training failures, and incidents at their site.
#
# `handbook_audit`/`handbook_freshness` describe the EMPLOYER's own shortfalls:
# a graded handbook gap and a section the law has moved under.
# `gather_hr_pilot_grounding` doesn't fetch them today (only Handbook Pilot
# does), so both groups are empty here — they are listed anyway because
# `build_corpus` is shared, and the day anyone wires them in, the default must
# not be that an employee's "what's the PTO policy?" comes back with a list of
# where the company's handbook is non-compliant.
#
# `schedint` (Schedule Intelligence) is supervisor-only for the same
# other-people reason as the first three: its records name understaffed
# shifts, per-location Fair Workweek exposure, and which specific employees
# have a lapsed credential/training item blocking a shift.
_SUPERVISOR_ONLY_SOURCES = ("schedule", "training_status", "recent_incidents",
                            "handbook_audit", "handbook_freshness", "schedint")
