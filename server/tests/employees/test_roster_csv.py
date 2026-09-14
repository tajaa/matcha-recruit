"""The field rules and line accounting every roster CSV importer shares."""

import pytest

from app.matcha.routes.employees import _shared
from app.matcha.services.employees import roster_csv

COLUMNS = ("name", "address", "city", "state", "zipcode")


def test_bulk_upload_and_the_wizard_normalize_a_work_state_identically():
    # _shared keeps the name its five callers import; the implementation is the
    # service's, so the two importers cannot answer this differently.
    assert _shared._normalize_work_state is roster_csv.normalize_work_state
    assert roster_csv.normalize_work_state("California") == ("CA", True)
    assert roster_csv.normalize_work_state(" ca ") == ("CA", True)
    assert roster_csv.normalize_work_state("") == (None, True)
    assert roster_csv.normalize_work_state("Westeros") == (None, False)


def test_email_rule_is_the_one_bulk_upload_applies():
    assert roster_csv.is_valid_email("jane.doe+tag@example.com")
    assert not roster_csv.is_valid_email("not-an-email")
    assert not roster_csv.is_valid_email("")
    assert not roster_csv.is_valid_email(None)


def test_rows_carry_their_source_line_past_skipped_blanks():
    rows = roster_csv.read_rows("a,b\n\n\nc,d\n")
    assert [(row.values, row.line) for row in rows] == [(["a", "b"], 1), (["c", "d"], 4)]


def test_a_quoted_newline_does_not_shift_later_rows():
    text = 'name,address,city,state,zipcode\nHQ,"1 Main\nSuite 2",Austin,TX,78701\nWest,9 Oak,Austin,TX,78702'
    rows = roster_csv.read_rows(text)
    assert rows[1].values[1] == "1 Main\nSuite 2"
    assert rows[2].line == 4


def test_parse_table_reports_the_real_line_of_an_incomplete_row():
    with pytest.raises(roster_csv.RosterCsvError, match="Row 4 must contain all 5 values"):
        roster_csv.parse_table(
            "name,address,city,state,zipcode\n\n\nHQ,1 Main,,TX,78701", COLUMNS, max_rows=500
        )


def test_parse_table_rejects_a_wrong_header_and_a_header_only_file():
    with pytest.raises(roster_csv.RosterCsvError, match="Expected header: name,address"):
        roster_csv.parse_table("name,address\nHQ,1 Main", COLUMNS, max_rows=500)
    with pytest.raises(roster_csv.RosterCsvError, match="at least one data row"):
        roster_csv.parse_table("name,address,city,state,zipcode\n", COLUMNS, max_rows=500)
    with pytest.raises(roster_csv.RosterCsvError, match="CSV is empty"):
        roster_csv.parse_table("", COLUMNS, max_rows=500)


def test_parse_table_caps_rows():
    body = "\n".join(f"S{i},{i} Main,Austin,TX,78701" for i in range(3))
    with pytest.raises(roster_csv.RosterCsvError, match="more than 2 data rows"):
        roster_csv.parse_table(
            "name,address,city,state,zipcode\n" + body, COLUMNS, max_rows=2
        )


def test_a_byte_order_mark_does_not_break_the_header():
    parsed = roster_csv.parse_table(
        "﻿name,address,city,state,zipcode\nHQ,1 Main,Austin,TX,78701",
        COLUMNS,
        max_rows=500,
    )
    assert parsed[0][0]["name"] == "HQ"


def test_require_unique_names_the_repeating_line():
    with pytest.raises(roster_csv.RosterCsvError, match="Row 7 duplicates"):
        roster_csv.require_unique([("a", 5), ("b", 6), ("a", 7)], "duplicates an earlier row")
