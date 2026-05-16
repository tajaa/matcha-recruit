"""Shared helpers for IR Incidents submodules.

Cross-cutting utilities used by more than one submodule live here. As
endpoints migrate out of `_legacy.py`, the helpers they need follow them
here so `_legacy.py` ends step 11 empty and is deleted.

Initial content is intentionally empty — symbols arrive in later steps:
- `_sse`, `_company_filter`, `_to_naive_utc`, `_utc_now_naive`,
  `_parse_occurred_at`, `_get_incident_with_company_check`,
  `_safe_json_loads`, `_coerce_metadata_dict`, `parse_witnesses`,
  `row_to_response`, `generate_incident_number`, `log_audit`,
  `_resolve_employee_refs`, `_auto_classify_incident_task`,
  `_get_company_admin_contacts`, `send_ir_notifications_task`,
  `_FIELD_WHITELIST`, `_FIELD_LABELS`, `_VALID_INCIDENT_TYPES`,
  `_VALID_SEVERITIES`, `_VALID_STATUSES`, `_validate_field_value`
"""
