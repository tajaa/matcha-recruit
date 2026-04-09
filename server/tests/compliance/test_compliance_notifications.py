"""
Test: Validate compliance change detection shows in Notifications tab.

This script:
1. Tweaks a compliance requirement's current_value (Berkeley min wage)
2. Creates test compliance_alerts (change + new_requirement + low-confidence)
3. Verifies the dashboard notifications query only returns the right alerts
4. Reverts everything

Run: python server/tests/test_compliance_notifications.py
Requires: SSH tunnel to prod DB on port 15432, or local DB with data.
"""

import subprocess
import sys
import json
import uuid
from datetime import datetime

# --- Config ---
# We'll shell out to psql via docker on the DB server
SSH_KEY = "roonMT-arm.pem"
DB_HOST = "3.101.83.217"
DB_CMD_PREFIX = (
    f'ssh -i {SSH_KEY} ec2-user@{DB_HOST} '
    '"docker exec matcha-postgres psql -U matcha -d matcha -t -c'
)

# Test targets
LOCATION_ID = "d434e960-c58d-44e2-911b-fa03b2fc852f"  # Berkeley
COMPANY_ID = "78db605a-0f59-40b7-98ba-3832f9d75008"
REQ_ID = "38b140e1-3162-4e58-862b-8bb0b8eedca6"  # Berkeley Local Minimum Wage
ORIGINAL_VALUE = "$19.18/hr"
TEST_VALUE = "$19.50/hr"


def run_sql(sql: str, fetch=True) -> str:
    """Run SQL on prod DB via SSH + docker exec."""
    # Set RLS context so tenant-isolated tables are accessible
    full_sql = (
        f"SET app.current_tenant_id = '{COMPANY_ID}';\n"
        f"SET app.is_admin = 'true';\n"
        f"{sql}"
    )
    ssh_cmd = [
        "ssh", "-i", SSH_KEY, f"ec2-user@{DB_HOST}",
        "docker exec -i matcha-postgres psql -U matcha -d matcha -t"
    ]
    result = subprocess.run(ssh_cmd, input=full_sql, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"SQL ERROR: {result.stderr.strip()}")
        sys.exit(1)
    # Filter out SET confirmations from output
    lines = [l for l in result.stdout.strip().split("\n") if l.strip() and l.strip() != "SET"]
    return "\n".join(lines)


