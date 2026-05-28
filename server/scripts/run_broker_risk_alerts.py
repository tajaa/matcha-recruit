"""Manually trigger the broker risk-alert sweep against the connected DB.

Runs the same async body the Celery worker runs (`_run_broker_risk_alerts`),
so it honors the scheduler_settings gate — enable the row first:

    UPDATE scheduler_settings SET enabled = true WHERE task_key = 'broker_risk_alerts';

Usage (DEV tunnel up, from server/):
    ./venv/bin/python scripts/run_broker_risk_alerts.py

Prints the result dict: {evaluated, candidates, sent, skipped, resolved} or
{"skipped": True, ...} when the scheduler row is missing/disabled.
"""
import asyncio

from app.config import load_settings
from app.workers.tasks.broker_risk_alerts import _run_broker_risk_alerts


def main():
    load_settings()  # worker process normally does this in @worker_process_init
    result = asyncio.run(_run_broker_risk_alerts())
    print("RESULT:", result)


if __name__ == "__main__":
    main()
