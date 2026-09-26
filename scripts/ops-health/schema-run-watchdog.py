#!/usr/bin/env python3
"""Alert when the Mac-hosted schema comparison does not finish on schedule."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

MAX_RUNNING_HOURS = 4
MAX_SUCCESS_AGE_HOURS = 27


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("workflow run has no created_at timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("workflow run has an invalid created_at timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("workflow run timestamp has no timezone")
    return parsed.astimezone(UTC)


def assess_runs(payload: object, now: datetime) -> dict[str, object]:
    if not isinstance(payload, dict) or not isinstance(payload.get("workflow_runs"), list):
        raise ValueError("GitHub response has no workflow_runs array")
    runs = payload["workflow_runs"]
    if not runs:
        return {"status": "unhealthy", "reason": "No schema comparison runs were returned.", "run_url": None}

    latest = max(runs, key=lambda run: _timestamp(run.get("created_at")))
    created = _timestamp(latest.get("created_at"))
    age_hours = (now.astimezone(UTC) - created).total_seconds() / 3600
    status = latest.get("status")
    conclusion = latest.get("conclusion")
    url = latest.get("html_url")
    if not isinstance(url, str) or not url.startswith("https://github.com/"):
        raise ValueError("workflow run has no GitHub URL")

    if age_hours < -0.1:
        reason = "The latest schema comparison has a future timestamp."
    elif status == "completed" and conclusion == "success" and age_hours < MAX_SUCCESS_AGE_HOURS:
        reason = "The latest schema comparison completed successfully."
    elif status == "completed" and conclusion == "success":
        reason = f"The last successful schema comparison is {age_hours:.1f} hours old."
    elif status == "completed":
        reason = f"The latest schema comparison completed with conclusion {conclusion!r}."
    elif status in {"queued", "in_progress", "waiting", "pending"} and age_hours < MAX_RUNNING_HOURS:
        reason = "The latest schema comparison is still within its four-hour run window."
    elif status in {"queued", "in_progress", "waiting", "pending"}:
        reason = f"The latest schema comparison is {status} after {age_hours:.1f} hours."
    else:
        reason = f"The latest schema comparison has an unknown status {status!r}."

    healthy = (
        status == "completed" and conclusion == "success" and 0 <= age_hours < MAX_SUCCESS_AGE_HOURS
    ) or (
        status in {"queued", "in_progress", "waiting", "pending"} and 0 <= age_hours < MAX_RUNNING_HOURS
    )
    return {
        "status": "healthy" if healthy else "unhealthy",
        "reason": reason,
        "run_url": url,
        "run_status": status,
        "conclusion": conclusion,
        "age_hours": round(age_hours, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()

    report = assess_runs(json.loads(args.runs.read_text()), datetime.now(UTC))
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.markdown.write_text(
        "The self-hosted dev/production schema monitor is not producing a fresh successful run.\n\n"
        f"Reason: {report['reason']}\n\n"
        f"Latest run: {report['run_url'] or 'none'}\n"
    )
    print(json.dumps(report))


if __name__ == "__main__":
    main()