def main():
    print("=" * 60)
    print("COMPLIANCE NOTIFICATIONS TEST")
    print("=" * 60)

    # Generate unique IDs for test alerts
    alert_change_id = str(uuid.uuid4())
    alert_new_req_id = str(uuid.uuid4())
    alert_low_conf_id = str(uuid.uuid4())
    alert_null_conf_id = str(uuid.uuid4())

    try:
        # Step 1: Verify current value
        current = run_sql(
            f"SELECT current_value FROM compliance_requirements WHERE id = '{REQ_ID}'"
        )
        print(f"\n[1] Current value: {current.strip()}")
        # psql may strip $ signs in output, so check the numeric part
        assert "19.18" in current, f"Expected '19.18' in value, got '{current}'"

        # Step 2: Tweak the requirement value
        run_sql(
            f"UPDATE compliance_requirements SET current_value = '{TEST_VALUE}' "
            f"WHERE id = '{REQ_ID}'"
        )
        verify = run_sql(
            f"SELECT current_value FROM compliance_requirements WHERE id = '{REQ_ID}'"
        )
        print(f"[2] Tweaked value: {verify.strip()}")
        assert "19.50" in verify, f"Expected '19.50' in value, got '{verify}'"

        # Step 3: Create 3 test alerts
        # A) Material change alert (should appear in notifications)
        run_sql(
            f"INSERT INTO compliance_alerts "
            f"(id, location_id, company_id, requirement_id, title, message, severity, status, "
            f"alert_type, confidence_score, category) VALUES ("
            f"'{alert_change_id}', '{LOCATION_ID}', '{COMPANY_ID}', '{REQ_ID}', "
            f"'TEST: Min wage changed', 'Berkeley minimum wage changed from {ORIGINAL_VALUE} to {TEST_VALUE}', "
            f"'critical', 'unread', 'change', 0.85, 'minimum_wage')"
        )
        print(f"[3a] Created change alert: {alert_change_id}")

        # B) New requirement alert (should NOT appear in notifications)
        run_sql(
            f"INSERT INTO compliance_alerts "
            f"(id, location_id, company_id, requirement_id, title, message, severity, status, "
            f"alert_type, confidence_score, category) VALUES ("
            f"'{alert_new_req_id}', '{LOCATION_ID}', '{COMPANY_ID}', '{REQ_ID}', "
            f"'TEST: New requirement found', 'Some new requirement discovered', "
            f"'warning', 'unread', 'new_requirement', 0.9, 'minimum_wage')"
        )
        print(f"[3b] Created new_requirement alert: {alert_new_req_id}")

        # C) Low-confidence change alert (should NOT appear in notifications)
        run_sql(
            f"INSERT INTO compliance_alerts "
            f"(id, location_id, company_id, requirement_id, title, message, severity, status, "
            f"alert_type, confidence_score, category) VALUES ("
            f"'{alert_low_conf_id}', '{LOCATION_ID}', '{COMPANY_ID}', '{REQ_ID}', "
            f"'TEST: Low confidence change', 'Unverified change detected', "
            f"'info', 'unread', 'change', 0.3, 'minimum_wage')"
        )
        print(f"[3c] Created low-confidence alert: {alert_low_conf_id}")

        # Step 4: Run the exact dashboard notifications query
        print(f"\n[4] Testing dashboard notifications query...")
        notif_query = (
            f"SELECT id::text, title, severity, alert_type, confidence_score "
            f"FROM compliance_alerts "
            f"WHERE company_id = '{COMPANY_ID}' "
            f"AND created_at > NOW() - INTERVAL '30 days' "
            f"AND alert_type = 'change' "
            f"AND COALESCE(confidence_score, 1.0) >= 0.6 "
            f"AND id IN ('{alert_change_id}', '{alert_new_req_id}', '{alert_low_conf_id}')"
        )
        notif_results = run_sql(notif_query)
        print(f"  Notifications query returned:")
        if notif_results:
            for line in notif_results.strip().split("\n"):
                print(f"    {line.strip()}")
        else:
            print("    (empty)")

        # Verify: only the high-confidence change alert should appear
        assert alert_change_id in (notif_results or ""), \
            "FAIL: High-confidence change alert missing from notifications!"
        assert alert_new_req_id not in (notif_results or ""), \
            "FAIL: new_requirement alert should NOT appear in notifications!"
        assert alert_low_conf_id not in (notif_results or ""), \
            "FAIL: Low-confidence alert should NOT appear in notifications!"

        print("\n  ✓ PASS: Only material change alert with confidence >= 0.6 appears")

        # Step 5: Verify ALL alerts still visible in Compliance Alerts tab (unfiltered)
        all_query = (
            f"SELECT id::text, title, alert_type, confidence_score "
            f"FROM compliance_alerts "
            f"WHERE company_id = '{COMPANY_ID}' "
            f"AND id IN ('{alert_change_id}', '{alert_new_req_id}', '{alert_low_conf_id}')"
        )
        all_results = run_sql(all_query)
        count = len([l for l in all_results.strip().split("\n") if l.strip()]) if all_results else 0
        print(f"\n[5] Compliance Alerts tab (unfiltered): {count} alerts visible")
        assert count == 3, f"FAIL: Expected 3 alerts in full view, got {count}"
        print("  ✓ PASS: All 3 alerts visible in Compliance Alerts tab")

        # Step 6: Test NULL confidence_score handling (overflow alerts)
        run_sql(
            f"INSERT INTO compliance_alerts "
            f"(id, location_id, company_id, requirement_id, title, message, severity, status, "
            f"alert_type, confidence_score, category) VALUES ("
            f"'{alert_null_conf_id}', '{LOCATION_ID}', '{COMPANY_ID}', '{REQ_ID}', "
            f"'TEST: NULL confidence change', 'Overflow alert with no confidence', "
            f"'warning', 'unread', 'change', NULL, 'minimum_wage')"
        )
        null_check = run_sql(
            f"SELECT id::text FROM compliance_alerts "
            f"WHERE id = '{alert_null_conf_id}' "
            f"AND alert_type = 'change' "
            f"AND COALESCE(confidence_score, 1.0) >= 0.6"
        )
        assert alert_null_conf_id in (null_check or ""), \
            "FAIL: NULL confidence alert should appear (COALESCE to 1.0)!"
        print(f"\n[6] NULL confidence_score handling:")
        print("  ✓ PASS: NULL confidence treated as 1.0, alert visible in notifications")

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED")
        print("=" * 60)

    finally:
        # REVERT everything
        print(f"\n[CLEANUP] Reverting changes...")

        # Revert the requirement value
        run_sql(
            f"UPDATE compliance_requirements SET current_value = '{ORIGINAL_VALUE}' "
            f"WHERE id = '{REQ_ID}'"
        )
        reverted = run_sql(
            f"SELECT current_value FROM compliance_requirements WHERE id = '{REQ_ID}'"
        )
        print(f"  Requirement reverted to: {reverted.strip()}")

        # Delete all test alerts
        run_sql(
            f"DELETE FROM compliance_alerts WHERE id IN ("
            f"'{alert_change_id}', '{alert_new_req_id}', "
            f"'{alert_low_conf_id}', '{alert_null_conf_id}')"
        )

        print("  Test alerts deleted")
        print("  ✓ All changes reverted")


if __name__ == "__main__":
    main()
