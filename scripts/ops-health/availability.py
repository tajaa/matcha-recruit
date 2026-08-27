#!/usr/bin/env python3
"""Assess TLS, disk, and worker status collected by the availability workflow."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

TLS_WARN_SECONDS = 21 * 24 * 60 * 60
DISK_WARN_PERCENT = 80          # unchanged
DISK_CRITICAL_PERCENT = 90      # unchanged
# Absolute floors are a backstop for volumes small enough that a percentage is
# meaningless, NOT a capacity target. App root is 16G and DB root is 8G, so an
# 8 GiB "free" floor was permanently tripped at 56% used.
DISK_WARN_BYTES = 1 * 1024**3
DISK_CRITICAL_BYTES = 512 * 1024**2


def probe_tls(host: str) -> dict:
    command = [
        "openssl", "s_client", "-connect", f"{host}:443", "-servername", host,
        "-verify_return_error", "-verify_hostname", host,
    ]
    try:
        conn = subprocess.run(command, input="", text=True, capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"host": host, "ok": False, "reason": f"TLS connection failed: {exc}"}
    if conn.returncode:
        return {"host": host, "ok": False, "reason": (conn.stderr or conn.stdout)[-500:]}
    cert = subprocess.run(
        ["openssl", "x509", "-noout", "-enddate"], input=conn.stdout, text=True,
        capture_output=True, timeout=10,
    )
    if cert.returncode or "=" not in cert.stdout:
        return {"host": host, "ok": False, "reason": "server returned no readable certificate"}
    try:
        expires = datetime.strptime(cert.stdout.strip().split("=", 1)[1], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
    except ValueError as exc:
        return {"host": host, "ok": False, "reason": f"unparseable expiry: {exc}"}
    remaining = int((expires - datetime.now(UTC)).total_seconds())
    return {
        "host": host,
        "ok": remaining > TLS_WARN_SECONDS,
        "expires_at": expires.isoformat(),
        "days_remaining": remaining // 86400,
        "reason": "certificate expires within 21 days" if remaining <= TLS_WARN_SECONDS else None,
    }


def assess_disk(record: dict) -> dict:
    total = int(record.get("total_kb", 0)) * 1024
    available = int(record.get("available_kb", 0)) * 1024
    if total <= 0 or available < 0:
        return {**record, "ok": False, "severity": "critical", "reason": "filesystem unavailable"}
    used_percent = round((1 - available / total) * 100)
    critical = used_percent >= DISK_CRITICAL_PERCENT or available < DISK_CRITICAL_BYTES
    warning = used_percent >= DISK_WARN_PERCENT or available < DISK_WARN_BYTES
    return {
        **record,
        "ok": not warning,
        "severity": "critical" if critical else "warning" if warning else "ok",
        "used_percent": used_percent,
        "available_gib": round(available / 1024**3, 1),
        "reason": "disk capacity threshold exceeded" if warning else None,
    }


def parse_status(path: Path) -> dict:
    result: dict[str, object] = {"disks": []}
    for line in path.read_text().splitlines():
        parts = line.split("|")
        if parts[0] == "DF" and len(parts) == 4:
            result["disks"].append({"mount": parts[1], "total_kb": parts[2], "available_kb": parts[3]})
        elif len(parts) == 2:
            result[parts[0].lower()] = parts[1]
    return result


def assess_worker(status: dict) -> dict:
    failures = []
    if status.get("worker") != "running":
        failures.append("matcha-worker container is not running")
    if status.get("celery_ping") != "ok":
        failures.append("Celery ping failed")
    if status.get("timer_enabled") != "enabled" or status.get("timer_active") != "active":
        failures.append("matcha-worker.timer is not enabled and active")
    if status.get("timer_result") not in {"success", ""}:
        failures.append(f"matcha-worker.service result is {status['timer_result']}")
    if not status.get("timer_last") or status.get("timer_last") == "n/a":
        failures.append("matcha-worker.timer has no recorded trigger")
    try:
        timer_age = int(status.get("timer_age_seconds", -1))
    except (TypeError, ValueError):
        timer_age = -1
    if timer_age < 0:
        failures.append("matcha-worker.timer trigger age is unavailable")
    elif timer_age > 90 * 60:
        failures.append(f"matcha-worker.timer last triggered {timer_age // 60} minutes ago")
    # lego-gummfit.service renews the *.gummfit.com wildcard cert daily. A
    # broken renewal (e.g. a dead Hostinger DNS API token) is otherwise
    # invisible until the 21-day TLS_WARN_SECONDS threshold trips — this adds
    # ~75 days of earlier warning by watching the renewal service directly.
    if status.get("lego_failed") == "failed":
        failures.append("lego-gummfit.service (cert renewal) is in a failed state")
    lego_result = status.get("lego_result", "missing")
    if lego_result != "success":
        failures.append(f"lego-gummfit.service last result is {lego_result}")
    if status.get("lego_timer_enabled") != "enabled" or status.get("lego_timer_active") != "active":
        failures.append("lego-gummfit.timer is not enabled and active")
    if not status.get("lego_timer_last") or status.get("lego_timer_last") == "n/a":
        failures.append("lego-gummfit.timer has no recorded trigger")
    try:
        lego_timer_age = int(status.get("lego_timer_age_seconds", -1))
    except (TypeError, ValueError):
        lego_timer_age = -1
    if lego_timer_age < 0:
        failures.append("lego-gummfit.timer trigger age is unavailable")
    elif lego_timer_age > 30 * 60 * 60:
        failures.append(f"lego-gummfit.timer last triggered {lego_timer_age // 3600} hours ago")
    return {"ok": not failures, "failures": failures}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domains", type=Path, required=True)
    parser.add_argument("--app-status", type=Path, required=True)
    parser.add_argument("--db-status", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    domains = json.loads(args.domains.read_text()).get("domains", [])
    hosts = sorted({"hey-matcha.com", "www.hey-matcha.com", "gummfit.com", "www.gummfit.com", "origin.gummfit.com", "tls-probe.gummfit.com", *domains})
    app = parse_status(args.app_status)
    db = parse_status(args.db_status)
    disks = [assess_disk({"host": "app", **disk}) for disk in app["disks"]]
    disks += [assess_disk({"host": "db", **disk}) for disk in db["disks"]]
    worker = assess_worker(app)
    report = {"tls": [probe_tls(host) for host in hosts], "disks": disks, "worker": worker}
    report["ok"] = all(item["ok"] for item in report["tls"]) and all(item["ok"] for item in disks) and worker["ok"]
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
