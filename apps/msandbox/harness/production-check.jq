def valid_production_http_check:
  (.path | type == "string" and startswith("/") and length <= 500
    and (contains("://") | not) and (contains("?") | not)
    and (contains("..") | not) and (test("[[:space:]]") | not))
  and (.expected_status | type == "number" and floor == . and . >= 100 and . <= 599)
  and ((.body_contains // "") | type == "string" and length <= 200)
  and ((.body_absent // "") | type == "string" and length <= 200);
