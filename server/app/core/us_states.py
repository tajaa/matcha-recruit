"""Canonical US jurisdiction codes.

50 states + DC + the 5 inhabited US territories, USPS 2-letter codes. Any code
that grounds a US compliance jurisdiction from external input — employee
`work_state` validation (CSV / manual create), HRIS location ingest — must gate
on this set so a typo or a foreign region (e.g. a Canadian province "ON") can't
silently create an ungrounded jurisdiction.

This is the shared home for what used to be copied per-module
(`_VALID_WORK_STATE_CODES`, `_US_STATE_CODES`, …). Prefer importing from here.
"""

US_STATE_CODES: frozenset[str] = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO",
    "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA",
    "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    # US territories.
    "AS", "GU", "MP", "PR", "VI",
})
