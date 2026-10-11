"""The pieces of the skill engine's system prompt, shared by both renderings.

`provider._build_prompt_and_contents` joins them into Gemini's static and
dynamic prompts exactly as before (pinned byte-for-byte by
`tests/matcha_work/test_gemini_prompt_golden.py`). `_claude_thread` arranges
the same pieces for Anthropic prompt caching: thread-stable parts in the
system prompt, per-turn parts after the conversation.
"""
from __future__ import annotations

from typing import Optional

from ._fields import (
    BLOG_FIELDS, HANDBOOK_FIELDS, HR_PILOT_FIELDS, OFFER_LETTER_FIELDS, ONBOARDING_FIELDS, POLICY_FIELDS,
    PRESENTATION_FIELDS, PROJECT_FIELDS, REVIEW_FIELDS, WORKBOOK_FIELDS,
)

# HR Pilot action vocabulary — offered only in HR Pilot threads, so the
# `hr_pilot` skill is invisible everywhere else (execution is gated again
# server-side regardless). Starts with the blank line that separates it.
HR_PILOT_ACTIONS = '\n\nHR PILOT ACTIONS:\nBesides answering questions, you may PROPOSE two documented actions, and you may\nCONFIRM any action already staged in current_state. All actions are strictly\ntwo-step and confirm-first — never propose and execute in the same message.\n\nPROPOSE (mode="skill", skill="hr_pilot", operation="none", with the hr_action in updates):\n- Discipline write-up — when a supervisor asks to write someone up / document an\n  attendance, performance, or policy issue:\n  updates={"hr_action": {"type":"discipline_draft", "employee_name": str,\n  "infraction_type": "attendance|performance|policy_violation",\n  "severity": "minor|moderate|severe", "occurrence_dates": ["YYYY-MM-DD", ...],\n  "description": str, "expected_improvement": str, "status": "proposed"}}\n- Time-off request on an employee\'s behalf — VACATION or PERSONAL only:\n  updates={"hr_action": {"type":"pto_request", "employee_name": str,\n  "request_type": "vacation|personal", "start_date": "YYYY-MM-DD",\n  "end_date": "YYYY-MM-DD", "hours": number, "reason": str, "status": "proposed"}}\nIn "reply", summarize what you drafted and ask the supervisor to confirm.\n\nCONFIRM (mode="skill", skill="hr_pilot", operation="execute_hr_action", updates={}):\n- When current_state.hr_action has status "proposed" (ANY type — including a\n  safety/incident or HR-case report the SYSTEM staged for the supervisor after a\n  hard-stop) and the user confirms (e.g. "yes", "confirm", "file it"), emit the\n  execute operation with an EMPTY updates object. NEVER restate hr_action.\n\nRules:\n- NEVER claim anything was filed unless you used operation="execute_hr_action".\n- If you\'re missing the employee, dates, hours, or what happened, ask\n  (mode="clarify") — never invent a name, date, or number for a real record.\n- Do NOT PROPOSE a discipline write-up or PTO request for anything involving\n  safety, injury, harassment, discrimination, sick/medical leave, or termination\n  — those go to corporate HR (and are refused here). This restriction is about\n  PROPOSING; it does NOT stop you from helping the supervisor CONFIRM a\n  system-staged report about such a topic.\n- Never give guidance about the CONTENT of a staged safety/harassment report —\n  only help the supervisor confirm it or cancel it.'


def valid_fields_for(current_skill: str, hr_pilot_mode: bool) -> list[str]:
    """The update keys the model may write for this thread's skill."""
    if current_skill == "offer_letter":
        return OFFER_LETTER_FIELDS
    if current_skill == "review":
        return REVIEW_FIELDS
    if current_skill == "workbook":
        return WORKBOOK_FIELDS
    if current_skill == "onboarding":
        return ONBOARDING_FIELDS
    if current_skill == "presentation":
        return PRESENTATION_FIELDS
    if current_skill == "handbook":
        return HANDBOOK_FIELDS
    if current_skill == "policy":
        return POLICY_FIELDS
    if current_skill == "project":
        return PROJECT_FIELDS
    if current_skill == "blog":
        return BLOG_FIELDS
    if current_skill == "hr_pilot":
        return HR_PILOT_FIELDS
    valid_fields = (
        OFFER_LETTER_FIELDS + REVIEW_FIELDS + WORKBOOK_FIELDS + ONBOARDING_FIELDS + PRESENTATION_FIELDS
        + HANDBOOK_FIELDS + POLICY_FIELDS + PROJECT_FIELDS + BLOG_FIELDS
    )
    # HR Pilot's action vocabulary is offered only in HR Pilot threads —
    # otherwise a normal chat could stage an `hr_action` the executor
    # would then refuse anyway.
    if hr_pilot_mode:
        valid_fields = valid_fields + HR_PILOT_FIELDS
    return valid_fields


def recruiting_update(current_skill: str, current_state: dict) -> str:
    """Post-finalization recruiting details from thread state ("" when none).
    The route-level `_inject_recruiting_project_context` provides the primary
    recruiting context via company_context."""
    if current_skill == "project" and current_state.get("posting"):
        posting = current_state.get("posting", {})
        candidates_count = len(current_state.get("candidates", []))
        is_finalized = bool(posting.get("finalized"))
        return f"""
RECRUITING PROJECT UPDATE:
- Posting finalized: {is_finalized}
- Candidates: {candidates_count}
"""
    return ""


def summary_block(context_summary: Optional[str]) -> str:
    """The compacted earlier conversation ("" when there is none)."""
    if not context_summary:
        return ""
    return (
        f"\n\n## Conversation Context Summary\n"
        f"(Earlier messages were summarized to preserve context)\n"
        f"{context_summary}\n"
    )


def slide_lock(slide_index: Optional[int], current_skill: str, current_state: dict) -> str:
    """The SLIDE LOCK instruction for an edit aimed at one slide ("" otherwise)."""
    if slide_index is None or current_skill not in ("presentation", "workbook"):
        return ""
    slides = current_state.get("slides") or []
    if not slides:
        pres = current_state.get("presentation")
        if isinstance(pres, dict):
            slides = pres.get("slides") or []
    slide_title = ""
    if 0 <= slide_index < len(slides):
        slide_title = slides[slide_index].get("title", "") if isinstance(slides[slide_index], dict) else ""
    label = f' "{slide_title}"' if slide_title else ""
    total = len(slides)
    return (
        f"\n\n--- SLIDE LOCK ACTIVE ---\n"
        f"The user has selected Slide {slide_index + 1}/{total}{label} (0-based index {slide_index}). "
        f"You MUST only modify this slide. In your updates JSON:\n"
        f"- The 'slides' array must be identical to current_state except at index {slide_index}\n"
        f"- Do NOT change any other slide's title, bullets, or speaker_notes\n"
        f"- Do NOT include presentation_title, subtitle, theme, or cover_image_url in updates\n"
        f"- Only include 'slides' in your updates object\n"
        f"- CRITICAL: The user is requesting a CHANGE to the current slide. You must produce "
        f"updated content that differs from current_state. If the user asks to add, remove, or "
        f"modify something, the slide in your response MUST reflect that change. Never return "
        f"the slide unchanged when the user has requested a modification.\n"
        f"--- END SLIDE LOCK ---"
    )
