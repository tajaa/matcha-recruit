"""Huume ER Copilot bridge (er_skill.py): the pilot-tool safety envelope
registration, the name-free case_brief read, and ask_case's grounded/
citation-gated answer.

    cd server && ./venv/bin/python -m pytest tests/huume/test_huume_er_skill.py -q
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.matcha.services.huume import er_skill
from app.matcha.services.huume.actions import PILOT_TOOL_REQUIRED_FEATURE, evaluate_pilot_tool
from app.matcha.services.huume.tools import TOOLS_BY_NAME

MOD = "app.matcha.services.huume.er_skill"
CASE_ID = "3f6b1c22-0000-4000-8000-000000000020"
EMP_ID = "3f6b1c22-0000-4000-8000-000000000021"


def _conn_ctx(conn):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _fake_resp(text):
    resp = MagicMock()
    resp.text = text
    return resp


class TestRegistration:
    def test_both_tools_require_er_copilot(self):
        assert PILOT_TOOL_REQUIRED_FEATURE["er_case_brief"] == "er_copilot"
        assert PILOT_TOOL_REQUIRED_FEATURE["ask_er_copilot"] == "er_copilot"

    def test_both_tools_registered(self):
        assert "er_case_brief" in TOOLS_BY_NAME
        assert "ask_er_copilot" in TOOLS_BY_NAME

    def test_ask_er_copilot_has_intent_hints(self):
        assert TOOLS_BY_NAME["ask_er_copilot"].intent_hints
        assert not TOOLS_BY_NAME["er_case_brief"].discovery  # takes an id, not a batch scan

    def test_gate_refuses_without_flag(self):
        features = {"huume": True, "matcha_work": True, "er_copilot": False}
        reason = evaluate_pilot_tool(tool="ask_er_copilot", role="client", features=features)
        assert reason and "er_copilot" in reason


class TestCaseBrief:
    @pytest.mark.asyncio
    async def test_invalid_case_id_is_an_error(self):
        result = await er_skill.case_brief(company_id=uuid4(), case_id="not-a-uuid")
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_case_not_found_is_tenant_scoped(self, monkeypatch):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value=None)
        monkeypatch.setattr("app.database.get_connection", MagicMock(return_value=_conn_ctx(conn)))

        result = await er_skill.case_brief(company_id=uuid4(), case_id=CASE_ID)

        assert result["status"] == "not_found"
        # The query itself is company-scoped — assert the WHERE clause carries both params.
        args = conn.fetchrow.await_args.args
        assert "company_id" in args[0]

    @pytest.mark.asyncio
    async def test_case_brief_is_name_free(self, monkeypatch):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={
            "id": CASE_ID, "case_number": "ER-2026-07-AB12", "title": "Workplace complaint",
            "status": "open", "category": "harassment",
            # er_cases.created_at is a naive TIMESTAMP column — asyncpg hands
            # back a naive datetime (no tzinfo), the actual shape open_days
            # must handle. A None fixture here would skip the arithmetic
            # entirely and hide a naive/aware TypeError.
            "created_at": datetime(2026, 6, 1),
            "involved_employees": json.dumps([{"employee_id": EMP_ID, "role": "complainant"}]),
        })
        conn.fetch = AsyncMock(side_effect=[
            [{"id": "doc-1", "filename": "statement.pdf", "document_type": "email"}],  # documents
            # summary/events text names the complainant on purpose — the
            # stored analysis is model-authored prose over the case, and
            # case_brief's headline must never copy it verbatim.
            [{"analysis_type": "timeline", "analysis_data": json.dumps({
                "summary": "3 events found involving Maria Chen.",
                "events": [{"desc": "e1"}, {"desc": "e2"}, {"desc": "e3"}],
            }), "generated_at": None}],  # analyses
        ])
        conn.fetchval = AsyncMock(return_value=2)  # notes_count
        monkeypatch.setattr("app.database.get_connection", MagicMock(return_value=_conn_ctx(conn)))

        result = await er_skill.case_brief(company_id=uuid4(), case_id=CASE_ID)

        assert result["status"] == "ok"
        assert result["involved_count"] == 1
        assert result["analyses"]["timeline"]["headline"] == "3 events on file."
        assert result["notes_count"] == 2
        assert isinstance(result["open_days"], int) and result["open_days"] >= 0

        encoded = json.dumps(result)
        assert EMP_ID not in encoded  # no employee ids leak into the model-facing payload
        assert "complainant" not in encoded
        assert "Maria Chen" not in encoded  # stored analysis free text must not leak either


class TestAskCase:
    @pytest.fixture(autouse=True)
    def _stub_settings(self, monkeypatch):
        # ask_case resolves its model via get_settings().analysis_model (same
        # source build_er_analyzer uses for the standalone ER Copilot page) —
        # settings aren't loaded in the unit test process, so every test in
        # this class needs this stubbed regardless of whether it reaches the
        # Gemini call.
        settings = MagicMock()
        settings.analysis_model = "gemini-3-flash-preview"
        monkeypatch.setattr(f"{MOD}.get_settings", lambda: settings)

    @pytest.mark.asyncio
    async def test_no_case_id_anywhere_is_an_error(self, monkeypatch):
        conn = MagicMock()
        monkeypatch.setattr("app.database.get_connection", MagicMock(return_value=_conn_ctx(conn)))

        result = await er_skill.ask_case(
            company_id=uuid4(), actor_user_id=uuid4(), case_id=None, state_case_id=None,
            question="what happened?",
        )
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_empty_question_is_an_error(self):
        result = await er_skill.ask_case(
            company_id=uuid4(), actor_user_id=uuid4(), case_id=CASE_ID, state_case_id=None, question="   ",
        )
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_resolves_state_case_id_when_no_explicit_id(self, monkeypatch):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={
            "id": CASE_ID, "case_number": "ER-2026-07-AB12", "title": "Complaint",
            "involved_employees": "[]",
        })
        conn.fetch = AsyncMock(return_value=[])  # analysis_rows
        conn.execute = AsyncMock()  # insert_audit_log's write
        monkeypatch.setattr("app.database.get_connection", MagicMock(return_value=_conn_ctx(conn)))
        monkeypatch.setattr(
            "app.matcha.services.er.er_case_context.load_guidance_context",
            AsyncMock(return_value={"all_doc_text_rows": []}),
        )
        monkeypatch.setattr(
            "app.matcha.services.er.er_compliance_grounding.build_jurisdiction_corpus",
            AsyncMock(return_value=("", {}, False)),
        )

        result = await er_skill.ask_case(
            company_id=uuid4(), actor_user_id=uuid4(), case_id=None, state_case_id=CASE_ID,
            question="what does the record show?",
        )

        assert result["status"] == "ok"
        assert result["case_id"] == CASE_ID

    @pytest.mark.asyncio
    async def test_citation_gate_drops_invented_ids(self, monkeypatch):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={
            "id": CASE_ID, "case_number": "ER-2026-07-AB12", "title": "Complaint",
            "involved_employees": "[]",
        })
        conn.fetch = AsyncMock(return_value=[
            {"analysis_type": "timeline", "analysis_data": json.dumps({"summary": "ok"}), "generated_at": None},
        ])
        conn.execute = AsyncMock()  # insert_audit_log's write
        monkeypatch.setattr("app.database.get_connection", MagicMock(return_value=_conn_ctx(conn)))
        monkeypatch.setattr(
            "app.matcha.services.er.er_case_context.load_guidance_context",
            AsyncMock(return_value={"all_doc_text_rows": [
                {"id": "doc-1", "filename": "notes.pdf", "document_type": "other", "scrubbed_text": "Some notes."},
            ]}),
        )
        monkeypatch.setattr(
            "app.matcha.services.er.er_compliance_grounding.build_jurisdiction_corpus",
            AsyncMock(return_value=("", {}, False)),
        )
        genai = MagicMock()
        genai.aio.models.generate_content = AsyncMock(return_value=_fake_resp(json.dumps({
            "answer": "The timeline shows one prior incident.",
            "evidence": [
                {"point": "real", "cited_ids": ["ercase:analysis-timeline"]},
                {"point": "fake", "cited_ids": ["ercase:doc-bogus"]},
            ],
        })))
        monkeypatch.setattr(f"{MOD}._genai", MagicMock(return_value=genai))

        result = await er_skill.ask_case(
            company_id=uuid4(), actor_user_id=uuid4(), case_id=CASE_ID, state_case_id=None,
            question="what does the timeline show?",
        )

        assert result["status"] == "ok"
        assert "ercase:analysis-timeline" in result["citations"]
        assert "ercase:doc-bogus" in result["dropped_citations"]
        assert any(rec["cid"] == "ercase:analysis-timeline" for rec in result["citation_records"])

    @pytest.mark.asyncio
    async def test_bare_id_missing_prefix_is_repaired(self, monkeypatch):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={
            "id": CASE_ID, "case_number": "ER-1", "title": "Complaint", "involved_employees": "[]",
        })
        conn.fetch = AsyncMock(return_value=[])
        conn.execute = AsyncMock()  # insert_audit_log's write
        monkeypatch.setattr("app.database.get_connection", MagicMock(return_value=_conn_ctx(conn)))
        monkeypatch.setattr(
            "app.matcha.services.er.er_case_context.load_guidance_context",
            AsyncMock(return_value={"all_doc_text_rows": [
                # cid is "ercase:doc-1" — the corpus renders it with the "ercase:" namespace
                # prefix, and the model here answers with just "doc-1", dropping it.
                {"id": "1", "filename": "notes.pdf", "document_type": "other", "scrubbed_text": "Some notes."},
            ]}),
        )
        monkeypatch.setattr(
            "app.matcha.services.er.er_compliance_grounding.build_jurisdiction_corpus",
            AsyncMock(return_value=("", {}, False)),
        )
        genai = MagicMock()
        genai.aio.models.generate_content = AsyncMock(return_value=_fake_resp(json.dumps({
            "answer": "Answer.",
            "evidence": [{"point": "p", "cited_ids": ["doc-1"]}],  # "ercase:" prefix dropped by the model
        })))
        monkeypatch.setattr(f"{MOD}._genai", MagicMock(return_value=genai))

        result = await er_skill.ask_case(
            company_id=uuid4(), actor_user_id=uuid4(), case_id=CASE_ID, state_case_id=None, question="q?",
        )

        assert result["citations"] == ["ercase:doc-1"]
        assert result["dropped_citations"] == []

    @pytest.mark.asyncio
    async def test_gemini_failure_degrades_to_error(self, monkeypatch):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={
            "id": CASE_ID, "case_number": "ER-1", "title": "Complaint", "involved_employees": "[]",
        })
        conn.fetch = AsyncMock(return_value=[])
        conn.execute = AsyncMock()  # insert_audit_log's write
        monkeypatch.setattr("app.database.get_connection", MagicMock(return_value=_conn_ctx(conn)))
        monkeypatch.setattr(
            "app.matcha.services.er.er_case_context.load_guidance_context",
            AsyncMock(return_value={"all_doc_text_rows": [
                {"id": "doc-1", "filename": "notes.pdf", "document_type": "other", "scrubbed_text": "Some notes."},
            ]}),
        )
        monkeypatch.setattr(
            "app.matcha.services.er.er_compliance_grounding.build_jurisdiction_corpus",
            AsyncMock(return_value=("", {}, False)),
        )
        genai = MagicMock()
        genai.aio.models.generate_content = AsyncMock(side_effect=RuntimeError("timeout"))
        monkeypatch.setattr(f"{MOD}._genai", MagicMock(return_value=genai))

        result = await er_skill.ask_case(
            company_id=uuid4(), actor_user_id=uuid4(), case_id=CASE_ID, state_case_id=None, question="q?",
        )

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_no_records_at_all_skips_gemini(self, monkeypatch):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={
            "id": CASE_ID, "case_number": "ER-1", "title": "Complaint", "involved_employees": "[]",
        })
        conn.fetch = AsyncMock(return_value=[])  # no analyses
        conn.execute = AsyncMock()  # insert_audit_log's write
        monkeypatch.setattr("app.database.get_connection", MagicMock(return_value=_conn_ctx(conn)))
        monkeypatch.setattr(
            "app.matcha.services.er.er_case_context.load_guidance_context",
            AsyncMock(return_value={"all_doc_text_rows": []}),  # no documents
        )
        monkeypatch.setattr(
            "app.matcha.services.er.er_compliance_grounding.build_jurisdiction_corpus",
            AsyncMock(return_value=("", {}, False)),  # no jurisdiction records
        )
        genai_call = MagicMock()
        monkeypatch.setattr(f"{MOD}._genai", genai_call)

        result = await er_skill.ask_case(
            company_id=uuid4(), actor_user_id=uuid4(), case_id=CASE_ID, state_case_id=None, question="q?",
        )

        assert result["status"] == "ok"
        genai_call.assert_not_called()
